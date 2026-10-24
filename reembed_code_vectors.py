#!/usr/bin/env python3
"""
reembed_code_vectors.py — second pass of ingestion. Fills ONE code-vector
store with one set of vectors for EVERY stored body version of every atomic
skill. No re-ingest: bodies come from code_at:<commit>:<def_key>.

The worker (next_claude.py) calls run() by itself when an ingestion run
ends. By hand:

    python reembed_code_vectors.py --provider voyage [--dry-run]
        [--slab 200] [--workers 4] [--full] [--force]
    python reembed_code_vectors.py --provider qwen
(--db /path/to/repo/.unified-brain.db or DB_PATH in .env; the store's key from .env)

What it does per atomic skill (active and deleted):
  1. Reads the skill's version list: skill_history entries + the current
     record. Each one names a commit and the def_key at that commit.
  2. Reads the body stored for each version (code_at:<commit>:<def_key>)
     and the ingester's chunk ranges saved next to it.
  3. Embeds each body and stores it as its own version, with the commit
     range it was valid for: from its own commit up to the commit of the
     next stored version, or the commit that deleted the skill.
Then each composite gets its one centroid row from its members' newest
versions (no embedding call).

Which skills: the first run walks every skill. A later run walks only the
skills that the commits ingested since the last finished run created,
changed or deleted (commit_skills:<commit>:*). --full walks every skill
again. A version that is already stored is never embedded again, only its
commit range is refreshed; --force embeds everything again.
--slab is skills per batch; --workers is batches sent at the same time.

Progress is written to Redis, HASH embed_run:<provider>:
  status  waiting | running | done | failed
  total / done        atomic skills to walk / walked
  versions / embedded stored body versions seen / sent to the embedder
  failed              batches that failed
  upto_rank           commits up to this rank are fully covered
embed_run_alive:<provider> exists while a run is alive (it expires by
itself when the process dies).
"""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv

import skills_lib
import store

load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

CHUNK_TARGET_CHARS = 16_000
KEY_ENV = {"voyage": "VOYAGE_API_KEY", "qwen": "DEEPINFRA_API_KEY"}
OPEN = skills_lib.CODE_VEC_OPEN
ALIVE_SECONDS = 900


def state_key(provider: str) -> str:
    return f"embed_run:{provider}"


def alive_key(provider: str) -> str:
    return f"embed_run_alive:{provider}"


def mark_waiting(r, providers: list) -> None:
    """Pass 1 is running and pass 2 will follow: say so in the org Redis."""
    for name in providers:
        try:
            if r.hget(state_key(name), "status") != "running":
                r.hset(state_key(name), "status", "waiting")
        except Exception as e:
            print(f"⚠️  embed_run waiting mark failed [{name}]: {e}")


def line_window_ranges(body: str, target: int = CHUNK_TARGET_CHARS):
    if len(body) <= target:
        return None
    lines = body.splitlines()
    out, start, size = [], 0, 0
    for i, ln in enumerate(lines):
        size += len(ln) + 1
        if size >= target:
            out.append([start, i + 1])
            start, size = i + 1, 0
    if start < len(lines):
        out.append([start, len(lines)])
    return out if len(out) > 1 else None


def stored_ranges(body: str, raw_chunks):
    """Chunk ranges saved by the ingester in pass 1. Field missing (data
    ingested before the ranges were saved): fall back to line windows."""
    if raw_chunks is None:
        return line_window_ranges(body)
    try:
        ranges = json.loads(raw_chunks)
    except (ValueError, TypeError):
        return line_window_ranges(body)
    return ranges or None


def skill_versions(sk: dict, history: list, rank: dict) -> list:
    """[(commit, [def_keys, newest first])], oldest version first.
    Same chain _touch_diffs reads: skill_history entries, then the current
    record. One commit can list more than one def_key when the symbol moved
    lines without a body change; the body is stored under at least one."""
    chain = []
    for raw in history:
        try:
            e = json.loads(raw)
        except (ValueError, TypeError):
            continue
        if e.get("def_key"):
            chain.append((e.get("commit_hash") or "", e["def_key"]))
    if sk.get("def_key"):
        chain.append((sk.get("commit_hash") or "", sk["def_key"]))
    by_commit: dict = {}
    for c, dk in chain:
        dks = by_commit.setdefault(c, [])
        if dk in dks:
            dks.remove(dk)
        dks.insert(0, dk)
    return sorted(by_commit.items(), key=lambda kv: rank.get(kv[0], 0))


def run(r, rb, emb, *, slab: int = 200, workers: int = 4, force: bool = False,
        dry: bool = False, full: bool = False, log=print) -> dict:
    """One second-pass run for ONE store on ONE org Redis.
    r = text client, rb = binary client, emb = skills_lib.CodeEmbedder.
    Returns the totals. Never raises: a failure ends in status 'failed'."""
    skey, akey = state_key(emb.name), alive_key(emb.name)
    if hasattr(r, "migrate_vec_tables") and r.vec_tables_to_migrate():
        r.migrate_vec_tables(log)          # older file: rebuild the vector tables once
    total = {"skills": 0, "versions": 0, "embedded": 0, "kept": 0, "texts": 0,
             "chars": 0, "no_body": 0, "skills_no_body": 0, "failed": 0,
             "composites": 0}

    def progress(**fields):
        if dry:
            return
        try:
            pipe = r.pipeline(transaction=False)
            if fields:
                pipe.hset(skey, mapping={k: str(v) for k, v in fields.items()})
            pipe.set(akey, "1", ex=ALIVE_SECONDS)
            pipe.execute()
        except Exception as e:
            log(f"⚠️  embed_run progress write failed: {e}")

    try:
        if not dry and skills_lib.get_code_vector_index(rb, emb) is None:
            raise RuntimeError("could not create the code vector index")
        commits = r.zrange("commit_order", 0, -1)
        rank = {h: i for i, h in enumerate(commits)}
        head = len(commits) - 1

        # Which skills: every skill, or only the ones touched by the commits
        # ingested after the last finished run.
        upto = None if (full or force) else r.hget(skey, "upto_rank")
        if upto is None:
            ids = sorted(r.smembers("skills_active") | r.smembers("skills_obsolete"))
            mode = "all skills"
        else:
            fresh = commits[int(upto) + 1:]
            pipe = r.pipeline(transaction=False)
            for c in fresh:
                for ev in ("new", "updated", "obsoleted"):
                    pipe.smembers(f"commit_skills:{c}:{ev}")
            ids = sorted(set().union(*pipe.execute())) if fresh else []
            mode = f"skills touched by {len(fresh)} new commit(s)"

        atomics, composites, skipped = [], [], 0
        for i in range(0, len(ids), 1000):
            part = ids[i:i + 1000]
            for sid, raw in zip(part, r.mget([f"skill:{s}" for s in part])):
                if not raw:
                    skipped += 1
                    continue
                sk = json.loads(raw)
                if sk.get("is_composite"):
                    composites.append((sid, sk))
                elif sid.startswith("~") or not sk.get("def_key"):
                    skipped += 1                  # blueprints / no position
                else:
                    atomics.append((sid, sk))
        log(f"pass 2 [{emb.name}] {mode}: atomics {len(atomics)}, "
            f"composites {len(composites)}, skipped {skipped}, commits {len(commits)}")
        progress(status="running", mode=mode, total=len(atomics), done=0,
                 versions=0, embedded=0, failed=0, error="",
                 started_at=int(time.time()), finished_at="")

        def run_slab(batch):
            st = {"skills": len(batch), "versions": 0, "embedded": 0, "kept": 0,
                  "texts": 0, "chars": 0, "no_body": 0, "skills_no_body": 0}
            # Version list of every skill in the batch: one round trip.
            pipe = r.pipeline(transaction=False)
            for sid, _sk in batch:
                pipe.lrange(f"skill_history:{sid}", 0, -1)
            plans = [skill_versions(sk, hist, rank)
                     for (_sid, sk), hist in zip(batch, pipe.execute())]

            # Which versions are already stored: one round trip. A stored
            # version had a body, so its body is not read again.
            slots = [(si, vi) for si, vers in enumerate(plans)
                     for vi in range(len(vers))]
            if force or not slots:
                stored = set()
            else:
                pipe = rb.pipeline(transaction=False)
                for si, vi in slots:
                    ver = skills_lib.code_version_id(plans[si][vi][0])
                    pipe.exists(f"{emb.prefix}_mean:{batch[si][0]}:{ver}")
                stored = {s for s, x in zip(slots, pipe.execute()) if x}

            # The body of every version that is not stored yet: one round trip.
            pipe = r.pipeline(transaction=False)
            reads = []
            for si, vi in slots:
                c, dks = plans[si][vi]
                if not c or (si, vi) in stored:
                    continue          # no commit: no code_at: copy exists
                for dk in dks:
                    pipe.hmget(f"code_at:{c}:{dk}", "body", "chunks")
                    reads.append((si, vi))
            found = {}
            for key, (body, chunks) in zip(reads, pipe.execute()):
                if body and key not in found:
                    found[key] = (body, chunks)

            # Versions that have a body, with the commit range each was
            # valid for. Entry: (sid, commit, def_key, body, chunks, from,
            # to, latest, obsolete); body is None for a stored version.
            todo = []
            for si, ((sid, sk), vers) in enumerate(zip(batch, plans)):
                obs = bool(sk.get("isObsolete", False))
                end = rank.get(sk.get("obsoleted_commit") or "", OPEN) if obs else OPEN
                have = []
                for vi, (c, dks) in enumerate(vers):
                    if (si, vi) in stored:
                        have.append((c, dks[0], None, None))
                    elif (si, vi) in found:
                        # Rows carry the newest address of this version.
                        have.append((c, dks[0]) + found[(si, vi)])
                    else:
                        st["no_body"] += 1
                if not have:
                    # Stored before code_at: existed. The only body is the
                    # live one (code:), or the deleted one (code_hist:). A
                    # deleted skill never reads code:, because a new symbol
                    # may now sit at the same address. It is filed as the
                    # version of the skill's last commit.
                    dk = sk["def_key"]
                    body, chunks = r.hmget(
                        f"{'code_hist' if obs else 'code'}:{dk}", "body", "chunks")
                    if not body:
                        st["skills_no_body"] += 1
                        continue
                    have.append((sk.get("commit_hash") or "", dk, body, chunks))
                for i, (c, dk, body, chunks) in enumerate(have):
                    last = i == len(have) - 1
                    todo.append((sid, c, dk, body, chunks, rank.get(c, 0),
                                 end if last else rank.get(have[i + 1][0], 0),
                                 last, obs))
            st["versions"] = len(todo)

            texts, index_of, owners = [], {}, []   # owners[i]: text indexes of todo[i]
            for sid, c, dk, body, chunks, fr, to, latest, obs in todo:
                if body is None:
                    # Already stored: refresh the commit range, no embedding.
                    st["kept"] += 1
                    if not dry:
                        skills_lib.set_code_version_window(
                            rb, emb.prefix, sid, c, from_rank=fr, to_rank=to,
                            latest=latest, obsolete=obs)
                    owners.append(None)
                    continue
                mine = []
                for text in skills_lib.chunk_texts(dk, body, stored_ranges(body, chunks)):
                    if text not in index_of:      # same text twice: embed it once
                        index_of[text] = len(texts)
                        texts.append(text)
                    mine.append(index_of[text])
                owners.append(mine)
            st["embedded"] = sum(1 for o in owners if o is not None)
            st["texts"] = len(texts)
            st["chars"] = sum(len(t) for t in texts)
            if dry or not texts:
                return st
            vecs = emb.embed(texts, "document")
            for t, mine in zip(todo, owners):
                if mine is None:
                    continue
                sid, c, dk, _body, _chunks, fr, to, latest, obs = t
                skills_lib.put_code_version(
                    rb, emb.prefix, sid, c, dk, [vecs[j] for j in mine],
                    from_rank=fr, to_rank=to, latest=latest, obsolete=obs)
            return st

        t0 = time.time()
        slabs = [atomics[i:i + slab] for i in range(0, len(atomics), slab)]
        with ThreadPoolExecutor(max_workers=max(workers, 1)) as pool:
            futures = [pool.submit(run_slab, b) for b in slabs]
            for fut in as_completed(futures):
                try:
                    st = fut.result()
                except Exception as e:
                    total["failed"] += 1
                    log(f"  ⚠️  pass 2 batch failed (the next run retries it): {e}")
                    progress(failed=total["failed"])
                    continue
                for k in st:
                    total[k] += st[k]
                progress(done=total["skills"], versions=total["versions"],
                         embedded=total["embedded"])
                log(f"  pass 2 [{emb.name}]: {total['skills']}/{len(atomics)} skills, "
                    f"{total['versions']} versions ({total['embedded']} embedded, "
                    f"{total['kept']} already stored), {total['texts']} texts, "
                    f"{time.time() - t0:.0f}s")

        if not dry:
            for sid, sk in composites:
                cc = skills_lib.composite_centroid(r, rb, sid, code_prefix=emb.prefix)
                if cc:
                    skills_lib.store_composite_code_vector(rb, sid, cc, prefix=emb.prefix)
                    if sk.get("isObsolete"):
                        skills_lib.set_code_version_window(
                            rb, emb.prefix, sid, "", obsolete=True)
                    total["composites"] += 1
            log(f"  pass 2 [{emb.name}]: composite centroids "
                f"{total['composites']}/{len(composites)}")

        if total["failed"]:
            # upto_rank stays: the next run walks the same commits again.
            progress(status="failed", finished_at=int(time.time()),
                     error=f"{total['failed']} batch(es) failed")
        else:
            progress(status="done", finished_at=int(time.time()), upto_rank=head)
    except Exception as e:
        total["failed"] += 1
        log(f"❌ pass 2 [{emb.name}] failed: {type(e).__name__}: {e}")
        progress(status="failed", failed=total["failed"],
                 finished_at=int(time.time()), error=str(e)[:300])
    finally:
        if not dry:
            try:
                r.delete(akey)
            except Exception:
                pass
    return total


def _arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main():
    dry = "--dry-run" in sys.argv
    provider = _arg("--provider")
    if provider not in KEY_ENV:
        sys.exit("--provider voyage|qwen is required")

    db = _arg("--db") or os.environ.get("DB_PATH", "")
    if not db:
        sys.exit("--db /path/to/repo/.unified-brain.db (or DB_PATH in .env) is required")
    key = os.environ.get(KEY_ENV[provider], "")
    if not key:
        sys.exit(f"{KEY_ENV[provider]} is required (.env)")
    emb = skills_lib.make_code_embedder(provider, key)
    if emb is None:
        sys.exit(f"could not build embedder '{provider}' (SDK missing?)")
    r  = store.open(db)
    rb = r.binary()
    print(f"store: {provider} → {emb.model} @{emb.dims}d, prefix {emb.prefix}:")

    t0 = time.time()
    total = run(r, rb, emb, slab=int(_arg("--slab", 200)),
                workers=int(_arg("--workers", 4)), force="--force" in sys.argv,
                dry=dry, full="--full" in sys.argv)

    row_kb = emb.dims * 4 / 1024
    print(f"{'DRY RUN — ' if dry else ''}{total['versions']} versions of "
          f"{total['skills']} atomics: {total['embedded']} embedded, "
          f"{total['kept']} already stored, {total['texts']} texts, "
          f"~{total['chars'] // 2:,} tokens (chars/2), "
          f"~{total['texts'] * row_kb / 1024:.0f} MB of new vectors at {emb.dims}d, "
          f"{time.time() - t0:.0f}s")
    print(f"versions in a skill's list with no stored body (their commits are "
          f"covered by the version before them): {total['no_body']}")
    print(f"skills with no stored body at all (no vectors): {total['skills_no_body']}")
    if total["failed"]:
        sys.exit(f"{total['failed']} batch(es) failed. Run the script again: "
                 f"finished versions are not embedded again.")


if __name__ == "__main__":
    main()
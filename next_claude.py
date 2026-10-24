#!/usr/bin/env python3
"""
unified-brain — ingest
----------------------
Reads a repository's git history and fills the repository's database
(<repo>/.unified-brain.db, one SQLite file) with one skill per symbol
version: bodies, call and reference edges, commit order. No LLM is called.
When the commits are done, one embedding pass fills the code-vector store
(reembed_code_vectors.run).

    python next_claude.py /path/to/repo                 # whole history
    python next_claude.py /path/to/repo --since <ref>   # commits after <ref>
    python next_claude.py /path/to/repo --resume        # continue after the last ingested commit
    python next_claude.py /path/to/repo --max 200       # at most N commits
    python next_claude.py /path/to/repo --no-embed      # skip the embedding pass
    python next_claude.py /path/to/repo --embed-only    # only the embedding pass
    python next_claude.py /path/to/repo --db /elsewhere/x.db   # database file elsewhere

Settings (.env): CODE_EMBED_PASS2 (voyage | qwen), VOYAGE_API_KEY /
DEEPINFRA_API_KEY, CODE_EMBED_PASS2_WORKERS.
"""
import asyncio
import json
import os
import sys
import time
import traceback

from dotenv import load_dotenv

import skills_lib
import reembed_code_vectors
import store
from defkey_reconciler import DefKeyReconciler, FilePayload, FileSymbolEntry, HunkDelta
from ingester import GitDiffIngester

load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

_CODE_EMBED_KEYS = {"voyage": "VOYAGE_API_KEY", "qwen": "DEEPINFRA_API_KEY"}


def _db_clients(db_path: str) -> tuple:
    """(text view, bytes view) of the repository's database file."""
    r = store.open(db_path)
    return r, r.binary()


def _pass2_embedders() -> list:
    """The code-vector stores filled after the run (CODE_EMBED_PASS2)."""
    out = []
    for name in [p.strip() for p in os.environ.get("CODE_EMBED_PASS2", "voyage").split(",") if p.strip()]:
        emb = skills_lib.make_code_embedder(name, os.environ.get(_CODE_EMBED_KEYS.get(name, ""), ""))
        if emb is None:
            print(f"⚠️  code-vector store '{name}' OFF (key or SDK missing)")
            continue
        out.append(emb)
        print(f"🔧 code-vector store '{name}': {emb.model} @{emb.dims}d → {emb.prefix}:")
    return out


# ── Payload → reconciler objects ─────────────────────────────────────────────

def _payload_to_file_payloads(payload: dict) -> tuple[dict, list[FilePayload]]:
    """Returns (definitions, file_payloads).
    definitions: def_key → body of every symbol the commit added or changed.
    file_payloads: the per-file context the reconciler needs."""
    definitions: dict = {}
    file_payloads: list[FilePayload] = []
    for sr in payload.get('searchResults', []):
        definitions.update(sr.get('definitions') or {})
        for fp_data in sr.get('files', []):
            all_symbols = [
                FileSymbolEntry(
                    name=s['name'],
                    line=s['line'],
                    structure_type=s['structureType'],
                    code=s['code'],
                    calls=s.get('calls', []) or [],
                    refs=s.get('refs', []) or [],
                    embedded=s.get('embedded', []) or [],
                    chunks=s.get('chunks', []) or [],
                )
                for s in fp_data.get('allSymbols', [])
            ]
            line_deltas = [
                HunkDelta(old_start=h['oldStart'], old_count=h['oldCount'],
                          new_start=h['newStart'], new_count=h['newCount'])
                for h in fp_data.get('lineDeltas', [])
            ]
            file_payloads.append(FilePayload(
                file_path=fp_data['filePath'],
                is_new=fp_data.get('isNew', False),
                is_deleted=fp_data.get('isDeleted', False),
                all_symbols=all_symbols,
                line_deltas=line_deltas,
                change_types=fp_data.get('changeTypes', {}),
            ))
    return definitions, file_payloads


def _def_key(file_path: str, sym: FileSymbolEntry) -> str:
    return f"{file_path}:{sym.name}:{sym.line}:{sym.structure_type}"


def _parse_def_key(def_key: str) -> tuple[str, str, int, str] | None:
    """'<file>:<symbol>:<line>:<type>' → (file, symbol, line, type). Splits
    from the right: file paths may contain colons."""
    parts = def_key.rsplit(":", 3)
    if len(parts) != 4:
        return None
    try:
        return parts[0], parts[1], int(parts[2]), parts[3]
    except ValueError:
        return None


def _symbol_of(def_key: str) -> str:
    p = _parse_def_key(def_key)
    return p[1] if p else def_key


def _active_skill_at(r, def_key: str) -> str | None:
    """The newest non-obsolete skill registered at this exact position."""
    for sid in reversed(r.lrange(f"symbol:{def_key}", 0, -1)):
        sid = sid.decode() if isinstance(sid, bytes) else sid
        raw = r.get(f"skill:{sid}")
        if raw and not json.loads(raw).get("isObsolete", False):
            return sid
    return None


def _register(reconciler: DefKeyReconciler, r, def_key: str, skill_id: str, commit_hash: str) -> None:
    p = _parse_def_key(def_key)
    if p:
        reconciler.register(filepath=p[0], symbol=p[1], line=p[2], struct_type=p[3],
                            skill_id=skill_id, redis_override=r, commit_hash=commit_hash)


# ── One commit ───────────────────────────────────────────────────────────────

async def ingest_payload(payload: dict, r, rb, reconciler: DefKeyReconciler,
                         commit_hash: str) -> dict | None:
    """Everything one commit changes, written to Redis. No LLM.
      1. register the commit (commit_order, commit_meta)
      2. reconcile the symbol index (drift, obsoleted, new, modified)
      3. store the body and the call/reference edges of every added or
         modified symbol (code:, code_at:<commit>:, calls:, refs:)
      4. a skill record for every new symbol; the existing skill updated
         for every modified one
    Returns the counts, or None when the commit changed no symbol."""
    commit_hash = payload.get('commitHash') or commit_hash
    goal = payload.get('goal', commit_hash)
    definitions, file_payloads = _payload_to_file_payloads(payload)
    if not definitions and not any(fp.is_deleted and fp.all_symbols for fp in file_payloads):
        return None

    t0 = time.perf_counter()
    seq = await asyncio.to_thread(
        skills_lib.register_commit, r, commit_hash, goal,
        payload.get("authorDate", "") or payload.get("author_date", ""),
        payload.get("author", "") or payload.get("authorName", ""),
        sorted({fp.file_path for fp in file_payloads}))

    # 2. reconcile
    results = await reconciler.reconcile_commit(
        file_payloads=file_payloads, commit_hash=commit_hash, goal=goal,
        redis_override=r, redis_binary_override=rb)
    new_keys: set[str] = set()
    modified_keys: set[str] = set()
    symbols: dict[str, FileSymbolEntry] = {}          # def_key → symbol (new + modified)
    for rec in results:
        for sym in rec.new_symbols:
            dk = f"{rec.file_path}:{sym.name}:{sym.line}:{sym.structure_type}"
            new_keys.add(dk); symbols[dk] = sym
        for sym in rec.modified_symbols:
            dk = f"{rec.file_path}:{sym.name}:{sym.line}:{sym.structure_type}"
            modified_keys.add(dk); symbols[dk] = sym
    drifted = sum(len(x.drifted) for x in results)
    obsoleted = sum(len(x.obsoleted) for x in results)

    # the symbols this commit added or changed, with a body
    changed: dict[str, str] = {}
    for fp in file_payloads:
        for dk, change_type in fp.change_types.items():
            if change_type in ('added', 'modified') and dk in definitions:
                changed[dk] = definitions[dk]

    # 3. bodies and edges — written here, unconditionally, so that every
    #    commit has its code_at: copies whatever happens to the skill save
    def _write_bodies_and_edges() -> tuple[int, int]:
        n = nref = 0
        for fp in file_payloads:
            if fp.is_deleted:
                continue
            for sym in fp.all_symbols:
                dk = _def_key(fp.file_path, sym)
                if fp.change_types.get(dk) not in ('added', 'modified'):
                    continue
                try:
                    skills_lib.store_code(r, dk, sym.code, commit_hash=commit_hash,
                                          chunks=sym.chunks or [])
                    n += skills_lib.write_call_edges(r, dk, sym.calls, commit_hash)
                    nref += skills_lib.write_ref_edges(r, dk, sym.refs or [], commit_hash)
                except Exception as e:
                    print(f"  ⚠️  body/edge write failed for {sym.name}: {e}")
        return n, nref
    n_calls, n_refs = await asyncio.to_thread(_write_bodies_and_edges)

    # 4. skills. A "new" symbol that already has an active skill at this
    #    exact position is an update, not a create (re-ingestion guard).
    to_update = {dk for dk in changed if dk in modified_keys}
    to_create = []
    for dk in changed:
        if dk in to_update:
            continue
        if _active_skill_at(r, dk):
            to_update.add(dk)
        else:
            to_create.append(dk)

    def _save_new() -> int:
        if not to_create:
            return 0
        items = [{"goal": goal, "vifs": [_symbol_of(dk)],
                  "description": "", "def_key": dk, "code_body": changed[dk],
                  "commit_hash": commit_hash,
                  "chunks": (symbols.get(dk).chunks if symbols.get(dk) else None)}
                 for dk in to_create]
        ids = skills_lib.save_skills_batch(r, rb, items, embedders=[])
        for dk, sid in zip(to_create, ids):
            if sid:
                _register(reconciler, r, dk, sid, commit_hash)
        return sum(1 for sid in ids if sid)

    def _update_existing() -> int:
        done = 0
        for dk in sorted(to_update):
            code = changed[dk]
            chunks = symbols.get(dk).chunks if symbols.get(dk) else None
            sid = _active_skill_at(r, dk)
            try:
                if sid:
                    skills_lib.update_skill_full(
                        r, rb, skill_id=sid, new_def_key=dk, new_code_body=code,
                        commit_hash=commit_hash, chunks=chunks, embedders=[],
                        code_vectors={})
                else:
                    sid = skills_lib.save_skill(
                        r, rb, goal=goal, vifs=[_symbol_of(dk)], def_key=dk,
                        code_body=code, commit_hash=commit_hash, chunks=chunks,
                        embedders=[], code_vectors={})
                _register(reconciler, r, dk, sid, commit_hash)
                done += 1
            except Exception as e:
                print(f"  ⚠️  skill update failed for {dk}: {e}")
        return done

    created = await asyncio.to_thread(_save_new)
    updated = await asyncio.to_thread(_update_existing)

    ms = (time.perf_counter() - t0) * 1000
    print(f"   {commit_hash[:8]} seq={seq}: new={len(new_keys)} modified={len(modified_keys)} "
          f"drifted={drifted} obsoleted={obsoleted} | skills created={created} updated={updated} "
          f"| edges calls={n_calls} refs={n_refs} | {ms:.0f}ms")
    return {"created": created, "updated": updated, "obsoleted": obsoleted,
            "drifted": drifted, "calls": n_calls, "refs": n_refs}


# ── The run ──────────────────────────────────────────────────────────────────

async def ingest_repo(repo_path: str, *, since: str | None, max_n: int | None,
                      r, rb) -> dict:
    ingester = GitDiffIngester(repo_path)
    reconciler = DefKeyReconciler(r, None, rb)
    commits = ingester.commit_range(since, max_n)
    print(f"\n🏗️  ingest {repo_path}: {len(commits)} commit(s)"
          + (f" after {since[:12]}" if since else "") + "\n")
    totals = {"commits": len(commits), "done": 0, "skipped": 0, "failed": 0,
              "created": 0, "updated": 0, "obsoleted": 0}
    # Progress for the timeline page's strip (GET /api/ingest/status).
    r.hset("ingest_run", mapping={
        "status": "running", "repo": os.path.basename(repo_path.rstrip("/")) or repo_path,
        "total": len(commits), "done": 0, "failed": 0, "current_commit": "",
        "started_at": int(time.time()), "finished_at": "", "last_error": ""})
    for i, h in enumerate(commits, 1):
        r.hset("ingest_run", "current_commit", h)
        r.set("ingest_run_alive", "1", ex=60)   # gone 60 s after a killed run
        for attempt in range(3):
            try:
                payload = await asyncio.to_thread(ingester.ingest_commit, h)
                res = await ingest_payload(payload, r, rb, reconciler, h)
                if res is None:
                    totals["skipped"] += 1
                else:
                    totals["done"] += 1
                    for k in ("created", "updated", "obsoleted"):
                        totals[k] += res[k]
                r.set("resume_point", h)
                break
            except Exception as e:
                if attempt < 2:
                    print(f"  ⚠️  retry {attempt + 1}/3 on {h[:8]}: {e}")
                    await asyncio.sleep(2)
                else:
                    print(f"  ❌ failed on {h[:8]}: {e}")
                    print(traceback.format_exc())
                    totals["failed"] += 1
                    r.hset("ingest_run", mapping={"failed": totals["failed"],
                                                  "last_error": f"{h[:12]}: {e}"[:300]})
        r.hset("ingest_run", "done", i)
        if i % 50 == 0:
            print(f"── {i}/{len(commits)} commits")
    r.hset("ingest_run", mapping={"status": "failed" if totals["failed"] else "done",
                                  "current_commit": "", "finished_at": int(time.time())})
    r.delete("ingest_run_alive")
    return totals


def embed_pass(r, rb) -> None:
    """One embedding pass over every stored body version (the only
    embedding call of the run)."""
    embs = _pass2_embedders()
    if not embs:
        print("⚠️  no code-vector store configured (CODE_EMBED_PASS2) — skipping embeddings")
        return
    workers = int(os.environ.get("CODE_EMBED_PASS2_WORKERS", "4"))
    reembed_code_vectors.mark_waiting(r, [e.name for e in embs])
    for emb in embs:
        print(f"\n🧬 embedding pass [{emb.name}]")
        total = reembed_code_vectors.run(r, rb, emb, workers=workers)
        print(f"   {total['versions']} versions of {total['skills']} skills: "
              f"{total['embedded']} embedded, {total['kept']} already stored, "
              f"{total['failed']} failed batch(es)")


def _arg(name: str, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main() -> None:
    flags_with_value = {"--since", "--max", "--db"}
    args, skip = [], False
    for i, a in enumerate(sys.argv[1:]):
        if skip:
            skip = False; continue
        if a in flags_with_value:
            skip = True; continue
        if not a.startswith("--"):
            args.append(a)
    if not args:
        print(__doc__)
        sys.exit(1)
    repo_path = os.path.abspath(args[0])
    db_path = _arg("--db") or store.db_path_for_repo(repo_path)
    r, rb = _db_clients(db_path)
    print(f"📁 database: {db_path}")

    t0 = time.time()
    if "--embed-only" not in sys.argv:
        since = _arg("--since")
        if "--resume" in sys.argv and not since:
            since = r.get("resume_point") or None
        max_n = int(_arg("--max")) if _arg("--max") else None
        totals = asyncio.run(ingest_repo(repo_path, since=since, max_n=max_n, r=r, rb=rb))
        print(f"\n✅ {totals['done']} commit(s) ingested, {totals['skipped']} with no symbol change, "
              f"{totals['failed']} failed; skills created={totals['created']} "
              f"updated={totals['updated']} obsoleted={totals['obsoleted']} "
              f"in {time.time() - t0:.0f}s")
        r.optimize()                      # merge the text index after the writes
    if "--no-embed" not in sys.argv:
        embed_pass(r, rb)
    print(f"\n⏱  total {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
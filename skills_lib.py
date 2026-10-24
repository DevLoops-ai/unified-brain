# unified-brain — cheaper, faster more accurate AI coding agents, by DevLoops
# Copyright (C) 2026 DevLoops SINGLE MEMBER P.C.
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
skills_lib.py
─────────────
Plain-Python skill operations over the one-file database (store.py).

All functions are sync. Async callers wrap with asyncio.to_thread when they
need parallelism via asyncio.gather.

No module-level Redis client — every function takes its dependencies
explicitly.
"""

import json
import struct
import uuid
import hashlib
from datetime import datetime
from typing import Optional
from openai import OpenAI
import re
import store as redis_lib        # the database; Store has the calls Redis had



# ── Code-body vectors (voyage-code-4) ─────────────────────────────────────────
# One set of rows per stored VERSION of a skill's body. A version is
# (skill_id, commit) and mirrors the body at code_at:<commit>:<def_key>.
# Versions are never overwritten by a later version.
#   cvec_at:<skill_id>:<commit>:<n>   HASH  one row per chunk — FT-indexed
#   cvec_at_mean:<skill_id>:<commit>  HASH  L2-normalised mean of the chunks
#   cvec_at_ver:<skill_id>            ZSET  commit → from_rank (version list)
# Chunk-row fields that say when a version is valid (ranks on commit_order):
#   from_rank  rank of the commit that wrote this body
#   to_rank    rank of the commit that replaced or deleted it
#              (CODE_VEC_OPEN while nothing has)
#   latest     "1" on the skill's newest version (stays "1" after deletion)
#   obsolete   "1" on every version once the skill is deleted
# Read as of commit rank R:  from_rank <= R < to_rank.
# Read with no commit range: latest == "1".
# Composites have no body: they keep ONE row set (their centroid), with an
# empty range (from_rank = to_rank = 0), so a commit-range search returns
# atomic versions only.
try:
    import voyageai
    VOYAGE_AVAILABLE = True
except ImportError as _voyage_err:
    voyageai = None
    VOYAGE_AVAILABLE = False
    print(f"⚠️  voyageai import failed — voyage store OFF: {_voyage_err}")

# One store per provider, each with its own prefix and FT index, so the
# replay can compare them on one Redis. Prefixes are chosen so no FT
# prefix matches another store's keys ("cvec_at:" ≠ "cvecq_at:" ≠
# "cvec_at_mean:" ≠ "cvec_at_ver:"). New names: the old one-row-per-skill
# rows (cvec:, cvec_mean:) and their indexes are no longer read or written.
CODE_EMBED_SPECS = {
    "voyage": {"model": "voyage-code-4",           "dims": 2048,
               "prefix": "cvec_at",  "index": "code_semantic_at"},
    "qwen":   {"model": "Qwen/Qwen3-Embedding-8B", "dims": 4096,
               "prefix": "cvecq_at", "index": "code_semantic_qwen_at"},
}
# to_rank of a version that no later commit has replaced or deleted.
CODE_VEC_OPEN = 2_000_000_000
DEEPINFRA_OPENAI_BASE = "https://api.deepinfra.com/v1/openai"
# Qwen3-Embedding has no input_type: the QUERY side carries an instruction
# prefix, the document side none. (Same string on every query — it is
# part of the model's contract, not a prompt to tune per call.)
QWEN_QUERY_INSTRUCT = ("Instruct: Given a question or a code snippet, retrieve "
                       "the source code that answers or implements it\nQuery: ")
# Request caps shared by both providers (Voyage: 1000 items / 120K tokens;
# DeepInfra is concurrency-limited, not token-limited). Code tokenises at
# ~2-3 chars/token, so 200K chars stays under 100K tokens.
CODE_EMBED_MAX_ITEMS = 1000
CODE_EMBED_MAX_CHARS = 200_000
# One text over the 32K window: Voyage truncates (truncation=True), the
# OpenAI-compatible endpoint rejects. The ingester's CHUNK_MAX_CHARS keeps
# chunks under it; this is the last guard for a single giant line.
CODE_EMBED_TEXT_CAP_CHARS = 90_000



import time as _time
from openai import APIError, APIConnectionError, RateLimitError, InternalServerError

def _embed_with_retry(openai_client: OpenAI, texts: list[str], max_retries: int = 5,
                      *, model: str):
    for attempt in range(max_retries):
        try:
            return openai_client.embeddings.create(model=model, input=texts,
                                                   encoding_format="float")
        except (RateLimitError, InternalServerError, APIConnectionError, APIError) as e:
            if attempt == max_retries - 1:
                raise
            wait = min(2.0 * (2 ** attempt), 30.0)
            print(f"  ⏳ Embedding retry {attempt+1}/{max_retries} ({type(e).__name__}), sleeping {wait:.0f}s")
            _time.sleep(wait)
    raise RuntimeError("unreachable: _embed_with_retry exhausted without raising")


def _voyage_retryable() -> tuple:
    """Transient error classes of the installed SDK, by name — auth and
    invalid-request errors are never retried."""
    if not VOYAGE_AVAILABLE:
        return ()
    err = getattr(voyageai, "error", None)
    names = ("RateLimitError", "ServerError", "ServiceUnavailableError",
             "Timeout", "APIConnectionError", "InternalServerError")
    return tuple(getattr(err, n) for n in names if err and hasattr(err, n))

_VOYAGE_RETRYABLE = _voyage_retryable()

def _voyage_with_retry(voyage, texts: list[str], input_type: str,
                       model: str, dims: int,
                       max_retries: int = 5) -> list[list[float]]:
    for attempt in range(max_retries):
        try:
            return voyage.embed(
                texts, model=model, input_type=input_type,
                output_dimension=dims, output_dtype="float",
                truncation=True,
            ).embeddings
        except _VOYAGE_RETRYABLE as e:
            if attempt == max_retries - 1:
                raise
            wait = min(2.0 * (2 ** attempt), 30.0)
            print(f"  ⏳ Code-embed retry {attempt+1}/{max_retries} "
                  f"({type(e).__name__}), sleeping {wait:.0f}s")
            _time.sleep(wait)
    raise RuntimeError("unreachable: _voyage_with_retry exhausted without raising")


class CodeEmbedder:
    """One code-vector store: provider client + model + dims + Redis prefix.
    Rows: <prefix>:<skill_id>:<commit>:<n> (FT-indexed),
    <prefix>_mean:<skill_id>:<commit>, <prefix>_ver:<skill_id>."""

    def __init__(self, name: str, client):
        spec = CODE_EMBED_SPECS[name]
        self.name, self.client = name, client
        self.model, self.dims = spec["model"], spec["dims"]
        self.prefix, self.index = spec["prefix"], spec["index"]

    def index_schema(self) -> dict:
        return {
            "index": {"name": self.index, "prefix": f"{self.prefix}:",
                      "storage_type": "hash"},
            "fields": [
                {"name": "skill_id",  "type": "tag"},
                {"name": "def_key",   "type": "tag"},
                {"name": "commit",    "type": "tag"},
                {"name": "chunk",     "type": "numeric"},
                {"name": "obsolete",  "type": "tag"},
                {"name": "latest",    "type": "tag"},
                {"name": "from_rank", "type": "numeric"},
                {"name": "to_rank",   "type": "numeric"},
                {"name": "embedding", "type": "vector", "attrs": {
                    "dims": self.dims, "algorithm": "hnsw",
                    "distance_metric": "cosine", "datatype": "float32",
                    "m": 16, "ef_construction": 200, "ef_runtime": 40}},
            ],
        }

    def _call(self, batch: list[str], input_type: str) -> list[list[float]]:
        if self.name == "voyage":
            return _voyage_with_retry(self.client, batch, input_type,
                                      self.model, self.dims)
        if input_type == "query":
            batch = [QWEN_QUERY_INSTRUCT + t for t in batch]
        resp = _embed_with_retry(self.client, batch, model=self.model)
        return [d.embedding for d in resp.data]

    def embed(self, texts: list[str], input_type: str) -> list[bytes]:
        """Batch-embed, chunked at the request caps.
        input_type: 'document' for stored chunks, 'query' for searches."""
        if not texts:
            return []
        texts = [t[:CODE_EMBED_TEXT_CAP_CHARS] for t in texts]
        out: list[bytes] = []
        batch, chars = [], 0
        def _flush():
            nonlocal batch, chars
            if batch:
                for v in self._call(batch, input_type):
                    out.append(struct.pack(f"{len(v)}f", *v))
            batch, chars = [], 0
        for t in texts:
            if batch and (len(batch) >= CODE_EMBED_MAX_ITEMS
                          or chars + len(t) > CODE_EMBED_MAX_CHARS):
                _flush()
            batch.append(t)
            chars += len(t)
        _flush()
        return out


def make_code_embedder(name: str, api_key: str) -> Optional["CodeEmbedder"]:
    """None when the key is missing (store off) or the SDK is absent."""
    if not api_key:
        return None
    if name == "voyage":
        return CodeEmbedder(name, voyageai.Client(api_key=api_key)) \
            if VOYAGE_AVAILABLE else None
    if name == "qwen":
        return CodeEmbedder(name, OpenAI(api_key=api_key,
                                         base_url=DEEPINFRA_OPENAI_BASE))
    raise ValueError(f"unknown code embedder {name!r}")




def chunk_texts(def_key: str, body: str, ranges=None) -> list[str]:
    """Texts to embed for one symbol. ranges = ingester's `chunks`
    ([[start,end), …] line indices over body); None/empty = one text.
    Every chunk carries the header (file, symbol, kind) and the body's
    first line (the signature), so a chunk never loses its identity."""
    p = parse_def_key(def_key)
    header = (f"{p[0]}\n{p[1]} [{p[3]}]\n" if p else f"{def_key}\n")
    if not ranges:
        return [header + body]
    lines = body.splitlines()
    sig = lines[0] if lines else ""
    out = []
    for i, (a, b) in enumerate(ranges):
        piece = "\n".join(lines[a:b])
        out.append(header + (piece if i == 0 else sig + "\n…\n" + piece))
    return out or [header + body]


def _l2_mean(vectors: list[bytes]) -> Optional[bytes]:
    import numpy as np
    if not vectors:
        return None
    m = np.mean([np.frombuffer(v, dtype=np.float32) for v in vectors], axis=0)
    n = np.linalg.norm(m)
    return (m / n).astype(np.float32).tobytes() if n >= 1e-9 else None


def _b2s(v):
    return v.decode() if isinstance(v, bytes) else v


def code_version_id(commit_hash: str) -> str:
    """Key part that names one version. "0" = a body stored with no commit."""
    return commit_hash or "0"


def commit_rank(redis: redis_lib.Store, commit_hash: str, default: int = 0) -> int:
    """Rank of a commit on commit_order; `default` when it is not there."""
    r = redis.zrank("commit_order", commit_hash) if commit_hash else None
    return int(r) if r is not None else default


def put_code_version(redis_binary: redis_lib.Store, prefix: str, skill_id: str,
                     commit_hash: str, def_key: str, vectors: list[bytes], *,
                     from_rank: int, to_rank: int = CODE_VEC_OPEN,
                     latest: bool = True, obsolete: bool = False) -> None:
    """Write ONE version of ONE skill in ONE store: its chunk rows, its mean
    row and its entry in the skill's version list. Other versions are not
    touched. Writing the same version again replaces it. Raises on failure."""
    ver = code_version_id(commit_hash)
    mean_key = f"{prefix}_mean:{skill_id}:{ver}"
    old_n = int(redis_binary.hget(mean_key, b"n") or 0)
    pipe = redis_binary.pipeline(transaction=False)
    for i in range(len(vectors), old_n):       # same version, fewer chunks now
        pipe.delete(f"{prefix}:{skill_id}:{ver}:{i}")
    for i, vec in enumerate(vectors):
        pipe.hset(f"{prefix}:{skill_id}:{ver}:{i}", mapping={
            b"skill_id":  skill_id.encode(),
            b"def_key":   def_key.encode(),
            b"commit":    ver.encode(),
            b"chunk":     str(i).encode(),
            b"obsolete":  b"1" if obsolete else b"0",
            b"latest":    b"1" if latest else b"0",
            b"from_rank": str(int(from_rank)).encode(),
            b"to_rank":   str(int(to_rank)).encode(),
            b"embedding": vec,
        })
    mean = _l2_mean(vectors)
    pipe.hset(mean_key, mapping={
        b"embedding": mean if mean else vectors[0],
        b"n":         str(len(vectors)).encode(),
        b"def_key":   def_key.encode(),
    })
    pipe.zadd(f"{prefix}_ver:{skill_id}", {ver: int(from_rank)})
    pipe.execute()


def set_code_version_window(redis_binary: redis_lib.Store, prefix: str,
                            skill_id: str, commit_hash: str, *,
                            from_rank: Optional[int] = None,
                            to_rank: Optional[int] = None,
                            latest: Optional[bool] = None,
                            obsolete: Optional[bool] = None) -> None:
    """Change the validity fields of ONE stored version. The embeddings are
    not touched and no embedding call is made. Fields left as None stay."""
    ver = code_version_id(commit_hash)
    n = int(redis_binary.hget(f"{prefix}_mean:{skill_id}:{ver}", b"n") or 0)
    fields = {}
    if from_rank is not None:
        fields[b"from_rank"] = str(int(from_rank)).encode()
    if to_rank is not None:
        fields[b"to_rank"] = str(int(to_rank)).encode()
    if latest is not None:
        fields[b"latest"] = b"1" if latest else b"0"
    if obsolete is not None:
        fields[b"obsolete"] = b"1" if obsolete else b"0"
    if not n or not fields:
        return
    pipe = redis_binary.pipeline(transaction=False)
    for i in range(n):
        pipe.hset(f"{prefix}:{skill_id}:{ver}:{i}", mapping=fields)
    if from_rank is not None:
        pipe.zadd(f"{prefix}_ver:{skill_id}", {ver: int(from_rank)})
    pipe.execute()


def store_code_vectors(redis_binary: redis_lib.Store, skill_id: str,
                       def_key: str, vectors: list[bytes],
                       prefix: str = "cvec_at", commit_hash: str = "") -> None:
    """Live ingestion, atomic skills: add the body written by commit_hash as
    the skill's newest version in ONE store and close the version it
    replaces. The replaced version keeps its rows."""
    if not vectors:
        return
    try:
        ver = code_version_id(commit_hash)
        rank = commit_rank(redis_binary, commit_hash)
        ver_key = f"{prefix}_ver:{skill_id}"
        newest = redis_binary.zrevrange(ver_key, 0, 0)
        newest = _b2s(newest[0]) if newest else None
        if newest != ver and redis_binary.zscore(ver_key, ver) is not None:
            # An older commit was ingested again: new vectors, same range.
            row = redis_binary.hmget(f"{prefix}:{skill_id}:{ver}:0",
                                     b"from_rank", b"to_rank", b"latest", b"obsolete")
            put_code_version(
                redis_binary, prefix, skill_id, commit_hash, def_key, vectors,
                from_rank=int(row[0] or rank),
                to_rank=int(row[1] or CODE_VEC_OPEN),
                latest=row[2] == b"1", obsolete=row[3] == b"1")
            return
        if newest and newest != ver:
            set_code_version_window(redis_binary, prefix, skill_id, newest,
                                    to_rank=rank, latest=False)
        put_code_version(redis_binary, prefix, skill_id, commit_hash, def_key,
                         vectors, from_rank=rank)
    except Exception as e:
        print(f"⚠️  Failed to store code vectors for {skill_id}: {e}")


def store_composite_code_vector(redis_binary: redis_lib.Store, skill_id: str,
                                vector: bytes, prefix: str = "cvec_at") -> None:
    """A composite's centroid in ONE store. One row set per composite,
    replaced on every refresh: a centroid is not a stored body, so it has no
    versions. Its range is empty (from_rank = to_rank = 0), so a search in a
    commit range never returns it; a search with no range does."""
    if not vector:
        return
    try:
        put_code_version(redis_binary, prefix, skill_id, "", "", [vector],
                         from_rank=0, to_rank=0, latest=True)
    except Exception as e:
        print(f"⚠️  Failed to store composite code vector for {skill_id}: {e}")


def flag_code_vectors_obsolete(redis_binary: redis_lib.Store, skill_id: str,
                               commit_hash: str = "") -> None:
    """The skill was deleted by commit_hash. In every store: all its versions
    are flagged obsolete, and its newest version stops being valid at that
    commit. No row is removed. A store with no rows for this skill costs one
    ZRANGE and nothing else."""
    try:
        end = commit_rank(redis_binary, commit_hash, default=CODE_VEC_OPEN)
        for spec in CODE_EMBED_SPECS.values():
            p = spec["prefix"]
            vers = [_b2s(v) for v in redis_binary.zrange(f"{p}_ver:{skill_id}", 0, -1)]
            for i, ver in enumerate(vers):
                close = None
                if i == len(vers) - 1:
                    cur = redis_binary.hget(f"{p}:{skill_id}:{ver}:0", b"to_rank")
                    if int(cur or 0) == CODE_VEC_OPEN:   # still open: close it
                        close = end
                set_code_version_window(redis_binary, p, skill_id, ver,
                                        to_rank=close, obsolete=True)
    except Exception as e:
        print(f"⚠️  Failed to flag code vectors obsolete for {skill_id}: {e}")


def code_mean_vectors(redis_binary: redis_lib.Store, prefix: str,
                      skill_ids: list[str],
                      to_rank: Optional[int] = None) -> list[Optional[bytes]]:
    """One mean vector per skill id, in the same order. None when the skill
    has no stored version (for that commit).
    to_rank=None: the skill's newest version.
    to_rank=R:    the version that was valid at commit rank R, which is the
                  newest one written at or before R. A composite always
                  gives its one centroid."""
    if not skill_ids:
        return []
    pipe = redis_binary.pipeline(transaction=False)
    for sid in skill_ids:
        if to_rank is None:
            pipe.zrevrange(f"{prefix}_ver:{sid}", 0, 0)
        else:
            pipe.zrevrangebyscore(f"{prefix}_ver:{sid}", int(to_rank), "-inf",
                                  start=0, num=1)
    vers = [(_b2s(v[0]) if v else None) for v in pipe.execute()]
    pipe = redis_binary.pipeline(transaction=False)
    for sid, ver in zip(skill_ids, vers):
        pipe.hget(f"{prefix}_mean:{sid}:{ver or '-'}", b"embedding")
    return [v or None for v in pipe.execute()]


def get_code_vector_index(redis_binary: redis_lib.Store,
                          embedder: "CodeEmbedder") -> Optional[bool]:
    """True when the store's vector table for this embedder exists (it is
    created here when missing); None when vectors are not available."""
    try:
        return True if redis_binary.ensure_vec_table(embedder.prefix, embedder.dims) else None
    except Exception as e:
        print(f"⚠️  Failed to build code vector table: {e}")
        return None




# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def parse_symbol_key(key: str) -> Optional[tuple[str, str, int, str]]:
    """Parses 'symbol:<filepath>:<symbol>:<line>:<type>'."""
    if not key.startswith("symbol:"):
        return None
    rest = key[len("symbol:"):]
    parts = rest.rsplit(":", 3)
    if len(parts) != 4:
        return None
    filepath, symbol, line_str, struct_type = parts
    try:
        return filepath, symbol, int(line_str), struct_type
    except ValueError:
        return None


def parse_def_key(def_key: str) -> Optional[tuple[str, str, int, str]]:
    """Parses 'filepath:symbol:line:type'."""
    parts = def_key.rsplit(":", 3)
    if len(parts) != 4:
        return None
    filepath, symbol, line_str, struct_type = parts
    try:
        return filepath, symbol, int(line_str), struct_type
    except ValueError:
        return None


def skill_symbols(skill: dict) -> list[str]:
    if skill.get("vifs"):
        return skill["vifs"]
    if skill.get("blueprints"):
        return skill["blueprints"]
    parsed = parse_def_key(skill.get("def_key", ""))
    return [parsed[1]] if parsed else []




def save_goal(redis: redis_lib.Store, goal: str) -> str:
    goal_hash = hashlib.md5(goal.encode()).hexdigest()[:12]
    if not redis.get(f"goal:{goal_hash}"):
        redis.set(f"goal:{goal_hash}", json.dumps({"text": goal}))
    return goal_hash


def register_commit(redis: redis_lib.Store, commit_hash: str, goal="", author_date="", author="", files=None) -> int:
    """Idempotent: first ingestion of a hash fixes its order; re-ingestion keeps it.
    Score = monotonic ingestion sequence (happy path: matches git walk order)."""
    if not commit_hash:
        return -1
    existing = redis.zscore("commit_order", commit_hash)
    if existing is not None:
        return int(existing)
    seq = redis.incr("commit_seq")
    redis.zadd("commit_order", {commit_hash: seq}, nx=True)
    redis.set(f"commit_meta:{commit_hash}", json.dumps({
        "goal": goal, "ingested_at": datetime.now().isoformat(),
        "author_date": author_date, "author": author,
        "files": files or [],
    }))
    return seq

def record_commit_event(redis: redis_lib.Store, commit_hash: str,
                        event: str, skill_id: str) -> None:
    """event ∈ {'new', 'updated', 'obsoleted'}. No-op without a commit_hash."""
    if commit_hash and skill_id:
        redis.sadd(f"commit_skills:{commit_hash}:{event}", skill_id)

# ── Call edges ────────────────────────────────────────────────────────────────

def write_call_edges(
    redis: redis_lib.Store,
    def_key: str,
    calls: list,                # [{"name": str, "line": int, "snippet": str}]
    commit_hash: str,
) -> int:
    """Diff-write a symbol's outgoing call edges.

    Provenance rules:
    - A surviving edge keeps its original 'commit'.
    - Same callee at a changed line = moved call → inherits old 'commit'
      (name-first matching, nearest line on duplicates).
    - Genuinely new edges are stamped with commit_hash and recorded in
      commit_calls:<hash> (immutable history).
    - Erased edges leave current state (calls:/called_by:); history untouched.
    Returns count of genuinely new edges.
    """
    fwd_key = f"calls:{def_key}"
    old_raw = redis.hgetall(fwd_key)
    old: dict[str, dict] = {}
    for f, v in old_raw.items():
        f = f.decode() if isinstance(f, bytes) else f
        v = v.decode() if isinstance(v, bytes) else v
        try:
            old[f] = json.loads(v)
        except (json.JSONDecodeError, TypeError):
            continue

    # Bucket old entries by callee name for move-matching
    old_by_name: dict[str, list] = {}
    for f, rec in old.items():
        name = f.rsplit(":", 1)[0]
        old_by_name.setdefault(name, []).append((f, rec))

    new_fields: dict[str, str] = {}
    new_edges:  list[dict] = []
    matched_old: set[str] = set()

    for c in calls:
        name, line = c.get("name", ""), int(c.get("line", 0))
        if not name:
            continue
        field = f"{name}:{line}"
        if field in new_fields:
            continue  # duplicate call site in payload — first wins
        exact = old.get(field)
        if exact is not None and field not in matched_old:
            # unchanged position → keep record as-is (preserves commit)
            new_fields[field] = json.dumps({
                "snippet": c.get("snippet", exact.get("snippet", "")),
                "commit":  exact.get("commit", commit_hash),
            })
            matched_old.add(field)
            continue
        # moved? nearest-line same-name unmatched old entry
        candidates = [(f, r) for f, r in old_by_name.get(name, [])
                      if f not in matched_old]
        if candidates:
            f_old, rec = min(
                candidates,
                key=lambda t: abs(int(t[0].rsplit(":", 1)[1]) - line),
            )
            matched_old.add(f_old)
            new_fields[field] = json.dumps({
                "snippet": c.get("snippet", ""),
                "commit":  rec.get("commit", commit_hash),
            })
            continue
        # genuinely new
        new_fields[field] = json.dumps({
            "snippet": c.get("snippet", ""),
            "commit":  commit_hash,
        })
        new_edges.append({"caller": def_key, "callee": name, "line": line,
                          "snippet": c.get("snippet", "")})

    old_names = {f.rsplit(":", 1)[0] for f in old}
    new_names = {f.rsplit(":", 1)[0] for f in new_fields}

    pipe = redis.pipeline(transaction=False)
    # Erased edges are history, not garbage: stamp the removing commit and
    # keep them so a windowed read can reconstruct callers at any commit.
    erased = {f: rec for f, rec in old.items() if f not in matched_old}
    if erased and commit_hash:
        pipe.hset(f"calls_hist:{def_key}", mapping={
            f: json.dumps({**rec, "removed": commit_hash}) for f, rec in erased.items()
        })
        for f in erased:
            pipe.sadd(f"called_by_hist:{f.rsplit(':', 1)[0]}", def_key)
    pipe.delete(fwd_key)
    if new_fields:
        pipe.hset(fwd_key, mapping=new_fields)
    for name in new_names - old_names:
        pipe.sadd(f"called_by:{name}", def_key)
    for name in old_names - new_names:
        pipe.srem(f"called_by:{name}", def_key)
    if commit_hash:
        for e in new_edges:
            pipe.sadd(f"commit_calls:{commit_hash}", json.dumps(e))
    pipe.execute()
    return len(new_edges)


def clear_call_edges(redis: redis_lib.Store, def_key: str,
                     commit_hash: str = "") -> None:
    """Symbol deleted: move its outgoing edges from current state to history.
    called_by:<its own name> is deliberately left intact — a non-empty set
    after obsoletion IS the 'obsoleted but still called' flag."""
    fwd_key = f"calls:{def_key}"
    raw = redis.hgetall(fwd_key)
    pipe = redis.pipeline(transaction=False)
    hist: dict[str, str] = {}
    for f, v in raw.items():
        f = f.decode() if isinstance(f, bytes) else f
        v = v.decode() if isinstance(v, bytes) else v
        name = f.rsplit(":", 1)[0]
        pipe.srem(f"called_by:{name}", def_key)
        try:
            rec = json.loads(v)
        except (json.JSONDecodeError, TypeError):
            rec = {}
        hist[f] = json.dumps({**rec, "removed": commit_hash})
        pipe.sadd(f"called_by_hist:{name}", def_key)
    if hist:
        pipe.hset(f"calls_hist:{def_key}", mapping=hist)
    pipe.delete(fwd_key)
    pipe.execute()


def drift_call_edges(
    redis: redis_lib.Store,
    old_def_key: str,
    new_def_key: str,
    line_delta: int,
) -> None:
    """Pure drift: rename address, shift call-site lines by delta,
    preserve every 'commit' value, repoint called_by memberships.
    Pure drift == body unchanged, so every body line (and therefore every
    call site) shifts by exactly the def-line delta — uniform shift is exact."""
    old_fwd, new_fwd = f"calls:{old_def_key}", f"calls:{new_def_key}"
    raw = redis.hgetall(old_fwd)
    if not raw:
        return
    pipe = redis.pipeline(transaction=False)
    shifted: dict[str, str] = {}
    for f, v in raw.items():
        f = f.decode() if isinstance(f, bytes) else f
        v = v.decode() if isinstance(v, bytes) else v
        name, line_s = f.rsplit(":", 1)
        try:
            shifted[f"{name}:{int(line_s) + line_delta}"] = v
        except ValueError:
            shifted[f] = v
        pipe.srem(f"called_by:{name}", old_def_key)
        pipe.sadd(f"called_by:{name}", new_def_key)
    pipe.delete(old_fwd)
    if shifted:
        pipe.hset(new_fwd, mapping=shifted)
    pipe.execute()


"""
Additions for skills_lib.py — reference (indirect-dispatch) edges.

A call edge answers "who calls X". A ref edge answers "whose address was
taken", which in C is where control actually goes: function-pointer tables,
designated initialisers, ifunc resolvers, weak aliases. Kept in a separate
namespace so `called_by:` does not silently change meaning for every query
that already exists.

    refs:<def_key>          HASH   field "<target>:<line>:<kind>" -> {snippet, commit}
    referenced_by:<target>  SET    def_keys that take <target>'s address
    commit_refs:<hash>      SET    immutable history of newly-created ref edges

Provenance rules mirror write_call_edges exactly: a surviving edge keeps its
original commit; a same-target edge at a changed line is a move and inherits;
only genuinely new edges are stamped and recorded.
"""

def write_ref_edges(redis, def_key, refs, commit_hash):
    """Diff-write a symbol's outgoing reference edges. Returns new-edge count."""
    fwd_key = f"refs:{def_key}"
    old_raw = redis.hgetall(fwd_key)
    old = {}
    for f, v in old_raw.items():
        f = f.decode() if isinstance(f, bytes) else f
        v = v.decode() if isinstance(v, bytes) else v
        try:
            old[f] = json.loads(v)
        except (json.JSONDecodeError, TypeError):
            continue

    def split_field(f):
        """"<target>:<line>:<kind>" -> (target, line, kind)"""
        parts = f.rsplit(":", 2)
        return (parts[0], parts[1], parts[2]) if len(parts) == 3 else (f, "0", "")

    old_by_target = {}
    for f, rec in old.items():
        target, _, kind = split_field(f)
        old_by_target.setdefault((target, kind), []).append((f, rec))

    new_fields, new_edges, matched_old = {}, [], set()

    for r in refs:
        target = r.get("name", "")
        kind = r.get("kind", "")
        try:
            line = int(r.get("line", 0))
        except (TypeError, ValueError):
            line = 0
        if not target:
            continue
        field = f"{target}:{line}:{kind}"
        if field in new_fields:
            continue
        exact = old.get(field)
        if exact is not None and field not in matched_old:
            new_fields[field] = json.dumps({
                "snippet": r.get("snippet", exact.get("snippet", "")),
                "commit": exact.get("commit", commit_hash),
            })
            matched_old.add(field)
            continue
        candidates = [(f, rec) for f, rec in old_by_target.get((target, kind), [])
                      if f not in matched_old]
        if candidates:
            f_old, rec = min(
                candidates,
                key=lambda t: abs(int(split_field(t[0])[1]) - line),
            )
            matched_old.add(f_old)
            new_fields[field] = json.dumps({
                "snippet": r.get("snippet", ""),
                "commit": rec.get("commit", commit_hash),
            })
            continue
        new_fields[field] = json.dumps({
            "snippet": r.get("snippet", ""),
            "commit": commit_hash,
        })
        new_edges.append({"referrer": def_key, "target": target,
                          "line": line, "kind": kind,
                          "snippet": r.get("snippet", "")})

    old_targets = {split_field(f)[0] for f in old}
    new_targets = {split_field(f)[0] for f in new_fields}

    pipe = redis.pipeline(transaction=False)
    erased = {f: rec for f, rec in old.items() if f not in matched_old}
    if erased and commit_hash:
        pipe.hset(f"refs_hist:{def_key}", mapping={
            f: json.dumps({**rec, "removed": commit_hash}) for f, rec in erased.items()
        })
        for f in erased:
            pipe.sadd(f"referenced_by_hist:{split_field(f)[0]}", def_key)
    pipe.delete(fwd_key)
    if new_fields:
        pipe.hset(fwd_key, mapping=new_fields)
    for t in new_targets - old_targets:
        pipe.sadd(f"referenced_by:{t}", def_key)
    for t in old_targets - new_targets:
        pipe.srem(f"referenced_by:{t}", def_key)
    if commit_hash:
        for e in new_edges:
            pipe.sadd(f"commit_refs:{commit_hash}", json.dumps(e))
    pipe.execute()
    return len(new_edges)


def clear_ref_edges(redis, def_key, commit_hash: str = ""):
    """Symbol deleted: move its outgoing ref edges to history.
    referenced_by:<its own name> is deliberately left intact — a non-empty
    set after obsoletion IS the 'obsoleted but still reachable by address'
    flag, which for a function-pointer target is a louder signal than the
    call-graph equivalent."""
    fwd_key = f"refs:{def_key}"
    raw = redis.hgetall(fwd_key)
    pipe = redis.pipeline(transaction=False)
    hist: dict[str, str] = {}
    for f, v in raw.items():
        f = f.decode() if isinstance(f, bytes) else f
        v = v.decode() if isinstance(v, bytes) else v
        parts = f.rsplit(":", 2)
        target = parts[0] if len(parts) == 3 else f
        pipe.srem(f"referenced_by:{target}", def_key)
        try:
            rec = json.loads(v)
        except (json.JSONDecodeError, TypeError):
            rec = {}
        hist[f] = json.dumps({**rec, "removed": commit_hash})
        pipe.sadd(f"referenced_by_hist:{target}", def_key)
    if hist:
        pipe.hset(f"refs_hist:{def_key}", mapping=hist)
    pipe.delete(fwd_key)
    pipe.execute()


def drift_ref_edges(redis, old_def_key, new_def_key, line_delta):
    """Pure drift: rename address, shift ref lines by delta, preserve every
    'commit' value, repoint referenced_by memberships."""
    old_fwd, new_fwd = f"refs:{old_def_key}", f"refs:{new_def_key}"
    raw = redis.hgetall(old_fwd)
    if not raw:
        return
    pipe = redis.pipeline(transaction=False)
    shifted = {}
    for f, v in raw.items():
        f = f.decode() if isinstance(f, bytes) else f
        v = v.decode() if isinstance(v, bytes) else v
        parts = f.rsplit(":", 2)
        if len(parts) == 3:
            target, line_s, kind = parts
            try:
                shifted[f"{target}:{int(line_s) + line_delta}:{kind}"] = v
            except ValueError:
                shifted[f] = v
        else:
            target = f
            shifted[f] = v
        pipe.srem(f"referenced_by:{target}", old_def_key)
        pipe.sadd(f"referenced_by:{target}", new_def_key)
    pipe.delete(old_fwd)
    if shifted:
        pipe.hset(new_fwd, mapping=shifted)
    pipe.execute()


def find_referrers(redis, target_name, include_hist: bool = False):
    """Inverse lookup for probes: which symbols take <target_name>'s address.
    Companion to find_callers_provenance. Returns [{def_key, kind, line,
    snippet, commit, removed?}]. include_hist adds edges since removed,
    each carrying the removing commit — callers window on it."""
    pairs = [(m, "refs") for m in redis.smembers(f"referenced_by:{target_name}")]
    if include_hist:
        pairs += [(m, "refs_hist")
                  for m in redis.smembers(f"referenced_by_hist:{target_name}")]
    out = []
    for m, prefix in pairs:
        dk = m.decode() if isinstance(m, bytes) else m
        for f, v in (redis.hgetall(f"{prefix}:{dk}") or {}).items():
            f = f.decode() if isinstance(f, bytes) else f
            v = v.decode() if isinstance(v, bytes) else v
            parts = f.rsplit(":", 2)
            if len(parts) != 3 or parts[0] != target_name:
                continue
            try:
                rec = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                rec = {}
            out.append({"def_key": dk, "kind": parts[2], "line": int(parts[1]),
                        "snippet": rec.get("snippet", ""),
                        "commit": rec.get("commit", ""),
                        "removed": rec.get("removed", "")})
    return out






def composite_centroid(
    redis: redis_lib.Store,
    redis_binary: redis_lib.Store,
    skill_id: str,
    code_prefix: str = "cvec_at",    # code store: read the newest version of each leaf
) -> Optional[bytes]:
    """L2-normalized mean of the LEAF atomic member vectors of a composite.
    Walks composes_skills to the bottom (cycle-safe); composites contribute
    nothing themselves — only their atomic leaves. None when no leaf has a
    stored vector."""
    import numpy as np
    leaves: set[str] = set()
    visited: set[str] = {skill_id}
    frontier = [skill_id]
    while frontier:
        vals = redis.mget([f"skill:{sid}" for sid in frontier])
        nxt = []
        for sid, raw in zip(frontier, vals):
            if not raw:
                continue
            sk = json.loads(raw)
            children = [c for c in sk.get("composes_skills", []) if c not in visited]
            if sk.get("is_composite", False) and children:
                visited.update(children)
                nxt.extend(children)
            elif not sk.get("is_composite", False):
                leaves.add(sid)
        frontier = nxt
    if not leaves:
        return None
    vecs = []
    leaf_ids = sorted(leaves)
    found = code_mean_vectors(redis_binary, code_prefix, leaf_ids)
    for v in found:
        if v:
            vecs.append(np.frombuffer(v, dtype=np.float32))
    if not vecs:
        return None
    mean = np.mean(vecs, axis=0)
    norm = np.linalg.norm(mean)
    if norm < 1e-9:
        return None
    return (mean / norm).astype(np.float32).tobytes()

def store_code(redis: redis_lib.Store, def_key: str, code_body: str,
               commit_hash: str = "", chunks: Optional[list] = None) -> None:
    """
    Persist a symbol's full code body to code:<def_key> as a HASH.
    The code_search FT index is declared over this prefix, so writing
    the hash IS the index update — single source of truth, no sync problem.

    When commit_hash is given, ALSO persist an immutable per-commit copy at
    code_at:<commit>:<def_key> — the time-travel body store. ('code_at:'
    does not match the FT 'code:' prefix, so it never pollutes grep.)
    """
    if not def_key or not code_body:
        return
    parsed = parse_def_key(def_key)
    if not parsed:
        return
    fp, sym, line, st = parsed
    # chunks=None: the caller does not know the ranges, the saved field is
    # left as it is. A list (also an empty one) is saved, so the second-pass
    # embed script cuts the body the same way the ingester did.
    extra = {} if chunks is None else {"chunks": json.dumps(chunks)}
    try:
        redis.hset(f"code:{def_key}", mapping={
            "def_key":     def_key,
            "file":        fp,
            "symbol":      sym,
            "struct_type": st,
            "line":        line,
            "body":        code_body,
            **extra,
        })
        if commit_hash:
            redis.hset(f"code_at:{commit_hash}:{def_key}", mapping={
                "def_key": def_key,
                "body":    code_body,
                **extra,
            })
    except Exception as e:
        print(f"⚠️  Failed to store code for {def_key}: {e}")


def get_code(redis: redis_lib.Store, def_key: str) -> str:
    """Single read path for code bodies. All readers go through this.
    Falls back to code_hist: — a targeted read by def_key that misses
    code: is by construction a historical read (obsoleted symbol)."""
    if not def_key:
        return ""
    val = redis.hget(f"code:{def_key}", "body")
    if val is None:
        val = redis.hget(f"code_hist:{def_key}", "body")
    if isinstance(val, bytes):
        val = val.decode()
    return val or ""


def get_code_as_of(redis: redis_lib.Store, def_key: str, commit_hash: str = "") -> str:
    """Time-travel body read: exact per-commit copy first, then the live/hist
    chain. The fallback body may reflect a later revision — callers badge it."""
    if not def_key:
        return ""
    if commit_hash:
        val = redis.hget(f"code_at:{commit_hash}:{def_key}", "body")
        if val is not None:
            return val.decode() if isinstance(val, bytes) else val
    return get_code(redis, def_key)


def get_skill_as_of(redis: redis_lib.Store, skill_id: str,
                    to_rank: int) -> Optional[dict]:
    """Reconstruct a skill's state as of commit rank <= to_rank.

    Current record wins if its last-touch commit is in range. Otherwise walk
    skill_history newest→oldest (entries snapshot each superseded state WITH
    the commit_hash of that state) and take the newest in-range snapshot.
    Unknown/empty commit hashes are treated as in-range (pre-tracking data).
    Reconstructed dicts carry _as_of_reconstructed=True and the snapshot's
    commit_hash, so callers can fetch the matching body via get_code_as_of.
    """
    raw = redis.get(f"skill:{skill_id}")
    if not raw:
        return None
    skill = json.loads(raw if isinstance(raw, str) else raw.decode())
    if skill.get("isObsolete", False):
        oc = skill.get("obsoleted_commit") or ""
        obr = redis.zrank("commit_order", oc) if oc else None
        if obr is not None and int(obr) <= to_rank:
            # Symbol did NOT exist at to_rank. Stamped, not hidden: history
            # reads stay possible, but no caller can mistake this for live
            # state at the probed commit.
            skill["_removed_at"] = oc
    cur_hash = skill.get("commit_hash", "")
    cur_rank = redis.zrank("commit_order", cur_hash) if cur_hash else None
    if cur_rank is None or cur_rank <= to_rank:
        return skill

    entries = redis.lrange(f"skill_history:{skill_id}", 0, -1)
    best = None
    for raw_e in reversed(entries):          # newest snapshot first
        try:
            e = json.loads(raw_e if isinstance(raw_e, str) else raw_e.decode())
        except (json.JSONDecodeError, TypeError):
            continue
        h = e.get("commit_hash", "")
        r = redis.zrank("commit_order", h) if h else None
        if r is None or r <= to_rank:
            best = e
            break
    if best is None:
        # Membership filtering should prevent this; fall back honestly.
        skill["_as_of_reconstructed"] = False
        skill["_as_of_warning"] = "no in-range snapshot found — record is post-range"
        return skill

    out = dict(skill)
    out["description_of_skill"] = best.get("description",
                                           out.get("description_of_skill", ""))
    out["def_key"]         = best.get("def_key", out.get("def_key", ""))
    out["composes_skills"] = best.get("composes_skills",
                                      out.get("composes_skills", []))
    out["commit_hash"]     = best.get("commit_hash", "")
    out["_as_of_reconstructed"] = True
    return out


def rename_code(redis: redis_lib.Store, old_def_key: str, new_def_key: str,
                commit_hash: str = "") -> None:
    """Drift: same body, new address. RENAME keeps the doc indexed
    (prefix unchanged); metadata fields must be patched to the new address.

    commit_hash = the drifted skill's CURRENT commit (its latest version).
    When given, the per-commit body copy is duplicated to the new address —
    COPY, not RENAME, because pre-drift history entries still reference the
    old (commit, def_key) pair and must keep resolving. Without this, the
    post-drift history snapshot (commit_hash unchanged, def_key updated)
    points at code_at:<commit>:<new> which was never written, and the next
    real edit's diff loses its previous-version body."""
    try:
        redis.rename(f"code:{old_def_key}", f"code:{new_def_key}")
    except KeyError:
        return  # old key never stored
    parsed = parse_def_key(new_def_key)
    if parsed:
        fp, sym, line, st = parsed
        redis.hset(f"code:{new_def_key}", mapping={
            "def_key": new_def_key, "file": fp, "symbol": sym,
            "struct_type": st, "line": line,
        })
    if commit_hash:
        old_at, new_at = (f"code_at:{commit_hash}:{old_def_key}",
                          f"code_at:{commit_hash}:{new_def_key}")
        try:
            copied = redis.copy(old_at, new_at, replace=True)
        except (KeyError, AttributeError):
            copied = False   # COPY needs Redis 6.2+ / recent client — fall through
        if not copied:
            body = redis.hget(old_at, "body")
            if body is not None:
                redis.hset(new_at, mapping={"def_key": new_def_key, "body": body})
        # Address field on the new copy must match its key either way
        if redis.exists(new_at):
            redis.hset(new_at, "def_key", new_def_key)


# ── Code FT index ─────────────────────────────────────────────────────────────

CODE_FT_INDEX = "code_search"

def ensure_code_index(redis: redis_lib.Store) -> bool:
    """The store indexes every body as it is written (FTS5 trigram)."""
    return True


CODE_HIST_FT_INDEX = "code_hist_search"

def ensure_code_hist_index(redis: redis_lib.Store) -> bool:
    return True


CODE_AT_FT_INDEX = "code_at_search"

def _code_at_index_ready(redis: redis_lib.Store) -> bool:
    """The store's index is written with the body: always complete."""
    return True

def ensure_code_at_index(redis: redis_lib.Store) -> bool:
    return True


# ── Two-stage grep: FT prefilter (recall-sound) → Python verify (exact) ──────

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")

_INDEX_PREFIX = {"code_search": "code:", "code_hist_search": "code_hist:",
                 "code_at_search": "code_at:"}


def _build_prefilter_query(pattern: str, is_regex: bool,
                           struct_types: Optional[tuple[str, ...]]) -> Optional[dict]:
    """
    Recall-sound prefilter: every true match contains every alphanumeric
    run of the pattern as a substring (case-folded); Python verify removes
    false positives. Returns None only when the pattern contains no
    alphanumeric run (nothing to filter on).
    """
    if not is_regex:
        tokens = _TOKEN_RE.findall(pattern)
    else:
        cleaned = re.sub(r"\\[dDwWsSbBAZ]|\\.|\[[^\]]*\]|\{[^}]*\}", " ", pattern)
        cleaned = re.sub(r"[|^$.*+?()]", " ", cleaned)
        tokens = _TOKEN_RE.findall(cleaned)
    if not tokens:
        return None
    return {"tokens": [t.lower() for t in tokens],
            "struct_types": tuple(struct_types) if struct_types else None}


def _iter_ft_keys(redis: redis_lib.Store, query: dict, index: str,
                  batch: int = 2000):
    """The keys of every body that may match (every token present)."""
    for key in redis.grep_keys(query["tokens"], _INDEX_PREFIX[index]):
        yield key


def _iter_ft_candidates(redis: redis_lib.Store, query: dict, batch: int = 500,
                        index: str = CODE_FT_INDEX, with_key: bool = False):
    """Every candidate record (def_key, file, symbol, struct_type, line,
    body), filtered by struct type when the query asks for it."""
    wanted = query.get("struct_types")
    for key in _iter_ft_keys(redis, query, index):
        h = redis.hgetall(key)
        d = {(k.decode() if isinstance(k, bytes) else k):
             (v.decode() if isinstance(v, bytes) else v) for k, v in h.items()}
        if wanted and d.get("struct_type") not in wanted:
            continue
        if with_key:
            d["__key"] = key
        yield d


def _rank_of(redis: redis_lib.Store, commit: str, cache: dict) -> Optional[int]:
    """Memoised zrank on commit_order. None = unknown/unindexed commit."""
    if not commit:
        return None
    if commit not in cache:
        r = redis.zrank("commit_order", commit)
        cache[commit] = int(r) if r is not None else None
    return cache[commit]

_MOVED_MAX_HOPS = 512

def _same_position_sids(redis, def_key):
    """Skill ids recorded at ANY address sharing this def_key's
    (file, symbol). code_at: def_keys carry line numbers frozen at write
    time; after later drifts the exact address resolves to no symbol
    record even though the position has full history. Both window checks
    failed open on that miss — this closes it."""
    p = parse_def_key(def_key)
    if not p:
        return []
    fp, sym = p[0], p[1]
    keys = (redis.smembers(f"symbol_name:{sym}") or set()) \
         | (redis.smembers(f"symbol_name_hist:{sym}") or set())
    out = []
    for k in keys:
        k = k.decode() if isinstance(k, bytes) else k
        pk = parse_symbol_key(k)
        if not pk or pk[0] != fp:
            continue
        alt = f"{pk[0]}:{pk[1]}:{pk[2]}:{pk[3]}"
        if alt == def_key:
            continue
        for lk in (f"symbol:{alt}", f"symbol_hist:{alt}"):
            for s in redis.lrange(lk, 0, -1) or []:
                out.append(s.decode() if isinstance(s, bytes) else s)
    return list(dict.fromkeys(out))

def _chase_moved(redis, def_key):
    """Follow moved_from: pointers to the address a drifted symbol lives at
    now. One pointer is written per drift, so chains are as long as the
    symbol's drift history; the walk is path-compressed, so after the first
    chase every address on the path resolves in a single hop. Cycle-safe.
    Returns def_key unchanged when nothing forwards from it."""
    hop, path, seen = def_key, [], set()
    while hop not in seen and len(path) < _MOVED_MAX_HOPS:
        seen.add(hop)
        nxt = redis.get(f"moved_from:{hop}")
        if not nxt:
            break
        path.append(hop)
        hop = nxt.decode() if isinstance(nxt, bytes) else nxt
    if len(path) > 1:
        pipe = redis.pipeline(transaction=False)
        for p in path[:-1]:
            pipe.set(f"moved_from:{p}", hop)
        pipe.execute()
    return hop


def _newest_version_rank(redis, def_key, to_rank, rank_cache):
    """Newest stored-version rank <= to_rank in the version chain of the
    skill(s) at this position (skill_history snapshots + current record).
    None when unresolvable (pre-tracking data) — callers keep the hit."""
    pipe = redis.pipeline(transaction=False)
    pipe.lrange(f"symbol:{def_key}", 0, -1)
    pipe.lrange(f"symbol_hist:{def_key}", 0, -1)
    prim, fall = pipe.execute()
    sids = [s.decode() if isinstance(s, bytes) else s
            for s in list(prim or []) + list(fall or [])]
    if not sids:
        moved = _chase_moved(redis, def_key)
        if moved != def_key:
            return _newest_version_rank(redis, moved, to_rank, rank_cache)
        # Drifted historical address with no pointer: resolve by
        # (file, symbol) so supersession is checked against the position's
        # real version chain instead of failing open to "keep".
        sids = _same_position_sids(redis, def_key)
    best = None
    for sid in dict.fromkeys(reversed(sids)):
        raw = redis.get(f"skill:{sid}")
        if not raw:
            continue
        sk = json.loads(raw if isinstance(raw, str) else raw.decode())
        hashes = [sk.get("commit_hash") or ""]
        for raw_e in redis.lrange(f"skill_history:{sid}", 0, -1):
            try:
                e = json.loads(raw_e if isinstance(raw_e, str) else raw_e.decode())
            except (json.JSONDecodeError, TypeError):
                continue
            hashes.append(e.get("commit_hash") or "")
        for h in hashes:
            r = _rank_of(redis, h, rank_cache)
            if r is not None and r <= to_rank and (best is None or r > best):
                best = r
    return best


def _grep_window_resolve(redis, def_key, is_hist, as_of, rank_cache):
    """Membership check for one grep hit — same rank arithmetic as the
    semantic-search window filter. def_key → skill(s) via the symbol index
    (hist rows prefer symbol_hist:), newest first.

    Returns (keep, cur_rank, removed_by_probed):
      keep     — False only on POSITIVE evidence of out-of-range: every
                 resolvable skill at this position was created after to_rank
                 or obsoleted BEFORE to_rank. Unknown provenance → True.
      cur_rank — the vouching skill's current commit rank (None if unknown);
                 cur_rank > to_rank means the row's body may be post-range.
      removed_by_probed — True when the vouching skill was obsoleted at
                 EXACTLY to_rank: removed by the probed commit itself. The
                 pre-removal body is evidence of that commit's deletion, so
                 the hit is kept and badged instead of dropped.
    """
    primary  = f"symbol_hist:{def_key}" if is_hist else f"symbol:{def_key}"
    fallback = f"symbol:{def_key}" if is_hist else f"symbol_hist:{def_key}"
    pipe = redis.pipeline(transaction=False)
    pipe.lrange(primary, 0, -1)
    pipe.lrange(fallback, 0, -1)
    prim, fall = pipe.execute()
    sids = [s.decode() if isinstance(s, bytes) else s for s in (prim or [])]
    if not sids:
        sids = [s.decode() if isinstance(s, bytes) else s for s in (fall or [])]
    if not sids:
        # Drifted address — chase forwarding pointers to the current key.
        moved = _chase_moved(redis, def_key)
        if moved != def_key:
            return _grep_window_resolve(redis, moved, is_hist, as_of, rank_cache)
        # Line-drift hole: exact address has no records. Resolve by
        # (file, symbol) via the shared helper; the sids feed the same
        # membership loop below — no recursion needed.
        sids = _same_position_sids(redis, def_key)
        if not sids:
            return True, None, False       # genuinely no record — unwindowable
    sids = list(dict.fromkeys(reversed(sids)))   # newest first, deduped
    values = redis.mget([f"skill:{sid}" for sid in sids])
    saw_skill = False
    for sid, raw in zip(sids, values):
        if not raw:
            continue
        saw_skill = True
        sk = json.loads(raw if isinstance(raw, str) else raw.decode())
        cr  = _rank_of(redis, sk.get("created_commit") or "", rank_cache)
        obr = _rank_of(redis, sk.get("obsoleted_commit") or "", rank_cache)
        if cr is not None and cr > as_of["to_rank"]:
            continue                       # created after the probed commit
        if obr is not None and obr < as_of["to_rank"]:
            continue                       # obsoleted BEFORE the probed
                                           # commit — did not exist in the
                                           # target state. from_rank is a
                                           # range-activity bound, never a
                                           # liveness bound.
        if obr is not None and obr == as_of["to_rank"]:
            # Removed by the probed commit itself: the deletion is part of
            # the change under judgment — keep the hit, badged.
            return (True,
                    _rank_of(redis, sk.get("commit_hash") or "", rank_cache),
                    True)
        return (True,
                _rank_of(redis, sk.get("commit_hash") or "", rank_cache),
                False)
    return (not saw_skill), None, False    # skills seen, all out-of-range → drop


def grep_code_ft(
    redis: redis_lib.Store,
    *,
    pattern: str,
    is_regex: bool = False,
    file: Optional[str] = None,
    struct_types: Optional[tuple[str, ...]] = None,
    max_results: int = 30,
    exact_total: bool = False,     # True → verify the full candidate stream
    overshoot_factor: int = 4,     # verify past max_results to sharpen the bound
    include_hist: bool = False,    # also scan code_hist: (obsoleted bodies)
    as_of: Optional[dict] = None,  # {"from_rank": int, "to_rank": int}
    rank_cache: Optional[dict] = None,  # commit → rank, shared between greps
) -> Optional[dict]:
    """
    Returns None when unfilterable (caller falls back to Neo4j), else:
      {'rows': [...verified matches, up to max_results...],
       'total_matched': int,
       'total_is_exact': bool,    # False → total_matched is a LOWER BOUND
       'candidates_scanned': int,
       'window_dropped': int}     # matches hidden by the as_of window

    as_of windowing: primary pass greps the code_at: per-commit body store —
    per (file, symbol) the winner is the newest matching version with
    rank <= to_rank, i.e. the body live at the window's upper bound. The
    live/hist scans then skip covered symbols and act as fallback for
    pre-code_at data, with membership filtering (created after to_rank /
    obsoleted at or before to_rank → dropped) and a post_range_body badge when
    a surviving live row's last-touch commit postdates the window.
    """
    query = _build_prefilter_query(pattern, is_regex, struct_types)
    if query is None:
        return None

    rx = re.compile(pattern) if is_regex else None
    file_suffix = file.lstrip("./") if file else None

    rows, matched, scanned = [], 0, 0
    stop_after = None if exact_total else max_results * overshoot_factor

    rank_cache = {} if rank_cache is None else rank_cache
    window_cache: dict = {}       # (def_key, is_hist) → (keep, cur_rank)
    window_dropped = 0
    covered: set[tuple] = set()   # (file, symbol) answered by the code_at pass

    # ── Windowed primary pass: the per-commit body store ────────────────
    code_at_partial = False
    code_at_capped = False
    if as_of is not None and ensure_code_at_index(redis):
        code_at_partial = not _code_at_index_ready(redis)
        query_at = _build_prefilter_query(pattern, is_regex, None)
        # All commit ranks in ONE read, instead of one lookup per commit.
        if "__loaded__" not in rank_cache:
            for i, h in enumerate(redis.zrange("commit_order", 0, -1)):
                rank_cache[h.decode() if isinstance(h, bytes) else h] = i
            rank_cache["__loaded__"] = True
        # Step 1 — keys only. The commit and the address are in the key, so
        # versions are ordered without loading a body. Per address, only its
        # newest in-window version can be the state at the probed commit.
        newest: dict[tuple, dict] = {}   # (file, symbol) → {def_key: version}
        try:
            for key in _iter_ft_keys(redis, query_at, CODE_AT_FT_INDEX):
                scanned += 1
                if not key.startswith("code_at:"):
                    continue
                commit, _, dk = key[len("code_at:"):].partition(":")
                r = _rank_of(redis, commit, rank_cache)
                if r is None or r > as_of["to_rank"]:
                    continue
                p = parse_def_key(dk)
                if not p:
                    continue
                fp, sym, line, st = p
                if file_suffix and not fp.endswith(file_suffix):
                    continue
                if struct_types and st not in struct_types:
                    continue
                per_addr = newest.setdefault((fp, sym), {})
                prev = per_addr.get(dk)
                if prev is None or r > prev["rank"]:
                    per_addr[dk] = {"rank": r, "commit": commit, "def_key": dk,
                                    "file": fp, "symbol": sym,
                                    "struct_type": st, "line": str(line)}
        except Exception:
            newest = {}    # query rejected — fall back
        # Step 2 — per symbol, newest address first: load ONE body, verify.
        for k in sorted(newest):
            if stop_after and matched >= stop_after:
                code_at_capped = True      # enough matches: stop reading
                break
            w = None
            for cand in sorted(newest[k].values(), key=lambda v: -v["rank"]):
                body = redis.hget(
                    f"code_at:{cand['commit']}:{cand['def_key']}", "body")
                if isinstance(body, bytes):
                    body = body.decode()
                body = body or ""
                if rx.search(body) if rx else (pattern in body):
                    w = {**cand, "body": body}
                    break
            if w is None:
                covered.add(k)   # state at the probed commit does not match
                continue
            keep, _cur, _removed = _grep_window_resolve(
                redis, w["def_key"], False, as_of, rank_cache)
            if not keep:
                window_dropped += 1
                continue
            # Superseded-winner check: the FT stream only contains versions
            # that MATCH the pattern, so the newest matching version can be
            # older than the newest stored version at to_rank. If a newer
            # in-window version exists, the pattern was removed before the
            # probed commit — this hit is history, not target state.
            r_state = _newest_version_rank(
                redis, w["def_key"], as_of["to_rank"], rank_cache)
            if r_state is not None and r_state > w["rank"]:
                window_dropped += 1
                covered.add(k)   # position is answered: state doesn't match
                continue
            covered.add(k)
            matched += 1
            if len(rows) < max_results:
                row = {"def_key": w["def_key"], "file": w["file"],
                       "symbol": w["symbol"], "struct_type": w["struct_type"],
                       "line": w["line"], "body": w["body"],
                       "as_of_commit": w["commit"][:12]}
                if w["rank"] < as_of["from_rank"]:
                    row["pre_range_version"] = True
                # True when the version chain confirmed that no newer
                # version existed at the probed commit.
                row["state_verified"] = r_state is not None
                if _removed:
                    row["removed_by_probed"] = True
                rows.append(row)

    def _admit(d: dict, is_hist: bool) -> bool:
        """Window gate for live/hist fallback rows."""
        nonlocal window_dropped
        if as_of is None:
            return True
        dk = d.get("def_key", "")
        ck = (dk, is_hist)
        if ck not in window_cache:
            window_cache[ck] = _grep_window_resolve(
                redis, dk, is_hist, as_of, rank_cache)
        keep, cur, removed = window_cache[ck]
        if not keep:
            window_dropped += 1
            return False
        if removed:
            d["removed_by_probed"] = True  # deleted by the probed commit —
                                           # body is parent-commit state
        if cur is not None and cur > as_of["to_rank"]:
            d["post_range_body"] = True    # no code_at copy — body may be newer than B
        elif cur is None:
            d["provenance_unresolved"] = True   # kept fail-open — flag it
        return True

    # ── Live corpus ──────────────────────────────────────────────────────
    for d in ([] if code_at_capped else _iter_ft_candidates(redis, query)):
        scanned += 1
        if file_suffix and not d.get("file", "").endswith(file_suffix):
            continue
        if as_of is not None and (d.get("file"), d.get("symbol")) in covered:
            continue
        body = d.get("body", "")
        if rx.search(body) if rx else (pattern in body):
            if not _admit(d, is_hist=False):
                continue
            matched += 1
            if len(rows) < max_results:
                rows.append(d)
        if stop_after and matched >= stop_after:
            break

    # ── Hist corpus (obsoleted bodies) ───────────────────────────────────
    if include_hist and (stop_after is None or matched < stop_after):
        try:
            for d in _iter_ft_candidates(redis, query, index=CODE_HIST_FT_INDEX):
                scanned += 1
                if file_suffix and not d.get("file", "").endswith(file_suffix):
                    continue
                if as_of is not None and (d.get("file"), d.get("symbol")) in covered:
                    continue
                body = d.get("body", "")
                if rx.search(body) if rx else (pattern in body):
                    if not _admit(d, is_hist=True):
                        continue
                    matched += 1
                    if len(rows) < max_results:
                        d["obsolete"] = True
                        rows.append(d)
                if stop_after and matched >= stop_after:
                    break
        except Exception:
            pass  # hist index not created on this org yet

    exhausted = (stop_after is None) or (matched < stop_after)
    return {
        "rows": rows,
        "total_matched": matched,
        "total_is_exact": exhausted,
        "candidates_scanned": scanned,
        "window_dropped": window_dropped,
        "code_at_partial": code_at_partial,
    }





def mark_composites_stale(
    redis: redis_lib.Store,
    changed_skill_id: str,
) -> int:
    """
    Mark all composites that include this skill (directly or transitively)
    as stale by walking the composite_uses inverse index.
    
    Works uniformly for atomic OR composite changed_skill_id inputs:
    - Atomic skill changed → direct parents marked, then their parents, etc.
    - Composite skill changed → its direct parents marked, and so on upward.
    
    Cycle-safe via visited set. Terminates naturally when no new ancestors
    are discovered.
    """
    visited: set[str] = {changed_skill_id}
    current_layer: set[str] = {changed_skill_id}
    marked = 0
    
    while True:
        # ── Gather direct parents of everything in current layer ─────────
        pipe = redis.pipeline(transaction=False)
        for sid in current_layer:
            pipe.smembers(f"composite_uses:{sid}")
        layer_results = pipe.execute()

        next_layer: set[str] = set()
        for parents_raw in layer_results:
            parents = {
                p.decode() if isinstance(p, bytes) else p
                for p in parents_raw
            }
            new_parents = parents - visited
            next_layer.update(new_parents)
            visited.update(new_parents)
        
        if not next_layer:
            break
        
        # ── Batch-fetch parents and mark stale ───────────────────────────
        parent_list = list(next_layer)
        keys        = [f"skill:{cid}" for cid in parent_list]
        values      = redis.mget(keys)
        
        for cid, key, val in zip(parent_list, keys, values):
            if not val:
                continue
            skill = json.loads(val)
            if skill.get("isObsolete", False):
                continue
            if not skill.get("is_composite", False):
                continue
            if skill.get("needs_update", False):
                continue
            
            skill["needs_update"] = True
            redis.set(key, json.dumps(skill))
            redis.sadd("stale_composites", cid)
            marked += 1
        
        current_layer = next_layer
    
    return marked



# ──────────────────────────────────────────────────────────────────────────────
# Hot-path operations
# ──────────────────────────────────────────────────────────────────────────────

def save_skill(
    redis: redis_lib.Store,
    redis_binary: redis_lib.Store,
    *,
    goal: str,
    vifs: list[str],
    description: str = "",
    def_key: str = "",
    code_body: str = "",
    commit_hash: str = "",
    suggested: bool = False,
    composes_skills: Optional[list[str]] = None,
    chunks: Optional[list] = None,      # ingester line ranges over code_body
    embedders: Optional[list] = None,   # CodeEmbedder list; empty = off
    code_vectors: Optional[dict] = None,  # {store name: [vectors]} (batch flow)
) -> str:
    """Save a new skill. Returns skill_id."""
    composes_skills = composes_skills or []
    goal_hash       = save_goal(redis, goal)
    raw_id          = uuid.uuid4().hex[:12]
    skill_id        = f"~{raw_id}" if suggested else raw_id
    is_composite    = bool(composes_skills)
    stored_vifs     = vifs if (is_composite or suggested) else []

    redis.set(f"skill:{skill_id}", json.dumps({
        "goal_ref":             goal_hash,
        "vifs":                 stored_vifs,
        "composes_skills":      composes_skills,
        "def_key":              def_key,
        "description_of_skill": description,
        "commit_hash":          commit_hash,
        "created_commit":       commit_hash,   # immutable — never overwritten
        "is_composite":         is_composite,
        "created_at":           datetime.now().isoformat(),
    }))

    if def_key and code_body:
        store_code(redis, def_key, code_body, commit_hash=commit_hash)

    redis.sadd("skills_active", skill_id)
    if is_composite:
        redis.sadd("composites", skill_id)

    if suggested:
        for name in vifs:
            existing = redis.get(f"blueprint:{name}")
            skills   = json.loads(existing) if existing else []
            if skill_id not in skills:
                skills.append(skill_id)
            redis.set(f"blueprint:{name}", json.dumps(skills))

    if composes_skills:
        for atomic_id in composes_skills:
            redis.sadd(f"composite_uses:{atomic_id}", skill_id)

    by_store = dict(code_vectors or {})
    if def_key and code_body:
        for emb in (embedders or []):
            if emb.name in by_store:
                continue
            try:
                by_store[emb.name] = emb.embed(
                    chunk_texts(def_key, code_body, chunks), "document")
            except Exception as e:
                print(f"⚠️  Code embed [{emb.name}] failed for {skill_id}: {e}")
    for name, vs in by_store.items():
        if vs:
            store_code_vectors(redis_binary, skill_id, def_key, vs,
                               prefix=CODE_EMBED_SPECS[name]["prefix"],
                               commit_hash=commit_hash)

    record_commit_event(redis, commit_hash, "new", skill_id)

    return skill_id


def save_skills_batch(
    redis: redis_lib.Store,
    redis_binary: redis_lib.Store,
    skills: list[dict],
    embedders: Optional[list] = None,
) -> list[str]:
    """
    Save N skills with, per code store, ONE batched call over every
    skill's chunk texts. Each dict is the kwargs save_skill takes (minus
    code_vectors).
    """
    if not skills:
        return []

    # Code vectors: flatten every skill's chunk texts once, embed per
    # store, split back. A failing store leaves that store's dict entry
    # absent; save_skill then retries it per skill.
    per_skill: list[dict] = [{} for _ in skills]
    if embedders:
        texts, owners = [], []
        for i, s in enumerate(skills):
            if s.get("def_key") and s.get("code_body"):
                ct = chunk_texts(s["def_key"], s["code_body"], s.get("chunks"))
                texts.extend(ct)
                owners.extend([i] * len(ct))
        for emb in embedders:
            try:
                vecs = emb.embed(texts, "document") if texts else []
                for i, v in zip(owners, vecs):
                    per_skill[i].setdefault(emb.name, []).append(v)
            except Exception as e:
                print(f"⚠️  Batch code embed [{emb.name}] failed "
                      f"({len(texts)} texts): {e}")

    skill_ids = []
    for skill_args, cv in zip(skills, per_skill):
        args = {k: v for k, v in skill_args.items() if k != "chunks"}
        sid = save_skill(redis, redis_binary, **args,
                         chunks=skill_args.get("chunks"),
                         embedders=embedders, code_vectors=cv)
        skill_ids.append(sid)
    return skill_ids




def obsolete_skill(
    redis: redis_lib.Store,
    redis_binary: redis_lib.Store,
    *,
    skill_id: str,
    reason: str = "Symbol deleted from codebase",
    commit_hash: str = "",
    record_event: bool = True,
) -> dict:
    skill_json = redis.get(f"skill:{skill_id}")
    if not skill_json:
        return {"success": False, "stale_composites": 0,
                "message": f"Skill '{skill_id}' not found"}

    skill = json.loads(skill_json)
    skill["isObsolete"]       = True
    skill["obsoleted_at"]     = datetime.now().isoformat()
    skill["obsoleted_commit"] = commit_hash   # immutable — rank axis for windows
    skill["obsolete_reason"]  = reason
    redis.set(f"skill:{skill_id}", json.dumps(skill))

    redis.srem("skills_active", skill_id)
    redis.sadd("skills_obsolete", skill_id)
    if skill.get("is_composite", False):
        redis.srem("composites", skill_id)

    def_key = skill.get("def_key", "")
    if def_key:
        # Historical index: probes on past commits resolve symbol→skill
        # through these after the live entries are pruned below.
        parsed_dk = parse_def_key(def_key)
        redis.lrem(f"symbol_hist:{def_key}", 0, skill_id)   # idempotent re-obsoletion
        redis.rpush(f"symbol_hist:{def_key}", skill_id)
        if parsed_dk:
            redis.sadd(f"symbol_name_hist:{parsed_dk[1]}", f"symbol:{def_key}")

        sym_key = f"symbol:{def_key}"
        if redis.exists(sym_key):
            redis.lrem(sym_key, 0, skill_id)
            if redis.llen(sym_key) == 0:
                redis.delete(sym_key)
                parsed = parse_symbol_key(sym_key)
                if parsed:
                    fp, sym, _, _ = parsed
                    redis.srem(f"file_symbols:{fp}", sym_key)
                    redis.srem(f"symbol_name:{sym}", sym_key)
        # Symbol position fully dead (index entry gone or never existed)
        # → its outgoing call edges leave current state. called_by:<name>
        # survives — that's the obsoleted-but-still-called flag.
        if not redis.exists(sym_key):
            clear_call_edges(redis, def_key, commit_hash=commit_hash)
            clear_ref_edges(redis, def_key, commit_hash=commit_hash)
            # Move body out of the grep index (an obsoleted symbol matching
            # greps corrupts investigation results) but keep it for
            # provenance under a non-indexed prefix.
            try:
                redis.rename(f"code:{def_key}", f"code_hist:{def_key}")
            except KeyError:
                pass  # no code stored at this position

    flag_code_vectors_obsolete(redis_binary, skill_id, commit_hash=commit_hash)

    composes = skill.get("composes_skills", [])
    if composes:
        for atomic_id in composes:
            redis.srem(f"composite_uses:{atomic_id}", skill_id)
            # Historical membership: upward walks with include_obsolete
            # still find this composite from its components.
            redis.sadd(f"composite_uses_hist:{atomic_id}", skill_id)
        redis.srem("stale_composites", skill_id)

    stale_count = mark_composites_stale(redis, skill_id)

    if not composes:
        redis.delete(f"composite_uses:{skill_id}")

    if record_event:
        record_commit_event(redis, commit_hash, "obsoleted", skill_id)

    return {
        "success":          True,
        "stale_composites": stale_count,
        "message":          f"Skill '{skill_id}' obsoleted",
    }



def update_skill_full(
    redis: redis_lib.Store,
    redis_binary: redis_lib.Store,
    *,
    skill_id: str,
    new_description: str = "",
    new_def_key: str = "",
    new_code_body: str = "",
    commit_hash: str = "",
    new_composes_skills: Optional[list[str]] = None,
    propagate_stale: bool = True,
    record_event: bool = True,
    chunks: Optional[list] = None,
    embedders: Optional[list] = None,
    code_vectors: Optional[dict] = None,  # {store name: [vectors]} (batch flow)
) -> dict:
    skill_json = redis.get(f"skill:{skill_id}")
    if not skill_json:
        return {"success": False, "stale_composites": 0,
                "message": f"Skill '{skill_id}' not found"}

    skill = json.loads(skill_json)
    if skill.get("isObsolete", False):
        return {"success": False, "stale_composites": 0,
                "message": f"Skill '{skill_id}' is obsolete — refusing update"}

    # Full audit trail in a side LIST — keeps skill JSON thin on hot paths.
    # One-time migration: move any embedded history entries out first.
    embedded = skill.pop("history", [])
    if embedded:
        redis.rpush(f"skill_history:{skill_id}",
                    *[json.dumps(h) for h in embedded])
    redis.rpush(f"skill_history:{skill_id}", json.dumps({
        "description":     skill.get("description_of_skill", ""),
        "def_key":         skill.get("def_key", ""),
        "composes_skills": skill.get("composes_skills", []),
        "commit_hash":     skill.get("commit_hash", ""),
        "updated_at":      skill.get("updated_at", skill.get("created_at", "")),
    }))
    skill["history_count"] = redis.llen(f"skill_history:{skill_id}")

    if new_composes_skills is not None:
        old_set = set(skill.get("composes_skills", []))
        new_set = set(new_composes_skills)
        for atomic_id in (old_set - new_set):
            redis.srem(f"composite_uses:{atomic_id}", skill_id)
            # Pruned membership survives for historical walks, both directions.
            redis.sadd(f"composite_uses_hist:{atomic_id}", skill_id)
            redis.sadd(f"composes_hist:{skill_id}", atomic_id)
        for atomic_id in (new_set - old_set):
            redis.sadd(f"composite_uses:{atomic_id}", skill_id)
        skill["composes_skills"] = list(new_composes_skills)
        if skill.get("is_composite", False):
            symbols: list[str] = []
            if new_composes_skills:
                for v in redis.mget([f"skill:{cid}" for cid in new_composes_skills]):
                    if not v:
                        continue
                    comp = json.loads(v)
                    if comp.get("isObsolete", False):
                        continue
                    symbols.extend(skill_symbols(comp))
            skill["vifs"] = list(dict.fromkeys(symbols))

    skill["description_of_skill"] = new_description
    skill["updated_at"]           = datetime.now().isoformat()
    if new_def_key:
        skill["def_key"] = new_def_key
    if commit_hash:
        skill["commit_hash"] = commit_hash
    skill["needs_update"] = False
    redis.set(f"skill:{skill_id}", json.dumps(skill))

    if skill.get("is_composite", False):
        redis.srem("stale_composites", skill_id)

    if new_def_key and new_code_body:
        store_code(redis, new_def_key, new_code_body, commit_hash=commit_hash)
        for emb in (embedders or []):
            try:
                # Vectors made by the caller in one batched call are used as
                # they are. A store without them is embedded here.
                vecs = (code_vectors or {}).get(emb.name)
                if not vecs:
                    vecs = emb.embed(
                        chunk_texts(new_def_key, new_code_body, chunks),
                        "document")
                # Version id = the commit on the skill record, the same
                # commit its code_at: body is stored under.
                store_code_vectors(redis_binary, skill_id, new_def_key, vecs,
                                   prefix=emb.prefix,
                                   commit_hash=skill.get("commit_hash", ""))
            except Exception as e:
                print(f"⚠️  Code embed [{emb.name}] failed for {skill_id}: {e}")

    stale_count = mark_composites_stale(redis, skill_id) if propagate_stale else 0

    if record_event:
        record_commit_event(redis, commit_hash, "updated", skill_id)

    return {
        "success":          True,
        "stale_composites": stale_count,
        "message":          f"Skill '{skill_id}' fully updated",
    }
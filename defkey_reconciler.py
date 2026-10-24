# unified-brain — cheaper, faster more accurate AI coding agents, by DevLoops
# Copyright (C) 2026 DevLoops SINGLE MEMBER P.C.
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
defkey_reconciler.py

Reconciles the Redis symbol index against each commit's file changes.

Redis key structure (three namespaces only — no defkey: duplication):
    symbol:<filepath>:<symbol>:<line>:<type>  →  skill_id
    skill:<id>                                →  metadata JSON
    code:<filepath>:<symbol>:<line>:<type>    →  full source body

symbol: IS the defkey index. There is no separate defkey: namespace.

For every commit this module handles:

  1. LINE DRIFT
     Symbol body unchanged, only position shifted due to edits above it.
     → Renames symbol:<old> → symbol:<new>
     → Renames code:<old>   → code:<new>
     → Updates def_key field inside skill:<id>
     → No skill change, no LLM call.

  2. CONTENT CHANGE / RENAME / DELETION
     Symbol body changed, renamed, or file deleted.
     → Calls obsolete_skill (moves skill to skill:obsolete:<id>)
     → Removes symbol:<def_key> index entry
     → Moves code:<def_key> → code_hist:<def_key> (out of grep index, kept for provenance)
     → Signals caller to create a new skill.

  3. NEW SYMBOLS
     Symbol in after-state with no existing symbol: entry.
     → Signals caller to create a new skill.
"""

import json
from dataclasses import dataclass, field
from typing import Optional
import store as redis_lib
import time
import skills_lib
import asyncio



# ── Types ─────────────────────────────────────────────────────────────────────

@dataclass
class HunkDelta:
    old_start: int
    old_count: int
    new_start: int
    new_count: int


@dataclass
class FileSymbolEntry:
    name:           str
    line:           int
    structure_type: str
    code:           str
    calls:          list = field(default_factory=list)  # [{"name","line","snippet"}]
    refs:           list = field(default_factory=list)  # [{name,line,snippet,kind}]
    embedded:       list = field(default_factory=list)  # [{content,line,host_pretag,density}]
    embedded_langs: list = field(default_factory=list)  # filled server-side: [{lang,summary,suspicious,line}]
    chunks:         list = field(default_factory=list)  # ingester retrieval chunks: [[start,end), …] line ranges over `code`


@dataclass
class FilePayload:
    file_path:    str
    is_new:       bool
    is_deleted:   bool
    all_symbols:  list[FileSymbolEntry]
    line_deltas:  list[HunkDelta]
    change_types: dict[str, str]  # def_key → added|modified|deleted


@dataclass
class ReconcileResult:
    file_path:        str
    drifted:          list[str] = field(default_factory=list)
    obsoleted:        list[str] = field(default_factory=list)
    new_symbols:      list[FileSymbolEntry] = field(default_factory=list)
    modified_symbols: list[FileSymbolEntry] = field(default_factory=list)


# ── Key construction ──────────────────────────────────────────────────────────


def make_symbol_key(filepath: str, symbol: str, line: int, struct_type: str) -> str:
    """symbol:<filepath>:<symbol>:<line>:<type> — primary def_key index."""
    return f"symbol:{filepath}:{symbol}:{line}:{struct_type}"


def make_code_key(filepath: str, symbol: str, line: int, struct_type: str) -> str:
    """code:<filepath>:<symbol>:<line>:<type> — code body store."""
    return f"code:{filepath}:{symbol}:{line}:{struct_type}"


def parse_symbol_key(key: str) -> Optional[tuple[str, str, int, str]]:
    """
    Parses 'symbol:<filepath>:<symbol>:<line>:<type>'
    → (filepath, symbol, line, struct_type)

    Splits from the right to handle filepaths containing colons.
    Returns None if key is not a valid def_key format.
    """
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


# ── Line delta computation ────────────────────────────────────────────────────

"""
Replacement for DefKeyReconciler._reconcile_file's position logic.

OLD:  new_positions = {(name, structure_type): line}
      Six #ifdef variants of one macro share (name, type), so the dict keeps
      only the last. All six existing symbol: entries then resolve to that one
      line and _apply_drift renames them onto a single key, merging their
      skill lists. Positions that were correct get destroyed.

NEW:  occurrences are paired explicitly — exact stored-body match first, then
      positional order — which is the same algorithm ingester.match_occurrences
      uses for the diff. The index migration and the diff therefore cannot
      disagree about which occurrence is which.
"""


def match_index_positions(existing, all_symbols, get_code):
    """
    existing:    {sym_key: [skill_id, ...]}  from _get_entries_for_file
    all_symbols: [FileSymbolEntry] post-commit
    get_code:    (filepath, name, line, struct_type) -> stored body str

    Returns (drifts, obsoletes, matched_new_keys)
      drifts:    [(sym_key, skill_ids, name, old_line, struct_type, new_line)]
      obsoletes: [(sym_key, skill_ids, name, reason)]
      matched_new_keys: {(name, struct_type, line)} already owned by a skill
    """
    from defkey_reconciler import parse_symbol_key   # local import for testing

    olds = {}
    for sym_key, skill_ids in existing.items():
        parsed = parse_symbol_key(sym_key)
        if not parsed:
            continue
        filepath, name, line, stype = parsed
        olds.setdefault((name, stype), []).append(
            (line, sym_key, skill_ids, filepath))
    for v in olds.values():
        v.sort(key=lambda t: t[0])

    news = {}
    for sym in all_symbols:
        news.setdefault((sym.name, sym.structure_type), []).append(sym)
    for v in news.values():
        v.sort(key=lambda s: s.line)

    drifts, obsoletes, matched_new = [], [], set()

    for key in set(olds) | set(news):
        name, stype = key
        o_list = list(olds.get(key, []))
        n_list = list(news.get(key, []))

        if not n_list:
            for line, sym_key, skill_ids, _fp in o_list:
                obsoletes.append((sym_key, skill_ids, name, 'symbol_gone'))
            continue

        # 1. exact stored-body match — an untouched variant keeps its identity
        #    even when siblings above it moved the line numbers.
        by_code = {}
        for n in n_list:
            by_code.setdefault(n.code, []).append(n)
        used_old, used_new = set(), set()
        pairs = []
        for line, sym_key, skill_ids, fp in o_list:
            stored = get_code(fp, name, line, stype)
            bucket = by_code.get(stored) if stored else None
            if bucket:
                n = bucket.pop(0)
                pairs.append(((line, sym_key, skill_ids, fp), n))
                used_old.add(sym_key)
                used_new.add(id(n))

        # 2. positional pairing of the remainder
        rest_old = [t for t in o_list if t[1] not in used_old]
        rest_new = [n for n in n_list if id(n) not in used_new]
        for t, n in zip(rest_old, rest_new):
            pairs.append((t, n))

        # 3. old occurrences with no counterpart are gone
        for line, sym_key, skill_ids, _fp in rest_old[len(rest_new):]:
            obsoletes.append((sym_key, skill_ids, name, 'occurrence_removed'))

        for (line, sym_key, skill_ids, _fp), n in pairs:
            matched_new.add((name, stype, n.line))
            if n.line != line:
                drifts.append((sym_key, skill_ids, name, line, stype, n.line))

    return drifts, obsoletes, matched_new


# ── Core reconciler ───────────────────────────────────────────────────────────

class DefKeyReconciler:
    """
    Reconciles Redis symbol index against commit file changes.
    Stateless between calls — instantiate once per server startup.
    """

    def __init__(self, redis_client, mcp_client, redis_binary_client=None):
        self.redis        = redis_client
        self.redis_binary = redis_binary_client
        self.mcp          = mcp_client  # keep for non-ingest callers, but not used here

    # ── Public API ────────────────────────────────────────────────────────────

    async def reconcile_commit(
        self,
        file_payloads: list[FilePayload],
        commit_hash: str,
        goal: str,
        redis_override: Optional[redis_lib.Store] = None,
        redis_binary_override: Optional[redis_lib.Store] = None,
    ) -> list[ReconcileResult]:
        redis        = redis_override        or self.redis
        redis_binary = redis_binary_override or self.redis_binary
        results = []
        for fp in file_payloads:
            result = await self._reconcile_file(fp, commit_hash, goal, redis, redis_binary)
            results.append(result)
        return results

    def register(
        self,
        filepath: str,
        symbol: str,
        line: int,
        struct_type: str,
        skill_id: str,
        code_body: str = "",
        redis_override: Optional[redis_lib.Store] = None,
        commit_hash: str = "",
    ) -> None:
        redis    = redis_override or self.redis
        sym_key  = make_symbol_key(filepath, symbol, line, struct_type)
        code_key = make_code_key(filepath, symbol, line, struct_type)

        # Handle migration from old string format to list format
        key_type = redis.type(sym_key)
        if key_type == 'string':
            old_val = redis.get(sym_key)
            redis.delete(sym_key)
            if old_val:
                redis.rpush(sym_key, old_val)

        # Append skill_id to list if not already present
        existing = redis.lrange(sym_key, 0, -1)
        existing = [s.decode() if isinstance(s, bytes) else s for s in existing]
        if skill_id not in existing:
            redis.rpush(sym_key, skill_id)

        # NEW: per-file index
        redis.sadd(f"file_symbols:{filepath}", sym_key)
        redis.sadd(f"symbol_name:{symbol}", sym_key)

        if code_body:
            skills_lib.store_code(
                redis, f"{filepath}:{symbol}:{line}:{struct_type}", code_body,
                commit_hash=commit_hash,
            )

        print(f"  🔑 Registered: {sym_key} → {skill_id}")

    # ── Per-file reconciliation ─────────────────────────────────────────────── 
    async def _reconcile_file(
        self,
        fp: FilePayload,
        commit_hash: str,
        goal: str,
        redis: redis_lib.Store,
        redis_binary: Optional[redis_lib.Store],
    ) -> ReconcileResult:
        result   = ReconcileResult(file_path=fp.file_path)
        t0       = time.perf_counter()
        existing = self._get_entries_for_file(fp.file_path, redis)
        print(f"  ⏱️  _get_entries_for_file: {(time.perf_counter() - t0) * 1000:.1f}ms")

        # ── Deleted file ──────────────────────────────────────────────────
        if fp.is_deleted:
            for sym_key, skill_ids in existing.items():
                parsed = parse_symbol_key(sym_key)
                if not parsed:
                    continue
                _, symbol, _, _ = parsed
                for skill_id in skill_ids:
                    await self._obsolete(
                        sym_key, skill_id, symbol, result,
                        reason=f"File deleted in: {goal[:80]}", 
                        redis=redis,
                        redis_binary=redis_binary,
                        commit_hash=commit_hash,
                    )
            return result

        # Occurrence-aware pairing. A file legitimately holds several symbols
        # sharing name AND structure_type — six #if/#elif variants of a macro,
        # a shell variable reassigned down the script, repeated cmake set().
        # Keying positions on (name, type) kept only the last, so every other
        # occurrence's symbol: key drifted onto it and their skill lists merged.
        drifts, obsoletes, matched_new = match_index_positions(
            existing, fp.all_symbols,
            lambda f, n, l, s: self._get_stored_code(f, n, l, s, redis),
        )

        for sym_key, skill_ids, name, reason in obsoletes:
            for skill_id in skill_ids:
                await self._obsolete(
                    sym_key, skill_id, name, result,
                    reason=f"{reason} in: {goal[:80]}",
                    redis=redis, redis_binary=redis_binary,
                    commit_hash=commit_hash,
                )

        for sym_key, skill_ids, name, old_line, stype, new_line in drifts:
            self._apply_drift(
                fp.file_path, name, old_line, stype, new_line, skill_ids,
                self._get_stored_code(fp.file_path, name, old_line, stype, redis),
                redis=redis,
            )
            result.drifted.append(name)
            print(f"  📍 Position migrated: {name} {old_line}→{new_line} "
                  f"({len(skill_ids)} skills)")

        # New vs modified, per occurrence. matched_new holds the occurrences
        # already owned by a skill; anything else is genuinely new even when a
        # same-named symbol exists elsewhere in the file (prototype/definition).
        for sym in fp.all_symbols:
            dk = f"{fp.file_path}:{sym.name}:{sym.line}:{sym.structure_type}"
            change_type = fp.change_types.get(dk)
            owned = (sym.name, sym.structure_type, sym.line) in matched_new
            if not owned:
                if change_type == 'added' or fp.is_new:
                    result.new_symbols.append(sym)
            elif change_type == 'modified':
                result.modified_symbols.append(sym)

        return result


    # ── Redis helpers ─────────────────────────────────────────────────────────
    
    def _get_entries_for_file(self, filepath, redis):
        sym_keys = redis.smembers(f"file_symbols:{filepath}")
        sym_keys = [k.decode() if isinstance(k, bytes) else k for k in sym_keys]
        sym_keys = [k for k in sym_keys if parse_symbol_key(k)]
        if not sym_keys:
            return {}

        pipe = redis.pipeline(transaction=False)
        for k in sym_keys:
            pipe.exists(k)
        alive = pipe.execute()

        live_keys = []
        stale = [k for k, ok in zip(sym_keys, alive) if not ok]
        if stale:
            redis.srem(f"file_symbols:{filepath}", *stale)
        live_keys = [k for k, ok in zip(sym_keys, alive) if ok]
        if not live_keys:
            return {}

        pipe = redis.pipeline(transaction=False)
        for k in live_keys:
            pipe.lrange(k, 0, -1)
        id_lists = pipe.execute()

        all_ids, spans = [], []
        for ids in id_lists:
            ids = [s.decode() if isinstance(s, bytes) else s for s in ids]
            spans.append((len(all_ids), len(all_ids) + len(ids)))
            all_ids.extend(ids)
        skill_blobs = redis.mget([f"skill:{s}" for s in all_ids]) if all_ids else []

        result = {}
        for key_str, (lo, hi) in zip(live_keys, spans):
            active = []
            for sid, blob in zip(all_ids[lo:hi], skill_blobs[lo:hi]):
                if not blob:
                    continue
                if json.loads(blob).get("isObsolete", False):
                    continue
                active.append(sid)
            if active:
                result[key_str] = active

        total = sum(len(v) for v in result.values())
        print(f"  📋 _get_entries_for_file({filepath}): "
              f"{len(result)} positions, {total} active skills")
        return result

    def _get_stored_code(
        self,
        filepath: str,
        symbol: str,
        line: int,
        struct_type: str,
        redis: redis_lib.Store
    ) -> str:
        return skills_lib.get_code(
            redis, f"{filepath}:{symbol}:{line}:{struct_type}"
        )

    def _apply_drift(
        self,
        filepath: str,
        symbol: str,
        old_line: int,
        struct_type: str,
        new_line: int,
        skill_ids: list[str],
        code_body: str,
        redis: redis_lib.Store
    ) -> None:
        old_sym  = make_symbol_key(filepath, symbol, old_line, struct_type)
        new_sym  = make_symbol_key(filepath, symbol, new_line, struct_type)

        old_code = make_code_key(filepath, symbol, old_line, struct_type)
        new_code = make_code_key(filepath, symbol, new_line, struct_type)

        old_def_key = f"{filepath}:{symbol}:{old_line}:{struct_type}"
        new_def_key = f"{filepath}:{symbol}:{new_line}:{struct_type}"

        # Forwarding pointer: the old address must stay resolvable — code_at:
        # snapshots carry it forever. Chains compose across repeated drifts;
        # the reader path-compresses them.
        redis.set(f"moved_from:{old_def_key}", new_def_key)

        # NEW: keep per-file index in sync with the rename
        redis.srem(f"file_symbols:{filepath}", old_sym)
        redis.sadd(f"file_symbols:{filepath}", new_sym)
        redis.srem(f"symbol_name:{symbol}", old_sym)
        redis.sadd(f"symbol_name:{symbol}", new_sym)

        # Latest-version commit for the code_at: copy: read the drifting
        # skills' records BEFORE the index rename. Any one carries it — a
        # merged position shares one body, hence one latest version.
        drift_commit = ""
        for _sid in skill_ids:
            _raw = redis.get(f"skill:{_sid}")
            if _raw:
                drift_commit = json.loads(_raw).get("commit_hash", "") or ""
                if drift_commit:
                    break

        if redis.exists(old_sym):
            if redis.exists(new_sym):
                old_ids = [s.decode() if isinstance(s, bytes) else s for s in redis.lrange(old_sym, 0, -1)]
                new_ids = [s.decode() if isinstance(s, bytes) else s for s in redis.lrange(new_sym, 0, -1)]
                for oid in old_ids:
                    if oid not in new_ids:
                        redis.rpush(new_sym, oid)
                redis.delete(old_sym)
            else:
                redis.rename(old_sym, new_sym)

        # Code hash rides along: RENAME keeps it in the FT index (same
        # prefix), then metadata fields are patched to the new address.
        if redis.exists(new_code):
            redis.delete(new_code)  # collision — old body wins, matches skill merge
        skills_lib.rename_code(redis, old_def_key, new_def_key,
                               commit_hash=drift_commit)
        if code_body and not redis.exists(new_code):
            skills_lib.store_code(redis, new_def_key, code_body,
                                  commit_hash=drift_commit)

        skills_lib.drift_call_edges(
            redis,
            old_def_key,
            new_def_key,
            new_line - old_line,
        )
        skills_lib.drift_ref_edges(
            redis, 
            old_def_key, 
            new_def_key,
            new_line - old_line
        )
        for skill_id in skill_ids:
            skill_json = redis.get(f"skill:{skill_id}")
            if skill_json:
                skill = json.loads(skill_json)
                skill["def_key"] = new_def_key
                redis.set(f"skill:{skill_id}", json.dumps(skill))

    async def _obsolete(
        self,
        sym_key: str,
        skill_id: str,
        symbol_name: str,
        result,
        reason: str,
        redis: redis_lib.Store,
        redis_binary: Optional[redis_lib.Store],
        commit_hash: str = "",
    ):
        print(f"  🗑️  _obsolete called: {symbol_name} [{skill_id}]")

        if redis_binary is None:
            print(f"  ⚠️  No redis_binary available — skipping obsoletion for {symbol_name} [{skill_id}]")
            return

        try:
            res = await asyncio.to_thread(
                skills_lib.obsolete_skill,
                redis, redis_binary,
                skill_id=skill_id,
                reason=reason,
                commit_hash=commit_hash,
            )
        except Exception as e:
            print(f"  ⚠️  Failed to obsolete {symbol_name}: {e}")
            return

        if not res.get("success"):
            print(f"  ⚠️  obsolete_skill returned: {res.get('message', '')[:200]}")
            return

        stale = res.get("stale_composites", 0)
        print(f"  🗄️  Obsoleted: {symbol_name} [{skill_id}] (composites flagged: {stale})")
        result.obsoleted.append(symbol_name)
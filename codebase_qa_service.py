#!/usr/bin/env python3
"""
unified-brain — local service
-----------------------------
One user, one database file per repository, settings from .env. Serves the question page on GET /,
the timeline on GET /timeline, and the report/probe API under /api/timeline.
"""

import json
import os
import store

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from typing import Optional, Literal
from pydantic import BaseModel
from templates import HTML, TIMELINE_HTML
import httpx
import time
import asyncio
import secrets
import traceback
import re
from concurrent.futures import ThreadPoolExecutor
import fnmatch
import hashlib
from datetime import datetime
import skills_lib
import json as _json
from dataclasses import dataclass
import contextvars
import threading
import litellm

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))


# Applied in order. Add a (pattern, replacement) line to extend coverage.
_SCRUB_PATTERNS = [
    # Passwords embedded in connection URIs: redis(s), bolt, neo4j(+s)
    (re.compile(r'((?:redis|rediss|bolt|neo4j)(?:\+s|\+ssc)?)://[^:/@\s]+:[^@\s]+@'),
     r'\1://***:***@'),
    # Anthropic / DeepSeek / OpenAI secret keys
    (re.compile(r'sk-(?:ant-)?[A-Za-z0-9_\-]{20,}'), 'sk-***'),
    # DevLoops API keys
    (re.compile(r'dl_(live|test)_[A-Za-z0-9_\-]+'), r'dl_\1_***'),
    # JWTs (header.payload.signature)
    (re.compile(r'eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+'), '***JWT***'),
    # Bearer tokens
    (re.compile(r'(?i)(bearer)\s+[A-Za-z0-9._\-]+'), r'\1 ***'),
    # Bare credential fields: password=…, "secret": "…", p_value: '…', etc.
    (re.compile(
        r'(?i)\b(redis_password|neo4j_password|password|passwd|secret|token|api[_-]?key|p_value)\b'
        r'(\s*["\']?\s*[:=]\s*["\']?)([^"\'\s,;}]+)'),
     r'\1\2***'),
]

def _scrub(text: str) -> str:
    """Redact known credential shapes from log/error strings.

    Covers URI passwords (redis/rediss/bolt/neo4j[+s]), sk-/dl_ keys, JWTs,
    Bearer tokens, and bare password/secret/token/p_value fields. Over-redaction
    is deliberate: a leaked secret costs more than a redacted log line.
    """
    for pat, repl in _SCRUB_PATTERNS:
        text = pat.sub(repl, text)
    return text

def _body_key(filepath: str, symbol: str) -> tuple[str, str]:
    """Registry key for a shipped code body. lstrips './' and drops ':start-end'
    so def_key paths and loc strings all collide correctly."""
    return ((filepath or "").lstrip("./").split(":", 1)[0], symbol or "")

def _body_seen(shown_bodies: dict, key: tuple, code: str) -> bool:
    """True if this exact body already shipped under this (file, symbol) key.
    Same-named symbols in one file have different bodies → different hashes →
    both ship. Same body re-read from two sources → normalized hash collides
    → elided. Registers on miss."""
    h = hashlib.sha1(
        "\n".join(l.strip() for l in code.rstrip().splitlines()).encode()
    ).hexdigest()
    hashes = shown_bodies.setdefault(key, set())
    if h in hashes:
        return True
    hashes.add(h)
    return False

# The ingester puts one annotation line on top of C symbols that sit inside
# #if/#ifdef branches. It is not file content and must not count as a line.
_PREPROC_CTX = re.compile(r"^(?://|#) \[preproc context: (.*)\]\n")

def _split_guard(code: str) -> tuple[str, str]:
    """(guard text, real body). ('', code) when there is no annotation."""
    m = _PREPROC_CTX.match(code or "")
    if not m:
        return "", code or ""
    return m.group(1), code[m.end():]

def _guard_line(skill: dict) -> str:
    g = skill.get("guard")
    return (f"Preprocessor context (DevLoops annotation, not a file line): {g}\n"
            if g else "")




# ── Settings (.env) ───────────────────────────────────────────────────────────
#   DB_PATH             /path/to/repo/.unified-brain.db — the repository's database (written by next_claude.py)
#   LLM_PROVIDER        anthropic | llmbase             writer / judge (PROVIDER_DEFAULTS)
#   LLM_API_KEY         key for that provider
#   LLM_MODEL           optional, overrides the provider's default model
#   LLM_API_BASE        optional, overrides the provider's default endpoint
#   OPENROUTER_API_KEY  Jev (evidence gathering)
#   QA_VECTOR_STORE     voyage | qwen — the code-vector store that pre-filters for Jev
#   VOYAGE_API_KEY / DEEPINFRA_API_KEY   key of that store
DB_PATH = os.getenv("DB_PATH", os.path.join(os.getcwd(), store.DB_FILE_NAME))

_redis_text   = store.open(DB_PATH)
_redis_binary = _redis_text.binary()

def _redis_clients() -> tuple:
    """(text view, bytes view) of the repository's database file."""
    return _redis_text, _redis_binary


class MissingSecret(Exception):
    pass


# ── Clients ────────────────────────────────────────────────────────────────────
app = FastAPI(title="unified-brain", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=65536)



TOP_K           = 17
MIN_SCORE       = 0.35

# ── Code-vector store ─────────────────────────────────────────────────────
# Chunk vectors of every stored body version (cvec_at:, voyage-code-4 or
# qwen). Default from env; a request can override via AskRequest.vector_store.
# Per-store score threshold via MIN_SCORE_VOYAGE / MIN_SCORE_QWEN.
QA_VECTOR_STORE_DEFAULT = os.environ.get("QA_VECTOR_STORE", "voyage")
_VECTOR_STORE: contextvars.ContextVar[str] = contextvars.ContextVar(
    "vector_store", default=QA_VECTOR_STORE_DEFAULT)

CODE_EMBEDDERS: dict = {}
for _n, _k in (("voyage", "VOYAGE_API_KEY"), ("qwen", "DEEPINFRA_API_KEY")):
    _e = skills_lib.make_code_embedder(_n, os.getenv(_k, ""))
    if _e is not None:
        CODE_EMBEDDERS[_n] = _e
print(f"🧭 code stores loaded: {sorted(CODE_EMBEDDERS) or 'none'} | "
      f"voyage sdk: {skills_lib.VOYAGE_AVAILABLE} | "
      f"VOYAGE_API_KEY set: {bool(os.getenv('VOYAGE_API_KEY'))}")
if _redis_text.vec_tables_to_migrate():
    print("⚠️  the vector tables of this file use the old layout: the embedding search scans "
          "every stored version. Run once to make it fast:\n"
          f"    python next_claude.py <repo> --embed-only        (file: {DB_PATH})")

def _code_embedder(store: str):
    e = CODE_EMBEDDERS.get(store)
    if e is None:
        raise RuntimeError(f"vector_store={store} but its API key is unset")
    return e

def _min_score(store: str) -> float:
    return float(os.environ.get(f"MIN_SCORE_{store.upper()}", str(MIN_SCORE)))


# ─── Haiku 4.5 pricing in USD per million tokens ──────────────────────







# ── Helpers ────────────────────────────────────────────────────────────────────


@dataclass
class LLMTarget:
    provider:     str
    model:        str
    api_key:      str
    api_base:     str | None
    extra_params: dict          # forwarded into litellm.acompletion(**extra_params)


def _no_think_params(target: "LLMTarget") -> dict:
    """Explicit thinking-disable by endpoint dialect. Makora V4-Flash-0731+
    defaults thinking ON; silence no longer disables. reasoning_effort='none'
    is the verified off switch (reasoning:null, no scaffold in prompt).
    api.deepseek.com keeps its native extra_body dialect. Anthropic: never
    send reasoning_effort."""
    if target.provider == "anthropic":
        return {}
    if target.api_base and "deepseek.com" in target.api_base:
        return {"extra_body": {"thinking": {"type": "disabled"}}}
    return {"reasoning_effort": "none",
            "allowed_openai_params": ["reasoning_effort"]}



def _decode_set(raw) -> set[str]:
    return {x.decode() if isinstance(x, bytes) else x for x in raw}










def _fetch_body(org_redis, *, def_key=None):
    """The stored body of a symbol (code:<def_key>). Nothing is read from
    the working tree: a file on disk is the state at HEAD, not at the
    commit under review."""
    if org_redis and def_key:
        code = skills_lib.get_code(org_redis, def_key)
        if code:
            return code, "redis"
    return "", ""


def _obsoleted_at_or_before(org_redis, skill: dict, to_rank: int) -> Optional[str]:
    """Full hash of the obsoleting commit if this skill was obsoleted at or
    before to_rank (i.e. it did NOT exist at the probed commit), else None.
    Obsolete-but-untracked returns None — caller falls back to old behavior."""
    if not skill.get("isObsolete", False):
        return None
    oc = skill.get("obsoleted_commit") or ""
    if not oc:
        return None
    r = org_redis.zrank("commit_order", oc)
    if r is not None and int(r) <= to_rank:
        return oc
    return None

def _fetch_skill_raw(skill_id: str, org_redis, prefer_redis=False,
                     include_obsolete=False, as_of=None) -> dict | None:
    if as_of is not None:
        # Time-travel read: reconstruct state as of the window's upper bound,
        # body from the per-commit store, never the HEAD row.
        skill = skills_lib.get_skill_as_of(org_redis, skill_id, as_of["to_rank"])
        if skill is None:
            return None
        removed_at = _obsoleted_at_or_before(org_redis, skill, as_of["to_rank"])
        if removed_at is not None:
            def_key = skill.get("def_key", "") or ""
            _obr = org_redis.zrank("commit_order", removed_at)
            if _obr is not None and int(_obr) == as_of["to_rank"]:
                # Removed by the probed commit ITSELF. The deletion is part
                # of the change under judgment, so the pre-removal body is
                # legitimate evidence — serve it, unmistakably tagged.
                # (code: was renamed to code_hist: on obsoletion; get_code
                # follows that fallback.)
                code = skills_lib.get_code(org_redis, def_key) if def_key else ""
                return {
                    "skill_id":      skill_id,
                    "name":          skill.get("name", skill_id),
                    "description":   skill.get("description_of_skill", ""),
                    "file_path":     def_key.split(":")[0] if def_key else "",
                    "def_key":       def_key,
                    "suggested":     skill_id.startswith("~"),
                    "code":          code,
                    "code_source":   "pre_removal" if code else "",
                    "is_obsolete":   True,
                    "removed_at":    removed_at,
                    "removed_by_probed": True,
                    "reconstructed": False,
                }
            # Symbol was removed BEFORE the probed commit — did NOT exist in
            # the target state. Serving its body as live state is the
            # stale-version contamination that fabricated the
            # HAVE_LINUX_LANDLOCK_H false positive. Ship the fact of
            # removal, withhold the body.
            return {
                "skill_id":      skill_id,
                "name":          skill.get("name", skill_id),
                "description":   skill.get("description_of_skill", ""),
                "file_path":     def_key.split(":")[0] if def_key else "",
                "def_key":       def_key,
                "suggested":     skill_id.startswith("~"),
                "code":          "",
                "code_source":   "",
                "is_obsolete":   True,
                "removed_at":    removed_at,
                "reconstructed": False,
            }
        is_obsolete = skill.get("isObsolete", False)
        if is_obsolete and not include_obsolete:
            return None
        def_key = skill.get("def_key", "")
        if skill.get("_as_of_warning"):
            # No in-range snapshot exists — the record (and its body) are
            # post-range. Serving them is the contamination the window
            # exists to prevent. Withhold the body, ship the fact.
            return {
                "skill_id":      skill_id,
                "name":          skill.get("name", skill_id),
                "description":   "(no in-range version stored — record "
                                 "postdates the probed commit; body withheld)",
                "file_path":     def_key.split(":")[0] if def_key else "",
                "def_key":       def_key,
                "suggested":     skill_id.startswith("~"),
                "code":          "",
                "code_source":   "",
                "is_obsolete":   is_obsolete,
                "reconstructed": False,
            }
        code = (skills_lib.get_code_as_of(org_redis, def_key,
                                          skill.get("commit_hash", ""))
                if def_key else "")
        return {
            "skill_id":      skill_id,
            "name":          skill.get("name", skill_id),
            "description":   skill.get("description_of_skill", ""),
            "file_path":     def_key.split(":")[0] if def_key else "",
            "def_key":       def_key,
            "suggested":     skill_id.startswith("~"),
            "code":          code,
            "code_source":   "as_of" if code else "",
            "is_obsolete":   is_obsolete,
            "reconstructed": bool(skill.get("_as_of_reconstructed", False)),
        }

    raw = org_redis.get(f"skill:{skill_id}")
    if not raw:
        return None
    skill = json.loads(raw)
    is_obsolete = skill.get("isObsolete", False)
    if is_obsolete and not include_obsolete:
        return None
    def_key = skill.get("def_key", "")
    code, source = ("", "")
    if def_key:
        code, source = _fetch_body(org_redis, def_key=def_key)
    return {
        "skill_id":    skill_id,
        "name":        skill.get("name", skill_id),
        "description": skill.get("description_of_skill", ""),
        "file_path":   def_key.split(":")[0] if def_key else "",
        "def_key":     def_key,
        "suggested":   skill_id.startswith("~"),
        "code":        code,
        "code_source": source,   # 'redis' | ''
        "is_obsolete": is_obsolete,
    }

def _fetch_skill_with_code(*args, **kwargs) -> dict | None:
    """_fetch_skill_raw, with the guard annotation split off the body.
    'code' is the real body, 'guard' the branch text, 'code_raw' the stored text."""
    sk = _fetch_skill_raw(*args, **kwargs)
    if sk and sk.get("code"):
        sk["code_raw"] = sk["code"]
        sk["guard"], sk["code"] = _split_guard(sk["code"])
    return sk



def _expand_composite_members(org_redis, skill: dict, as_of=None,
                              limit: int = 12) -> list[dict]:
    """One-level read-time intent for a composite: its members' atomic
    descriptions. Nested composite members render their synthetic one-liner
    — no recursion. Windowed reads serve as-of descriptions and drop
    members whose provenance fails closed."""
    member_ids = list(skill.get("composes_skills") or [])[:limit]
    if not member_ids:
        return []
    values = org_redis.mget([f"skill:{m}" for m in member_ids])
    out = []
    for mid, raw in zip(member_ids, values):
        if not raw:
            continue
        m = json.loads(raw)
        desc = m.get("description_of_skill", "")
        if as_of is not None:
            desc = _asof_description(org_redis, mid, m, as_of["to_rank"])
            if desc is None:
                continue
        parsed = skills_lib.parse_def_key(m.get("def_key", "") or "")
        out.append({
            "skill_id":    mid,
            "symbol":      parsed[1] if parsed else
                           ("(nested composite)" if m.get("is_composite") else ""),
            "description": desc,
            "is_obsolete": m.get("isObsolete", False),
        })
    return out




def _knn_candidates(question, org_redis_binary, *, embedding, top_k,
                    include_obsolete, store: str,
                    atomics_only=False, as_of=None) -> list[tuple[str, float]]:
    """[(skill_id, score)] above threshold, best first.
    Chunk rows of stored body versions, collapsed to one per skill with
    score = max over its chunks. as_of given: only the version of each
    skill that was valid at as_of["to_rank"] is searched. No as_of: only
    its newest version.
    `embedding`, when given, must be a vector of the selected store's model."""
    k = top_k or TOP_K
    if True:
        emb = _code_embedder(store)
        idx = skills_lib.get_code_vector_index(org_redis_binary, emb)
        if idx is None:
            return []
        if embedding is None:
            if not question:
                return []
            embedding = emb.embed([question], "query")[0]
        # Several chunk rows can belong to one skill, so k*8 rows may hold
        # fewer than k skills. Ask for more rows until k skills are found,
        # the scores fall under the cut, or the index has no more rows.
        n_rows = k * 8
        max_rows = int(os.environ.get("CODE_KNN_MAX_ROWS", "20000"))
        while True:
            # as_of: the body that existed at the window's right-side commit
            # (written at or before it, not yet replaced or deleted at it).
            # No as_of: each skill's newest version.
            _t_knn = time.time()
            rows = org_redis_binary.knn(
                emb.prefix, embedding, n_rows,
                as_of_rank=(as_of["to_rank"] if as_of is not None else None),
                latest_only=as_of is None, include_obsolete=include_obsolete)
            _t_knn = time.time() - _t_knn
            best: dict[str, float] = {}
            below_cut = False
            for r in rows:
                score = 1 - float(r.get("vector_distance", 1))
                if score < _min_score(store):
                    below_cut = True
                    continue
                sid = r.get("skill_id", "")
                sid = sid.decode() if isinstance(sid, bytes) else sid
                dk = r.get("def_key", "")
                dk = dk.decode() if isinstance(dk, bytes) else dk
                if atomics_only and not dk:
                    continue                  # composite row: it has no def_key
                if sid and score > best.get(sid, float("-inf")):
                    best[sid] = score
            print(f"🧭 code knn [{store}]: asked {n_rows} rows, got {len(rows)}, "
                  f"{len(best)} skills (want {k}) in {_t_knn:.2f}s")
            if (len(best) >= k or below_cut or len(rows) < n_rows
                    or n_rows >= max_rows):
                break
            n_rows = min(n_rows * 4, max_rows)
        return sorted(((s, round(sc, 3)) for s, sc in best.items()),
                      key=lambda t: -t[1])[:k]















def _build_context(skills: list[dict], shown_bodies: Optional[dict] = None) -> str:
    parts = []
    for i, s in enumerate(skills, 1):
        tag = " [PLANNED — not yet implemented]" if s["suggested"] else ""
        if s.get("is_obsolete"):
            tag += " [OBSOLETE at current HEAD — existed at the probed commit]"
        if s.get("reconstructed"):
            tag += " [STATE RECONSTRUCTED as of the probed range — later revisions hidden]"
        header = f"### {i}. {s['name']}{tag} (relevance: {s['score']})"
        if s["file_path"]:
            header += f"\nFile: {s['file_path']}"
        if s.get("guard"):
            header += "\n" + _guard_line(s).rstrip()
        body = header + (f"\n\n**Description:** {s['description']}" if s["description"] else "")
        if s.get("is_composite") and s.get("members"):
            mem = "\n".join(
                f"  - `{m['skill_id']}` {m['symbol']}"
                + (" [OBSOLETE]" if m.get("is_obsolete") else "")
                + f": {m['description']}"
                for m in s["members"])
            body += ("\n\n**Mechanism members** (the composite's intent is the "
                     "sum of these; the label line above is not a description):\n"
                     + mem)
        if s["code"]:
            if shown_bodies is not None and _body_seen(
                    shown_bodies,
                    _body_key(s["file_path"], s.get("symbol") or s["name"]),
                    s["code"]):
                body += ("\n\n**Source code:** (body already shown this session — "
                         f"see the earlier occurrence for {s['file_path']}; do not re-request)")
            else:
                body += f"\n\n**Source code:**\n```typescript\n{s['code'].rstrip()}\n```"
        elif s.get("is_composite"):
            body += "\n\n**Source code:** (composite — no single body)"
        else:
            body += ("\n\n**Source code:** (none stored — do not assert "
                     "this skill's behavior; its body is not shown)")
        if s.get("branch"):
            body += "\n\n" + s["branch"]
        parts.append(body)
    return "\n\n---\n\n".join(parts)




SYSTEM_PROBE = """You are a supply-chain code reviewer judging ONE commit's change to ONE mechanism, as of that commit. You have NO tools and cannot ask for anything: everything you may use is in the message below. The question states exactly what to establish and how to end.

EVIDENCE BLOCKS (all read as of the probed commit)
- The target: the changed symbol's body and the diff of this commit. Bodies and diffs are the ONLY source of actual code. Read a body before any claim about what it does.
- "Everything else this commit changed": the same commit's other slices, with their diffs.
- "find_callers_provenance" / "find_referrers": current call and address-taken edges, each stamped with its introducing commit; edges introduced after the probed commit are hidden. Zero callers but a referrer is LIVE.
- "Code reached by following names from the change": bodies DevLoops read by following names out of the change, each with the chain that led there. "Places reached but not read" are leads, never evidence.
- A fact that is not shown in these blocks is NOT READ: say "not shown to me" and do not build a verdict on it.

RULES
- Make fewer claims rather than one unread claim. Say "I did not read X" when you did not.
- RULE PRECEDENCE: the verdict rules below are policy, not advice. When a rule states that a verdict follows from named premises alone and you have established those premises as READ facts, stamp that verdict. Mitigating context (plausible stated goal, coordinated sibling changes, build-system maturity, project or author history — in EITHER direction) goes in prose and never lowers the stamped severity. If you believe a rule misfires here, stamp per the rule and say why in prose; you do not have override authority.
- CLAIM CLASSES — READ vs DERIVED:
  Every sentence in your answer is one of two classes:
  (a) READ — grounded in a body, diff, or doc you retrieved THIS session. State plainly, cite the coordinate.
  (b) DERIVED — an inference connecting read facts: consequences on platforms or configurations you did not read, defaults of external systems (linkers, OSes, toolchains), behavior of code paths you did not open, "therefore X is moot/safe/broken elsewhere". Syntactic validity of text you read, under the language's own grammar, is a READ fact — the text is the evidence; only behavior contingent on a specific compiler, libc, or toolchain is DERIVED.
  DERIVED claims are where answers go wrong. For each one: find it in the blocks shown and promote it to (a), or prefix it explicitly ("Inference, not verified in this codebase: ..."), or DELETE it. A narrower answer of pure (a) claims outranks a broader answer padded with unverified (b). The moment you are about to write about a system, platform, or config whose code is not shown to you is the moment to stop or cut.
  The VERDICT is itself a derivation — that is its job. The rule is: every FACTUAL PREMISE the verdict rests on must be (a), read this session and bound to the probed commit's state. A verdict is sound when its premises are all READ, even though the concluding step is yours; a verdict with an unverified (b) premise is a defect.
- Cite the file, symbol, and lines you actually read, from ONE block per claim; line numbers from different blocks are not comparable.
- Bodies and diffs are byte-accurate at the commit; nothing shown is a rendering artifact.
- Never treat author, project, or maintainer history as evidence. If you recognize this project, commit, or code from prior knowledge, that recollection is NEVER READ evidence: do not use it to reconstruct, verify, or contradict anything — only what is shown in this message counts, and recalled upstream code additionally defeats the temporal window."""


def _diff_between(org_redis, sid: str, commit: str) -> dict:
    """One skill's body diff at one commit, reusing the _touch_diffs chain
    walk. Returns {'diff': ...} or {'status': ...}."""
    out = _touch_diffs(org_redis,
                       {"skill_id": sid, "touches": [{"commit": commit}]})
    return out[0] if out else {"status": "no version chain for this skill"}

def _callers_text(sym: str, org_redis, as_of: Optional[dict] = None) -> str:
    """Who calls `sym`, with the introducing commit (ingestion call index,
    current + historical). Windowed to the probed commit when as_of is set."""
    caller_keys = [(dk, "calls") for dk in
                   _decode_set(org_redis.smembers(f"called_by:{sym}"))]
    caller_keys += [(dk, "calls_hist") for dk in
                    _decode_set(org_redis.smembers(f"called_by_hist:{sym}"))]
    if not caller_keys:
        return (f"No callers of `{sym}` in the ingestion index, current or "
                f"historical. (Index covers ingested commits only.)")
    pipe = org_redis.pipeline(transaction=False)
    for dk, prefix in caller_keys:
        pipe.hgetall(f"{prefix}:{dk}")
    lines = [f"### Callers of `{sym}` (with introducing commit)", ""]
    for (dk, _prefix), h in zip(caller_keys, pipe.execute()):
        for f, v in h.items():
            f = f.decode() if isinstance(f, bytes) else f
            v = v.decode() if isinstance(v, bytes) else v
            callee, _, line = f.rpartition(":")
            if callee != sym:
                continue
            try: rec = json.loads(v)
            except (json.JSONDecodeError, TypeError): rec = {}
            if as_of is not None:
                _i = org_redis.zrank("commit_order", rec.get("commit") or "")
                if _i is not None and int(_i) > as_of["to_rank"]:
                    continue          # introduced after the probed commit
                _x = org_redis.zrank("commit_order", rec.get("removed") or "")
                if _x is not None and int(_x) <= as_of["to_rank"]:
                    continue          # already removed at the probed commit
            rm = (f" — removed in `{rec['removed'][:12]}`"
                  if rec.get("removed") else "")
            lines.append(f"- `{dk}` L{line} — introduced in "
                         f"`{(rec.get('commit') or '?')[:12]}`{rm}: "
                         f"`{(rec.get('snippet') or '')[:80]}`")
    if as_of is not None and len(lines) == 2:
        return (f"No callers of `{sym}` at the probed commit — every "
                f"recorded call edge was either introduced later or "
                f"already removed by then.")
    return "\n".join(lines)


def _referrers_text(sym: str, org_redis, as_of: Optional[dict] = None) -> str:
    """Who takes the address of `sym` (ref-edge index, current + historical).
    Windowed to the probed commit when as_of is set."""
    refs = skills_lib.find_referrers(org_redis, sym, include_hist=True)
    if as_of is not None:
        kept = []
        for r in refs:
            _i = org_redis.zrank("commit_order", r.get("commit") or "")
            if _i is not None and int(_i) > as_of["to_rank"]:
                continue                   # introduced after the probed commit
            _x = org_redis.zrank("commit_order", r.get("removed") or "")
            if _x is not None and int(_x) <= as_of["to_rank"]:
                continue                   # already removed at the probed commit
            kept.append(r)
        refs = kept
    if not refs:
        return (f"No referrers of `{sym}` in the ref-edge index — "
                f"nothing currently takes its address. (Covers "
                f"ingested commits; call edges are separate — see the "
                f"callers list.)")
    lines = [f"### Referrers of `{sym}` (address-taken, with "
             f"introducing commit)", ""]
    for r in refs:
        rm = f" — removed in `{r['removed'][:12]}`" if r.get("removed") else ""
        lines.append(f"- `{r['def_key']}` L{r['line']} "
                     f"[{r.get('kind') or 'ref'}] — introduced in "
                     f"`{(r.get('commit') or '?')[:12]}`{rm}: "
                     f"`{(r.get('snippet') or '')[:80]}`")
    return "\n".join(lines)



def _sse_event(payload: dict) -> str:
    """Format a payload as a Server-Sent Event."""
    return f"data: {_json.dumps(payload)}\n\n"




# ── API Models ─────────────────────────────────────────────────────────────────

JEV_URL = "https://openrouter.ai/api/alpha/decisions"
JEV_MODEL = os.environ.get("JEV_MODEL", "typesafe/jev-1.13")   # or cloudflare/clef-flash

def _jev_rows_as_of(org_redis, rows: list, to_rank: int) -> list:
    """rows = [(skill_id, current record)]. Keeps the skills that existed at
    commit rank to_rank, each with its record AS OF that commit (def_key,
    commit, description). Same rules as the window filter in _search_skills."""
    if not rows:
        return []
    pipe = org_redis.pipeline(transaction=False)
    for _sid, sk in rows:
        pipe.zrank("commit_order", sk.get("created_commit") or "__none__")
        pipe.zrank("commit_order", sk.get("obsoleted_commit") or "__none__")
        pipe.zrank("commit_order", sk.get("commit_hash") or "__none__")
    ranks = pipe.execute()
    out = []
    for i, (sid, sk) in enumerate(rows):
        cr, obr, cur = ranks[3 * i], ranks[3 * i + 1], ranks[3 * i + 2]
        if cr is not None and cr > to_rank:
            continue               # created after that commit
        if obr is not None and obr <= to_rank:
            continue               # deleted at or before that commit
        if cur is not None and cur > to_rank:
            # Changed after that commit: take the version that was current then.
            sk = skills_lib.get_skill_as_of(org_redis, sid, to_rank)
            if sk is None or sk.get("_as_of_warning"):
                continue           # no version from that time is stored
        out.append((sid, sk))
    return out


def _jev_select(question: str, org_redis,
                only_ids: Optional[list[str]] = None,
                as_of: Optional[dict] = None) -> tuple[list[dict], dict]:
    """TEST ARM (vector_store="jev"): score EVERY active atomic skill against
    the question with Jev (description + code) and keep the ones at or above
    JEV_MIN_SCORE, best first. No fixed top-K: the set is as large as the
    question needs, bounded by JEV_MAX_SKILLS and JEV_MAX_CHARS.
    as_of given: only skills that existed at as_of["to_rank"] are scored,
    each on the body it had at that commit.
    Returns (skills in _search_skills shape, info)."""
    min_score  = float(os.environ.get("JEV_MIN_SCORE", "2.0"))
    max_skills = int(os.environ.get("JEV_MAX_SKILLS", "60"))
    max_chars  = int(os.environ.get("JEV_MAX_CHARS", "300000"))
    workers    = int(os.environ.get("JEV_CONCURRENCY", "128"))
    t0 = time.time()

    if only_ids is not None:
        ids = [i for i in only_ids if not i.startswith("~")]   # pre-selected set
    elif as_of is not None:
        # Every skill that ever existed; the window check below keeps the
        # ones that existed at the range's last commit.
        ids = [i for i in (_decode_set(org_redis.smembers("skills_active"))
                           | _decode_set(org_redis.smembers("skills_obsolete")))
               if not i.startswith("~")]
    else:
        ids = [i for i in _decode_set(org_redis.smembers("skills_active"))
               if not i.startswith("~")]
    cands: list[dict] = []
    for start in range(0, len(ids), 500):
        part = ids[start:start + 500]
        batch = []
        rows = [(sid, json.loads(raw)) for sid, raw in
                zip(part, org_redis.mget([f"skill:{i}" for i in part])) if raw]
        if as_of is not None:
            rows = _jev_rows_as_of(org_redis, rows, as_of["to_rank"])
        for sid, sk in rows:
            if sk.get("is_composite", False):
                continue
            if as_of is None and sk.get("isObsolete", False):
                continue           # no range: live skills only
            dk = sk.get("def_key") or ""
            p = skills_lib.parse_def_key(dk)
            if p:
                batch.append((sid, sk, dk, p))
        pipe = org_redis.pipeline(transaction=False)
        for _sid, sk, dk, _p in batch:
            if as_of is not None and sk.get("commit_hash"):
                # The body stored for the version that was current then.
                pipe.hget(f"code_at:{sk['commit_hash']}:{dk}", "body")
            else:
                pipe.hget(f"code:{dk}", "body")
        for (sid, sk, dk, p), body in zip(batch, pipe.execute()):
            body = (body.decode() if isinstance(body, bytes) else body) or ""
            if not body and as_of is not None:
                # No per-commit copy stored: same fallback as get_code_as_of.
                body = skills_lib.get_code(org_redis, dk)
            cands.append({"sid": sid, "sk": sk, "dk": dk, "p": p, "body": body})

    client = httpx.Client(
        timeout=60,
        limits=httpx.Limits(max_connections=workers,
                            max_keepalive_connections=workers),
        headers={"Authorization":
                 f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}"})

    def _score(c: dict) -> None:
        payload = {
            "model": JEV_MODEL,
            "state": _strip_desc({
                "file": c["p"][0], "symbol": c["p"][1],
                "description": c["sk"].get("description_of_skill", ""),
                "code": c["body"][:int(os.environ.get("JEV_BODY_MAX_CHARS", "60000"))],
            }),
            "questions": {"rel": {
                "type": "score",
                "instructions": ("How relevant is this piece of code (`code`) "
                                 "for answering this question about the "
                                 f"codebase: {question}"
                                 if _no_desc() else
                                 "How relevant is this piece of code (`code`, "
                                 "described in `description`) for answering this "
                                 f"question about the codebase: {question}"),
                "criteria": [
                    "Not relevant: has nothing to do with the question",
                    "Loosely related: same area of the codebase, but does not help answer the question",
                    "Relevant: it is part of a mechanism the question asks about",
                    "Directly relevant: this code itself does what the question asks about",
                ],
            }},
        }
        c["score"], c["cost"] = None, 0.0
        for attempt in range(4):
            try:
                res = client.post(JEV_URL, json=payload)
            except httpx.HTTPError as e:
                c["err"] = f"{type(e).__name__}: {_scrub(str(e))[:200]}"
                time.sleep(2 ** attempt)
                continue
            if res.status_code == 429 or res.status_code >= 500:
                if attempt == 0:
                    print(f"⏳ Jev select call got HTTP {res.status_code}, retrying")
                time.sleep(2 ** attempt)
                continue
            try:
                data = res.json()
            except ValueError:
                c["err"] = f"HTTP {res.status_code}, not JSON: {res.text[:200]}"
                return
            ans = (data.get("answers") or {}).get("rel") or {}
            if res.status_code == 200 and "score" in ans:
                c.pop("err", None)
                c["score"] = float(ans["score"])
                c["cost"] = float((data.get("usage") or {}).get("cost") or 0)
            else:
                c["err"] = f"HTTP {res.status_code} {res.text[:200]}"
            return

    try:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(_score, cands))
    finally:
        client.close()

    scored = [c for c in cands if c["score"] is not None]
    _errs = [c["err"] for c in cands if c.get("err")]
    if _errs:
        print(f"⚠️  Jev select: {len(_errs)} call(s) failed. First: {_scrub(_errs[0])}")
    above = sorted((c for c in scored if c["score"] >= min_score),
                   key=lambda c: -c["score"])
    _sg = globals().get("_split_guard")      # present only if the guard diffs are applied
    out, used = [], 0
    for c in above:
        if len(out) >= max_skills or used > max_chars:
            break
        guard, code = _sg(c["body"]) if _sg else ("", c["body"])
        used += len(code)
        out.append({
            "skill_id":      c["sid"],
            "def_key":       c["dk"],
            "name":          c["sk"].get("skill_name", c["sid"]),
            "description":   ("" if _no_desc()
                              else c["sk"].get("description_of_skill", "")),
            "file_path":     c["p"][0],
            "symbol":        c["p"][1],
            "suggested":     False,
            "is_obsolete":   bool(c["sk"].get("isObsolete", False)),
            "reconstructed": bool(c["sk"].get("_as_of_reconstructed", False)),
            "code":          code,
            "guard":         guard,
            "score":         round(c["score"], 2),
            "is_composite":  False,
        })
    info = {
        "candidates": len(cands), "scored": len(scored),
        "failed": len(cands) - len(scored), "above": len(above),
        "kept": len(out), "min_score": min_score,
        "cost": round(sum(c["cost"] for c in cands), 4),
        "secs": round(time.time() - t0, 1),
    }
    return out, info


_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")




_JEV_VERDICTS = {
    "accept":   "Yes, this helps answer the question.",
    "continue": "Inconclusive. It may lead to something that helps.",
    "reject":   "No, this is a dead end.",
}


def _fmt_probs(probs) -> str:
    return " ".join(f"{k}={float(v):.2f}" for k, v in (probs or {}).items())


def _jev_verdict(client, state: dict, instructions: str):
    """One Jev choice call: accept / continue / reject.
    Returns (verdict or None, probability per verdict, cost)."""
    payload = {"model": JEV_MODEL, "state": state,
               "questions": {"v": {"type": "choice",
                                   "instructions": instructions,
                                   "criteria": _JEV_VERDICTS}}}
    last_err = None
    for attempt in range(4):
        try:
            res = client.post(JEV_URL, json=payload)
        except httpx.HTTPError as e:
            last_err = e
            time.sleep(2 ** attempt)
            continue
        if res.status_code == 429 or res.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        try:
            data = res.json()
        except ValueError:
            return None, {}, 0.0
        ans = (data.get("answers") or {}).get("v") or {}
        if res.status_code == 200 and ans.get("choice") in _JEV_VERDICTS:
            return (ans["choice"], ans.get("probabilities") or {},
                    float((data.get("usage") or {}).get("cost") or 0))
        print(f"⚠️  Jev verdict call failed: HTTP {res.status_code} "
              f"{_scrub(res.text[:200])}")
        return None, {}, 0.0
    print(f"⚠️  Jev verdict gave up after 4 tries ({_scrub(str(last_err))})")
    return None, {}, 0.0


_JUDGE_SYSTEM = ("You judge one piece of code for an investigation of a "
                 "codebase. Answer only with JSON.")


def _llm_verdict(target, question: str, chain: str, why: str,
                 file: str, symbol: str, code: str):
    """One call to the LLM: does this code help answer the question?
    Returns (verdict or None, names to follow, one-line reason,
    (tokens in, tokens out))."""
    if target is None:
        return None, [], "", (0, 0)
    user = (
        f"QUESTION:\n{question}\n\n"
        f"FOUND SO FAR:\n{chain}\n\n"
        f"HOW THIS CODE WAS REACHED:\n{why}\n\n"
        f"FILE: {file}\nSYMBOL: {symbol}\nCODE:\n{code}\n\n"
        "Does this code help answer the question?\n"
        '- "accept": yes, this helps answer the question.\n'
        '- "continue": inconclusive. It may lead to something that helps.\n'
        '- "reject": no, this is a dead end.\n\n'
        'If the verdict is accept or continue, put in "follow" up to 5 names '
        "from this code (identifiers, file names, option names) that should "
        "be searched next to get closer to the answer. Copy each name exactly "
        "as it is written in the code. Use an empty list if there is none.\n\n"
        'JSON only: {"verdict": "accept" | "continue" | "reject", '
        '"follow": ["..."], "reason": "<one short sentence>"}')
    for attempt in range(5):
        try:
            resp = litellm.completion(
                model=target.model, api_key=target.api_key,
                api_base=target.api_base, max_tokens=400, temperature=0.0,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": _JUDGE_SYSTEM},
                          {"role": "user", "content": user}],
                **{**(target.extra_params or {}), **_no_think_params(target)})
        except (litellm.RateLimitError, litellm.ServiceUnavailableError,
                litellm.InternalServerError):
            time.sleep(min(2 ** attempt * 2, 30))
            continue
        except Exception as e:
            print(f"⚠️  judge call failed: {_scrub(str(e))[:200]}")
            return None, [], "", (0, 0)
        u = getattr(resp, "usage", None)
        toks = ((u.prompt_tokens or 0), (u.completion_tokens or 0)) if u else (0, 0)
        try:
            d = json.loads(resp.choices[0].message.content or "{}")
        except (json.JSONDecodeError, TypeError):
            return None, [], "", toks
        v = str(d.get("verdict", "")).strip().lower()
        if v not in ("accept", "continue", "reject"):
            return None, [], "", toks
        follow = []
        for x in (d.get("follow") or []):
            x = x.strip() if isinstance(x, str) else ""
            # keep a name only if it really is in the judged code
            if len(x) >= 3 and x in code and x not in follow:
                follow.append(x)
        return (v, follow[:5] if v != "reject" else [],
                str(d.get("reason", ""))[:200], toks)
    return None, [], "", (0, 0)


def _jev_excerpt(body: str, hit: Optional[int], cap: int) -> tuple[str, bool]:
    """Whole body when it fits Jev's input. Else the biggest part around the
    link line that fits (or the head when there is no link line)."""
    if len(body) <= cap:
        return body, False
    if hit is None:
        return body[:cap], True
    lines = body.splitlines()
    lo = hi = hit
    size = len(lines[hit]) + 1
    while True:
        grew = False
        if lo > 0 and size + len(lines[lo - 1]) + 1 <= cap:
            lo -= 1
            size += len(lines[lo]) + 1
            grew = True
        if hi < len(lines) - 1 and size + len(lines[hi + 1]) + 1 <= cap:
            hi += 1
            size += len(lines[hi]) + 1
            grew = True
        if not grew:
            break
    return "\n".join(lines[lo:hi + 1])[:cap], True


def _settle(verdict, probs):
    """Jev's label, except: a reject it is not sure about becomes continue."""
    sure = float(os.environ.get("JEV_SURE_REJECT", "0.75"))
    if verdict == "reject" and float((probs or {}).get("reject", 0)) < sure:
        return "continue"
    return verdict

def _no_desc() -> bool:
    """TEST (JEV_NO_DESC=1): the Jev path runs without the stored
    LLM descriptions."""
    return os.environ.get("JEV_NO_DESC", "1") == "1"


def _strip_desc(state: dict) -> dict:
    """Under JEV_NO_DESC, take the description fields out of a Jev state."""
    if _no_desc():
        state.pop("description", None)
    return state

def _prev_steps(c: dict, cap: int) -> str:
    """The earlier steps of a chain, for Jev.
    Normal: one description line per step.
    Under JEV_NO_DESC: their code, newest step first, in the room that is
    left next to the candidate's own code. A body that does not fit whole
    is given as the part around its link line."""
    if not _no_desc():
        return "\n".join(f"- {lab}: {d}" for lab, d in c["prev"])
    room = cap - len(c.get("excerpt") or "")
    parts: list[str] = []
    for label, body, hit in reversed(c.get("prev_code") or []):
        head = f"### {label}\n"
        left = room - len(head) - 80
        if left < 500:
            break                      # the room is used up
        piece, cut = _jev_excerpt(body, hit, left)
        parts.append(head + piece
                     + ("\n… [part of the body: the rest did not fit] …"
                        if cut else "") + "\n")
        room -= len(parts[-1])
    return "\n".join(reversed(parts)) or "(none)"


def _led_to(led: list[dict], room: int) -> str:
    """What a step led to, for Jev.
    Normal: one description line each.
    Under JEV_NO_DESC: the code of each while it fits in `room`
    characters; the rest are listed by name."""
    if not led:
        return "(nothing further was found from here)"
    if not _no_desc():
        return "\n".join(
            f"- `{o['symbol']}` in {o['file']}: {o.get('desc') or ''}"
            for o in led)
    parts, names = [], []
    for o in led:
        code = o.get("excerpt") or o.get("body") or ""
        block = f"### `{o['symbol']}` in {o['file']}\n{code}\n"
        if code and len(block) <= room:
            parts.append(block)
            room -= len(block)
        else:
            names.append(f"- `{o['symbol']}` in {o['file']}")
    if names:
        parts.append("Also led to (code not shown, no room left):\n"
                     + "\n".join(names))
    return "\n".join(parts)



def _fill_descriptions(org_redis, nodes: list[dict]) -> None:
    """Put the stored skill description on each node (key 'desc'), read from
    Redis by the node's address. Nodes that already have one are left alone."""
    if _no_desc():
        for n in nodes:
            n["desc"] = ""        # test: no stored descriptions
        return
    todo = [n for n in nodes if not n.get("desc")]
    if not todo:
        return
    try:
        pipe = org_redis.pipeline(transaction=False)
        for n in todo:
            pipe.lrange(f"symbol:{n['file']}:{n['symbol']}:{n['line']}:"
                        f"{n['struct']}", 0, -1)
        sids = []
        for ids in pipe.execute():
            sid = ids[-1] if ids else ""
            sids.append(sid.decode() if isinstance(sid, bytes) else sid)
        vals = org_redis.mget([f"skill:{s}" for s in sids])
        for n, raw in zip(todo, vals):
            n["desc"] = (json.loads(raw).get("description_of_skill", "")
                         if raw else "")
    except Exception as e:
        print(f"⚠️  description lookup failed (non-fatal): {_scrub(str(e))}")
        for n in todo:
            n.setdefault("desc", "")


def _name_pool(org_redis, c: dict) -> list[str]:
    """The names in a body that Jev may pick to search next. These are the
    names the code used to follow blindly: names near the link that are
    defined symbols, and for whole-file bodies also long names with an
    underscore that are not symbols (build switches, option names)."""
    window = int(os.environ.get("JEV_EXPAND_WINDOW", "10"))
    max_defs = int(os.environ.get("JEV_EXPAND_MAX_DEFS", "4"))
    pool_max = int(os.environ.get("JEV_FOLLOW_POOL", "40"))
    body = c.get("body") or ""
    lines = body.splitlines()
    if c.get("hit") is not None:
        near = "\n".join(lines[max(0, c["hit"] - window): c["hit"] + window + 1])
    else:
        near = body[:20000]
    sym = c.get("symbol") or ""
    own = sym if sym and not sym.startswith("<") else ""
    toks: list[str] = []
    for t in _NAME_RE.findall(near):
        if t != own and t not in toks:
            toks.append(t)
    toks = toks[:200]
    if not toks:
        return []
    try:
        pipe = org_redis.pipeline(transaction=False)
        for t in toks:
            pipe.scard(f"symbol_name:{t}")
        counts = [int(x or 0) for x in pipe.execute()]
    except Exception as e:
        print(f"⚠️  name pool lookup failed (non-fatal): {_scrub(str(e))}")
        return []
    whole = c.get("struct") in ("module", "blob") or sym.startswith("<")
    return [t for t, k in zip(toks, counts)
            if (1 <= k <= max_defs)
            or (whole and k == 0 and "_" in t and len(t) >= 6)][:pool_max]


_NONE_NAME = "(none of these)"


def _names_as_choice() -> bool:
    """JEV_NAMES_AS_CHOICE=1: the names of a body are offered to Jev as ONE
    choice question (a distribution over the names plus "none of these")
    instead of one yes/no question per name. Same decision, far fewer
    tokens per call."""
    return os.environ.get("JEV_NAMES_AS_CHOICE", "0") == "1"


def _picked(picks: dict) -> list[str]:
    """Names Jev said yes to, best first. With independent yes/no answers
    a name is followed at JEV_FOLLOW_MIN. With one choice over the names
    the probabilities share one distribution, so a name is followed when
    it beats "none of these" and has at least half the best name's
    share — the same relative reading the hit triage uses."""
    if _NONE_NAME in picks:
        none_p = float(picks.get(_NONE_NAME) or 0)
        names = {n: p for n, p in picks.items() if n != _NONE_NAME}
        if not names:
            return []
        top = max(names.values())
        return [n for n, p in sorted(names.items(), key=lambda t: -t[1])
                if p > none_p and p >= 0.5 * top]
    cut = float(os.environ.get("JEV_FOLLOW_MIN", "0.5"))
    return [n for n, p in sorted(picks.items(), key=lambda t: -t[1]) if p >= cut]


def _fmt_picks(picks: dict) -> str:
    top = sorted(picks.items(), key=lambda t: -t[1])[:10]
    return (" names: " + " ".join(f"{n}={p:.2f}" for n, p in top)) if top else ""


def _jev_triage_hits(client, state: dict, hits: list[dict], around: int = 3):
    """One Jev call over the places a followed name was found, before any of
    them is read in full: like a developer scanning search results. `state`
    carries the question, the chain so far and the name. Each hit is shown
    as its coordinates, how the name occurs there, and the lines around the
    occurrence. Returns ({index: probability that opening it helps}, cost);
    an empty dict means the call failed (the caller then opens everything,
    as without triage)."""
    shown = []
    for i, c in enumerate(hits):
        bl = (c.get("body") or "").splitlines()
        h = c.get("hit")
        if h is None:
            ctx = "\n".join(bl[:around * 2])
        else:
            lo, hi = max(0, h - around), min(len(bl), h + around + 1)
            ctx = "\n".join(f"{c['line'] + j}: {bl[j]}" for j in range(lo, hi))
        shown.append(f"[{i}] {c['file']}:{c['symbol']}:{c['line']} ({c.get('struct') or '?'}) "
                     f"— {c.get('why') or ''}\n{ctx}")
    questions = {}
    for i in range(len(hits)):
        questions[f"h{i}"] = {
            "type": "noul",
            "instructions": (f"Would reading the whole body of place [{i}] in `places` "
                             "help answer the `question`, given what is "
                             "`already_established`? A test, an example or another "
                             "platform's copy of the same function helps only if the "
                             "question is about that."),
        }
    payload = {"model": JEV_MODEL,
               "state": {**state, "places": "\n\n".join(shown)},
               "questions": questions}
    last_err = None
    for attempt in range(4):
        try:
            res = client.post(JEV_URL, json=payload)
        except httpx.HTTPError as e:
            last_err = e
            time.sleep(2 ** attempt)
            continue
        if res.status_code == 429 or res.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        try:
            data = res.json()
        except ValueError:
            return {}, 0.0
        if res.status_code != 200:
            print(f"⚠️  Jev triage failed: HTTP {res.status_code} {_scrub(res.text[:200])}")
            return {}, 0.0
        answers = data.get("answers") or {}
        probs = {}
        for i in range(len(hits)):
            a = answers.get(f"h{i}") or {}
            if a.get("noul") is not None:
                probs[i] = float(a["noul"])
        return probs, float((data.get("usage") or {}).get("cost") or 0)
    print(f"⚠️  Jev triage gave up after 4 tries ({_scrub(str(last_err))}); opening every place")
    return {}, 0.0


def _jev_verdict_names(client, state: dict, instructions: str,
                       names: list[str]):
    """One Jev call, two kinds of questions on the same body: the
    accept/continue/reject verdict, and one yes/no per name (should this
    name be searched next?). Returns (verdict or None, verdict
    probabilities, cost, {name: probability of yes})."""
    questions = {"v": {"type": "choice", "instructions": instructions,
                       "criteria": _JEV_VERDICTS}}
    as_choice = _names_as_choice() and bool(names)
    if as_choice:
        # One question: which name from `code` should be searched next?
        # Jev returns a probability for every option; _picked() reads them.
        questions["names"] = {
            "type": "choice",
            "instructions": ("Which name from `code` should be searched next "
                             "to get closer to answering the `question`? "
                             "Pick \"(none of these)\" if no name is worth "
                             "following."),
            "criteria": {**{name: f'search "{name}" next' for name in names},
                         _NONE_NAME: "no name here is worth searching"},
        }
    else:
        for i, name in enumerate(names):
            # the name goes in quotes: backticks would be read as a state field
            questions[f"n{i}"] = {
                "type": "noul",
                "instructions": (f'Should the name "{name}" from `code` be '
                                 "searched next to get closer to answering the "
                                 "`question`?"),
            }
    payload = {"model": JEV_MODEL, "state": state, "questions": questions}
    last_err = None
    for attempt in range(4):
        try:
            res = client.post(JEV_URL, json=payload)
        except httpx.HTTPError as e:
            last_err = e
            time.sleep(2 ** attempt)
            continue
        if res.status_code == 429 or res.status_code >= 500:
            if attempt == 0:
                print(f"⏳ Jev chain call got HTTP {res.status_code}, retrying")
            time.sleep(2 ** attempt)
            continue
        try:
            data = res.json()
        except ValueError:
            return None, {}, 0.0, {}
        answers = data.get("answers") or {}
        ans = answers.get("v") or {}
        if res.status_code == 200 and ans.get("choice") in _JEV_VERDICTS:
            picks = {}
            if as_choice:
                probs = (answers.get("names") or {}).get("probabilities") or {}
                picks = {n: float(p) for n, p in probs.items()
                         if n in names or n == _NONE_NAME}
            else:
                for i, name in enumerate(names):
                    a = answers.get(f"n{i}") or {}
                    if a.get("noul") is not None:
                        picks[name] = float(a["noul"])
            return (ans["choice"], ans.get("probabilities") or {},
                    float((data.get("usage") or {}).get("cost") or 0), picks)
        print(f"⚠️  Jev verdict call failed: HTTP {res.status_code} "
              f"{_scrub(res.text[:200])}")
        return None, {}, 0.0, {}
    print(f"⚠️  Jev chain call gave up after 4 tries: candidate dropped ({_scrub(str(last_err))})")
    return None, {}, 0.0, {}



def _jev_expand(question: str, org_redis, seeds: list[dict],
                budget: Optional[int] = None,
                max_add: Optional[int] = None,
                memory=None,
                as_of: Optional[dict] = None,
                spread: bool = False,
                chains: int = 0) -> tuple[list[dict], dict]:
    """TEST (JEV_EXPAND=1): follow names outward from the skills Jev kept.
    chains > 0 is the narrow mode of the fast probe: one Jev call picks the
    `chains` best names of the start code. Each name starts one chain. A
    chain then makes one search and one Jev call per step. No second look
    at the end. Jev calls: 1 + chains x JEV_EXPAND_MAX_HOPS at most.
    For every accepted piece of code, code collects (a) who mentions its file
    name or symbol, (b) for whole-file bodies, who mentions the names next to
    the link, (c) the definitions of the names it uses. Jev scores each
    candidate knowing how it was reached; accepted ones are expanded again.
    Stops when nothing new is accepted or the budget is spent.
    Returns (extra skills in _search_skills shape, info)."""
    min_score = float(os.environ.get("JEV_EXPAND_MIN_SCORE", "2.0"))
    budget    = budget or int(os.environ.get("JEV_EXPAND_BUDGET", "300"))     # Jev calls
    max_add   = max_add or int(os.environ.get("JEV_EXPAND_MAX_ADD", "60"))
    max_chars = int(os.environ.get("JEV_EXPAND_MAX_CHARS", "250000"))
    max_hits  = int(os.environ.get("JEV_EXPAND_MAX_HITS", "25"))    # more hits = name is everywhere
    max_defs  = int(os.environ.get("JEV_EXPAND_MAX_DEFS", "4"))
    per_node  = int(os.environ.get("JEV_EXPAND_PER_NODE", "30"))
    window    = int(os.environ.get("JEV_EXPAND_WINDOW", "10"))      # lines around a link
    body_cap  = int(os.environ.get("JEV_BODY_MAX_CHARS", "60000"))
    t0 = time.time()
    greps = 0
    _ranks: dict = {}      # commit → rank, shared by this chain's greps
    grep_cache: dict[str, Optional[dict]] = (
        memory.grep_cache if memory is not None else {})

    want: Optional[set] = None      # a set = only note the names, search nothing
    _glock = threading.Lock()

    def _grep(name: str):
        nonlocal greps
        if want is not None:
            want.add(name)
            return None
        if name not in grep_cache:
            with _glock:
                greps += 1
            try:
                grep_cache[name] = skills_lib.grep_code_ft(
                    org_redis, pattern=name, is_regex=False, file=None,
                    struct_types=None, max_results=max_hits + 1,
                    include_hist=as_of is not None, as_of=as_of,
                    rank_cache=_ranks)
            except Exception as e:
                print(f"⚠️  expand grep `{name}` failed: {_scrub(str(e))}")
                grep_cache[name] = None
            if memory is not None:
                memory.note_word(name, "system",
                                 (grep_cache[name] or {}).get("total_matched", 0))
        return grep_cache[name]

    def _mentions(name: str, why: str) -> list[dict]:
        res = _grep(name)
        if not res or res.get("total_matched", 0) > max_hits:
            return []                          # the name is everywhere: it links nothing
        out = []
        for r in res.get("rows", []):
            if r.get("post_range_body") or r.get("provenance_unresolved"):
                continue               # not the state at the probed commit
            note = ""
            if r.get("pre_range_version") and not r.get("state_verified"):
                note = (" [⚠ this version is older than the report range: "
                        "a lead, not evidence]")
            if r.get("removed_by_probed"):
                note = (" [removed by the probed commit: this is the state "
                        "before it]")
            rb = r.get("body") or ""
            hit = next((i for i, ln in enumerate(rb.splitlines()) if name in ln), None)
            out.append({"file": r.get("file", ""), "symbol": r.get("symbol", ""),
                        "line": int(r.get("line", 0) or 0),
                        "struct": r.get("struct_type", ""),
                        "body": rb, "hit": hit, "why": why + note})
        return out

    def _defs(name: str) -> list[dict]:
        """Definitions of a name. Under a window, the body is the one stored
        as of the probed commit."""
        if want is not None:
            return []
        keys = _decode_set(org_redis.smembers(f"symbol_name:{name}"))
        if as_of is not None:
            keys |= _decode_set(org_redis.smembers(f"symbol_name_hist:{name}"))
        found = []
        for sk in sorted(keys)[:max_defs]:
            dk = sk[len("symbol:"):]
            p = skills_lib.parse_def_key(dk)
            if not p:
                continue
            if as_of is None:
                body = skills_lib.get_code(org_redis, dk) or ""
            else:
                body = ""
                ids = (org_redis.lrange(sk, 0, -1)
                       + org_redis.lrange(f"symbol_hist:{dk}", 0, -1))
                for sid in reversed(ids):
                    sid = sid.decode() if isinstance(sid, bytes) else sid
                    s = _fetch_skill_with_code(sid, org_redis,
                                               prefer_redis=True,
                                               include_obsolete=True,
                                               as_of=as_of)
                    if s and s.get("code") and not s.get("removed_by_probed"):
                        body = s.get("code_raw") or s["code"]
                        p = skills_lib.parse_def_key(s.get("def_key") or "") or p
                        break
            if body:
                found.append({"file": p[0], "symbol": p[1], "line": int(p[2]),
                              "struct": p[3], "body": body})
        return found

    def _candidates(n: dict) -> list[dict]:
        body = n["body"] or ""
        lines = body.splitlines()
        if n["hit"] is not None:
            near = "\n".join(lines[max(0, n["hit"] - window): n["hit"] + window + 1])
        else:
            near = body[:20000]
        base = os.path.basename(n["file"] or "")
        own = n["symbol"] if n["symbol"] and not n["symbol"].startswith("<") else ""
        out: list[dict] = []

        if chains and n.get("follow") is not None:
            # Narrow mode. The start code opens `chains` chains, a later
            # step continues its own chain with 1. Names are tried best
            # first. A name gives one place: the first one that has a body
            # and was not reached before. A name that gives no place is
            # skipped; at most 3 names are tried for each place needed.
            need = chains if n.get("start") else 1
            picked: list[dict] = []
            for name in list(n["follow"])[:need * 3]:
                if len(picked) >= need:
                    break
                got = _mentions(name, f"it mentions `{name}`, a name the "
                                      "judge chose to follow")
                if not got:
                    got = [{**d, "hit": None,
                            "why": f"it defines `{name}`, a name the "
                                   "judge chose to follow"}
                           for d in _defs(name)]
                took = None
                for c in got:
                    k = (c["file"], c["symbol"], c["line"])
                    if c.get("body") and k not in seen and k not in claimed:
                        claimed.add(k)
                        picked.append(c)
                        took = c
                        break
                decisions.append({
                    "kind": "search", "step": hops + 1, "name": name,
                    "from": f"`{n['symbol']}` in {n['file']}",
                    "hits": int(((grep_cache.get(name) or {})
                                 .get("total_matched", 0)) or 0),
                    "places": len(got),
                    "took": (f"`{took['symbol']}` in {took['file']}"
                             if took else "")})
            return list(n.get("extra") or []) + picked

        # (a) who mentions this file or this symbol
        for name in (base, own):
            if name and len(name) >= 4:
                out += _mentions(name, f"it mentions `{name}`")

        # Names the judge chose to follow come first, and replace the blind
        # picks below. Seeds from the start selection have no such list.
        if n.get("follow") is not None:
            groups: list[list[dict]] = []
            for name in n["follow"]:
                got = _mentions(name, f"it mentions `{name}`, a name the "
                                      "judge chose to follow")
                if not got:
                    # too many mentions to follow: take its definitions
                    got = [{**d, "hit": None,
                            "why": f"it defines `{name}`, a name the "
                                   "judge chose to follow"}
                           for d in _defs(name)]
                if got:
                    groups.append(got)
            if spread:
                # one candidate per followed name in turn, so one common
                # name cannot take every slot
                depth = max((len(g) for g in groups), default=0)
                chosen = [g[i] for i in range(depth) for g in groups
                          if i < len(g)]
            else:
                chosen = [c for g in groups for c in g]
            # candidates handed in with the seed (composite members) go first
            return list(n.get("extra") or []) + (chosen + out)[:per_node]

        toks: list[str] = []
        for t in _NAME_RE.findall(near):
            if t != own and t not in toks:
                toks.append(t)
        toks = toks[:200]
        counts = []
        if toks:
            pipe = org_redis.pipeline(transaction=False)
            for t in toks:
                pipe.scard(f"symbol_name:{t}")
            counts = [int(c or 0) for c in pipe.execute()]

        # (b) whole-file bodies: names next to the link that are not symbols
        #     (build switches, option names) -> who else mentions them
        if n["struct"] in ("module", "blob") or (n["symbol"] or "").startswith("<"):
            plain = [t for t, c in zip(toks, counts)
                     if c == 0 and "_" in t and len(t) >= 6][:12]
            for name in plain:
                out += _mentions(name, f"it mentions `{name}`, a name used next to that link")

        # (c) names used here that are defined symbols -> their definitions.
        # Looked up 16 at a time, and only until this node's list is full.
        wanted = [t for t, c in zip(toks, counts) if 1 <= c <= max_defs]
        i = 0
        while want is None and i < len(wanted) and len(out) < per_node:
            chunk = wanted[i:i + 16]
            i += 16
            with ThreadPoolExecutor(max_workers=len(chunk)) as ex:
                found = list(ex.map(_defs, chunk))
            for t, defs in zip(chunk, found):
                for d in defs:
                    out.append({**d, "hit": None,
                                "why": f"it defines `{t}`, which is used there"})
        return out[:per_node]

    def _excerpt(body: str, hit: Optional[int]) -> tuple[str, bool]:
        return _jev_excerpt(body, hit, body_cap)

    level: list[dict] = []
    # Per-seed diagnostic: what each start body cost in chain calls and
    # what it produced. Filled as the hops run, reported in info["per_seed"].
    per_seed: list[dict] = []
    for i, s in enumerate(seeds):
        p = skills_lib.parse_def_key(s.get("def_key") or "")
        per_seed.append({"file": s.get("file_path", ""),
                         "symbol": s.get("symbol", ""),
                         "score": s.get("score"),
                         "calls": 0, "cost": 0.0, "accepted": 0, "leads": 0})
        level.append({
            "root_i": i,
            "file": s.get("file_path", ""), "symbol": s.get("symbol", ""),
            "line": int(p[2]) if p else 0, "struct": p[3] if p else "",
            "body": s.get("code") or "", "hit": s.get("hit"),
            "chain": s.get("chain") or (
                f"`{s.get('symbol') or s.get('name')}` in "
                f"{s.get('file_path', '')} was judged relevant to the question"),
            "trail": [f"`{s.get('symbol') or s.get('name')}` in "
                      f"{s.get('file_path', '')}"],
            "follow": s.get("follow"),
            "extra": s.get("extra"),
            "desc": s.get("description") or "",
            "start": True,
        })
    _fill_descriptions(org_redis, level)
    seen = {(n["file"], n["symbol"], n["line"]) for n in level}
    claimed: set = set()       # narrow mode: places already given to a chain
    # For the evidence record: every decision of this step, in order.
    # kind "start": the names Jev scored on the start code and the ones
    # that opened a chain. kind "search": one searched name, its hit count
    # and the place taken from it. kind "read": one place Jev judged, with
    # its verdict and the names it chose next. kind "second_look": the
    # final judgment of an open step in the wide mode.
    decisions: list[dict] = []
    by_key: dict = {}          # every candidate that was judged, by address

    instructions = "Does this `code` help answer the `question`?"

    def _link(c: dict) -> str:
        """The matching line of a candidate, with one line around it."""
        if c.get("hit") is None:
            return ""
        bl = c["body"].splitlines()
        return " | ".join(x.strip()
                          for x in bl[max(0, c["hit"] - 1): c["hit"] + 2]
                          if x.strip())[:300]

    client = httpx.Client(
        timeout=60,
        limits=httpx.Limits(max_connections=256, max_keepalive_connections=256),
        headers={"Authorization":
                 f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}"})
    max_hops = int(os.environ.get("JEV_EXPAND_MAX_HOPS", "4"))
    judge_target = memory.target if memory is not None else None
    use_llm_judge = os.environ.get("CHAIN_JUDGE", "jev") == "llm"
    # Jev takes hundreds of calls at once; the LLM judge keeps the low limit
    judge_workers = int(os.environ.get("JUDGE_CONCURRENCY", "16")
                        if use_llm_judge
                        else os.environ.get("JEV_CONCURRENCY", "64"))
    tok_in = tok_out = 0
    triage_calls = triage_skipped = 0
    added: list[dict] = []    # accept: the body goes to the context
    held: list[dict] = []     # continue, or accept that did not fit: one-line lead
    used = scored = hops = 0
    cost = 0.0
    try:
        if chains and not use_llm_judge:
            # Narrow mode, the first call: Jev scores every name of the
            # start code. The best `chains` names start the chains.
            for n in level:
                if not n.get("follow") or not n.get("body"):
                    continue
                _ex, _cut = _excerpt(n["body"], n["hit"])
                _v, _p, _c, picks = _jev_verdict_names(
                    client, {"question": question, "file": n["file"],
                             "symbol": n["symbol"], "code": _ex},
                    instructions, list(n["follow"]))
                scored += 1
                cost += _c or 0
                if n.get("root_i") is not None:
                    per_seed[n["root_i"]]["calls"] += 1
                    per_seed[n["root_i"]]["cost"] += _c or 0
                if picks:
                    n["follow"] = [name for name, _pr in sorted(
                        picks.items(), key=lambda t: -t[1]) if name != _NONE_NAME]
                decisions.append({
                    "kind": "start", "step": 0,
                    "from": f"`{n['symbol']}` in {n['file']}",
                    "scored": {k: round(float(v), 2) for k, v in sorted(
                        picks.items(), key=lambda t: -t[1])},
                    "chosen": list(n["follow"])[:chains],
                    "call_failed": not picks})
                print(f"🌱 chain start `{n['symbol']}`: {len(picks)} names "
                      f"scored, first {chains} start a chain —"
                      + _fmt_picks(picks))
        # budget is per hop, so a chain can go deeper than one hop
        while level and hops < max_hops and len(added) < max_add and used < max_chars:
            # All names of this hop are known now: note them, search the
            # new ones together, then build the candidates from the cache.
            want = None if chains else set()
            for n in ([] if chains else level):
                _candidates(n)
            _new = [x for x in (want or ()) if x not in grep_cache]
            want = None
            if _new:
                with ThreadPoolExecutor(max_workers=int(
                        os.environ.get("JEV_GREP_CONCURRENCY", "16"))) as ex:
                    list(ex.map(_grep, _new))
            per = [_candidates(n) for n in level]
            cands: list[dict] = []
            # one candidate per node in turn, so every node gets a share of the budget
            for i in range(per_node):
                for n, lst in zip(level, per):
                    if i >= len(lst):
                        continue
                    c = lst[i]
                    k = (c["file"], c["symbol"], c["line"])
                    if k in seen or not c["body"]:
                        # already reached from another step: remember the link
                        if k in by_key:
                            n.setdefault("also", []).append(by_key[k])
                        continue
                    seen.add(k)
                    by_key[k] = c
                    c["chain"] = n["chain"]
                    c["trail"] = n["trail"]
                    # every earlier step of this chain, with its description
                    c["prev"] = n.get("prev", []) + [(
                        f"`{n['symbol']}` in {n['file']}", n.get("desc") or "")]
                    # the same steps with their code (used under JEV_NO_DESC)
                    c["prev_code"] = n.get("prev_code", []) + (
                        [(f"`{n['symbol']}` in {n['file']}", n["body"],
                          n.get("hit"))] if n.get("body") else [])
                    c["parent"] = n
                    c["root_i"] = n.get("root_i")
                    cands.append(c)
            for n in level:
                n["expanded"] = True

            # Hit triage (JEV_HIT_TRIAGE, default on): a followed name found
            # in several places is first scanned in one call — coordinates and
            # the lines around each occurrence, judged against each other —
            # and only the places Jev would open are read in full.
            # Definitions and single places are read as before. Measured on
            # five open62541 questions: 3–8x fewer Jev calls, same answers.
            if os.environ.get("JEV_HIT_TRIAGE", "1") == "1" and not use_llm_judge:
                groups: dict = {}
                for c in cands:
                    m = re.search(r"it mentions `([^`]+)`", c.get("why") or "")
                    if m and c.get("hit") is not None:
                        groups.setdefault((id(c["parent"]), m.group(1)), []).append(c)
                work = [(k, g) for k, g in groups.items() if len(g) >= 2]
                dropped: set = set()

                def _triage(item):
                    (_pid, name), g = item
                    n = g[0]["parent"]
                    probs, c_ = _jev_triage_hits(client, _strip_desc({
                        "question": question,
                        "already_established": n["chain"],
                        "reached_from": f"`{n['symbol']}` in {n['file']}",
                        "following_name": name,
                    }), g)
                    if not probs:
                        return name, len(g), 0, c_, n.get("root_i")
                    cut = float(os.environ.get("JEV_FOLLOW_MIN", "0.5"))
                    skipped = 0
                    for i, c in enumerate(g):
                        c["triage_p"] = probs.get(i)
                        if probs.get(i) is not None and probs[i] < cut:
                            dropped.add(id(c)); skipped += 1
                    return name, len(g), skipped, c_, n.get("root_i")

                if work:
                    with ThreadPoolExecutor(max_workers=judge_workers) as ex:
                        results = list(ex.map(_triage, work))
                    scored += len(work)
                    triage_calls += len(work)
                    triage_skipped += sum(r[2] for r in results)
                    cost += sum(r[3] for r in results)
                    for name, total, skipped, _c, _ri in results:
                        if _ri is not None:
                            per_seed[_ri]["calls"] += 1
                            per_seed[_ri]["cost"] += _c or 0
                        print(f"🔎 triage `{name}`: {total} places, {skipped} skipped")
                        decisions.append({"kind": "triage", "step": hops + 1,
                                          "name": name, "places": total,
                                          "skipped": skipped})
                    before = len(cands)
                    cands = [c for c in cands if id(c) not in dropped]
                    print(f"🔎 triage hop {hops + 1}: {before} candidates → {len(cands)} "
                          f"to read ({len(work)} triage calls)")

            if len(cands) > budget:
                print(f"⚠️  hop {hops + 1}: {len(cands)} candidates, budget {budget}: "
                      f"{len(cands) - budget} not judged")
            cands = cands[:budget]
            if not cands:
                break
            hops += 1
            _fill_descriptions(org_redis, cands)

            def _judge(c: dict) -> None:
                c["excerpt"], c["cut"] = _excerpt(c["body"], c["hit"])
                if use_llm_judge:
                    (c["verdict"], c["follow"], c["reason"],
                     c["toks"]) = _llm_verdict(
                        judge_target, question, c["chain"], c["why"],
                        c["file"], c["symbol"], c["excerpt"])
                else:
                    state = _strip_desc({
                        "question": question,
                        "already_established": c["chain"],
                        "previous_steps": _prev_steps(c, body_cap),
                        "reached_because": c["why"],
                        "file": c["file"], "symbol": c["symbol"],
                        "description": c.get("desc") or "",
                        "code": c["excerpt"],
                    })
                    raw_v, _p, c["cost"], picks = _jev_verdict_names(
                        client, state, instructions, _name_pool(org_redis, c))
                    c["verdict"] = _settle(raw_v, _p)
                    c["probs"], c["picks"] = _p, picks
                    # the names Jev said yes to are searched in the next hop
                    c["follow"], c["toks"] = _picked(picks), (0, 0)
                    c["reason"] = (_fmt_probs(_p)
                                   + (" (not sure: continue)"
                                      if raw_v != c["verdict"] else "")
                                   + _fmt_picks(picks))

            with ThreadPoolExecutor(max_workers=judge_workers) as ex:
                list(ex.map(_judge, cands))
            scored += len(cands)
            for c in cands:
                if c.get("root_i") is not None:
                    per_seed[c["root_i"]]["calls"] += 1
                    per_seed[c["root_i"]]["cost"] += c.get("cost") or 0
            tok_in += sum(c["toks"][0] for c in cands)
            tok_out += sum(c["toks"][1] for c in cands)
            cost += sum(c.get("cost") or 0 for c in cands)
            for c in cands:
                print(f"🌱 expand hop {hops}: {c.get('verdict')} {c['file']} "
                      f"`{c['symbol']}` ({c['why']}) "
                      f"follow={c.get('follow')} — {c.get('reason')}")
                decisions.append({
                    "kind": "read", "step": hops,
                    "file": c["file"], "symbol": c["symbol"],
                    "from": f"`{c['parent']['symbol']}` in {c['parent']['file']}",
                    "reached_by": c["why"],
                    "verdict": c.get("verdict") or "",
                    "probs": {k: round(float(v), 2)
                              for k, v in (c.get("probs") or {}).items()},
                    "next_names": {k: round(float(v), 2) for k, v in sorted(
                        (c.get("picks") or {}).items(), key=lambda t: -t[1])},
                    "followed": (list(c.get("follow") or [])
                                 if c.get("verdict") in ("accept", "continue")
                                 else []),
                    "reason": "" if c.get("probs") else (c.get("reason") or ""),
                    "chars": len(c.get("excerpt") or ""),
                    "excerpt": bool(c.get("cut"))})

            # accept and continue are both followed; only reject ends a chain
            nxt: list[dict] = []
            rank = {"accept": 0, "continue": 1}
            follow = sorted((c for c in cands if c.get("verdict") in rank),
                            key=lambda c: rank[c["verdict"]])
            for c in follow:
                lk = _link(c)
                step = (f"`{c['symbol']}` in {c['file']} ({c['why']}"
                        + (f"; line: `{lk}`" if lk else "") + ")")
                c["chain"] = f"{c['chain']}; then {step}"
                c["trail"] = c["trail"] + [step]
                if (c["verdict"] == "accept" and len(added) < max_add
                        and used <= max_chars):
                    used += len(c["excerpt"])
                    added.append(c)
                else:
                    held.append(c)
                c["parent"].setdefault("kids", []).append(c)
                nxt.append(c)
            level = nxt

        # Final decision with the whole picture: every open step that was
        # followed is judged once more, now also seeing what it led to.
        again = [c for c in held if c.get("expanded") and not use_llm_judge
                 and not chains]

        def _final(c: dict) -> None:
            led = [o for o in (c.get("kids") or []) + (c.get("also") or [])
                   if o.get("verdict") in ("accept", "continue")]
            c["led_n"] = len(led)
            prev_txt = _prev_steps(c, body_cap)
            raw_v, _p, c["cost"] = _jev_verdict(client, _strip_desc({
                "question": question,
                "already_established": c["chain"],
                "previous_steps": prev_txt,
                "led_to": _led_to(led, body_cap - len(c["excerpt"])
                                  - len(prev_txt)),
                "file": c["file"], "symbol": c["symbol"],
                "description": c.get("desc") or "",
                "code": c["excerpt"],
            }), instructions)
            c["final"], c["final_probs"] = _settle(raw_v, _p), _p

        if again:
            with ThreadPoolExecutor(max_workers=judge_workers) as ex:
                list(ex.map(_final, again))
            scored += len(again)
            cost += sum(c.get("cost") or 0 for c in again)
            for c in again:
                if c.get("root_i") is not None:
                    per_seed[c["root_i"]]["calls"] += 1
                    per_seed[c["root_i"]]["cost"] += c.get("cost") or 0
            for c in again:
                print(f"🌱 final: {c.get('final')} {c['file']} "
                      f"`{c['symbol']}` led_to={c.get('led_n')} "
                      f"— {_fmt_probs(c.get('final_probs'))}")
                decisions.append({
                    "kind": "second_look", "step": hops,
                    "file": c["file"], "symbol": c["symbol"],
                    "led_to": c.get("led_n", 0),
                    "verdict": c.get("final") or "",
                    "probs": {k: round(float(v), 2)
                              for k, v in (c.get("final_probs") or {}).items()}})
                if (c.get("final") == "accept" and len(added) < max_add
                        and used <= max_chars):
                    used += len(c["excerpt"])
                    added.append(c)
            added_ids = {id(x) for x in added}
            # sure reject: dropped. accept: attached. not sure: stays a lead.
            held = [c for c in held
                    if c.get("final") != "reject" and id(c) not in added_ids]
    finally:
        client.close()

    out: list[dict] = []
    for c in added:
        guard, code = _split_guard(c["excerpt"])
        if c["cut"]:
            code += ("\n… [excerpt only: the part around the link is shown; "
                     "the rest of this body is not shown in this run] …")
        sid = ""
        try:
            ids = org_redis.lrange(
                f"symbol:{c['file']}:{c['symbol']}:{c['line']}:{c['struct']}", 0, -1)
            if ids:
                sid = ids[-1].decode() if isinstance(ids[-1], bytes) else ids[-1]
        except Exception:
            pass
        out.append({
            "skill_id":      sid,
            "name":          sid or f"{c['symbol']} ({c['file']})",
            "description":   "[found by following names] " + " → ".join(c["trail"]),
            "file_path":     c["file"],
            "symbol":        c["symbol"],
            "suggested":     False,
            "is_obsolete":   False,
            "reconstructed": False,
            "code":          code,
            "guard":         guard,
            "score":         1.0,
            "is_composite":  False,
            # for the evidence record: how it was reached, and which body it was
            "trail":         list(c["trail"]),
            "cut":           bool(c["cut"]),
            "body_chars":    len(c.get("body") or ""),
            "body_sha256":   _sha(c.get("body") or ""),
        })
    # Followed but not attached: one-line leads, in the order they were reached.
    max_leads = int(os.environ.get("JEV_LEADS_MAX", "20"))
    leads = [{"file": c["file"], "symbol": c["symbol"],
              "trail": " → ".join(c["trail"])} for c in held[:max_leads]]
    for c in added:
        if c.get("root_i") is not None:
            per_seed[c["root_i"]]["accepted"] += 1
    for c in held:
        if c.get("root_i") is not None:
            per_seed[c["root_i"]]["leads"] += 1
    for d in per_seed:
        d["cost"] = round(d["cost"], 4)
    info = {"added": len(out), "hops": hops, "scored": scored, "greps": greps,
            "triage_calls": triage_calls, "triage_skipped": triage_skipped,
            "per_seed": per_seed,
            "cost": round(cost, 4), "secs": round(time.time() - t0, 1),
            "leads": leads, "tok_in": tok_in, "tok_out": tok_out,
            "decisions": decisions,
            # every word that was searched, with its number of hits
            "searches": [{"word": w, "hits": int((r or {}).get("total_matched", 0) or 0)}
                         for w, r in list(grep_cache.items())]}
    return out, info


class JevMemory:
    """Memory of one investigation, shared by the start expansion and by
    every grep judge. One object per question."""

    def __init__(self, question: str, skills: list[dict], target=None):
        self.question = question
        self.target = target            # the LLM: it judges the chain
        self.lock = threading.Lock()
        # bodies already in the model's context: (file, symbol)
        self.seen: set[tuple] = {(s.get("file_path", ""), s.get("symbol", ""))
                                 for s in skills}
        # what was found so far, as short sentences
        self.known: list[str] = [
            f"`{s.get('symbol') or s.get('name')}` in {s.get('file_path', '')} "
            "was judged relevant to the question" for s in skills[:12]]
        # word -> grep result, shared by every expansion of this investigation
        self.grep_cache: dict = {}
        # leads already listed to the model: (file, symbol)
        self.leads_shown: set[tuple] = set()
        # every grep word of this investigation, by the model or by the system
        self.words: dict[str, dict] = {}

    def note_word(self, word: str, by: str, hits: int, where: str = "") -> None:
        with self.lock:
            self.words.setdefault(f"{word}|{where}", {
                "word": word, "where": where, "by": by, "hits": int(hits or 0)})

    def words_block(self) -> str:
        with self.lock:
            items = list(self.words.values())
        if not items:
            return ""

        def _fmt(w: dict) -> str:
            where = f" in {w['where']}" if w["where"] else ""
            return f"`{w['word']}`{where} ({w['hits']})"

        mine = [_fmt(w) for w in items if w["by"] == "model"]
        auto = [_fmt(w) for w in items if w["by"] == "system"]
        lines = ["### Words already searched in this investigation",
                 "The number is how many symbols matched."]
        if mine:
            lines.append("- Searched by you: " + ", ".join(mine)
                         + ". You already have these results. Do not search "
                           "them again; pick new words.")
        if auto:
            lines.append("- Searched by DevLoops while following names: "
                         + ", ".join(auto)
                         + ". The matches that helped are in the attached "
                           "bodies and in the leads. Search one of these "
                           "yourself only if you need to see all its matches.")
        return "\n".join(lines)

    def add_seen(self, skills: list[dict]) -> None:
        with self.lock:
            for s in skills:
                self.seen.add((s.get("file_path", ""), s.get("symbol", "")))

    def new_leads(self, leads: list[dict]) -> list[dict]:
        """Leads not shown before and not already in the context.
        Marks them as shown."""
        out = []
        with self.lock:
            for l in leads:
                k = (l["file"], l["symbol"])
                if k in self.seen or k in self.leads_shown:
                    continue
                self.leads_shown.add(k)
                out.append(l)
        return out






class AskRequest(BaseModel):
    question: str
    mode: str = "technical"
    history: list[dict] = []  # [{"role": "user"|"assistant", "content": str}]
    from_commit: str = ""       # historical QA: window the conversation to a commit range
    to_commit:   str = ""
    vector_store: Literal["", "voyage", "qwen"] = ""   # "" = env default; the code-vector store that pre-filters for Jev




async def _final_answer_stream(question, retrieved_context, evidence, synth_target,
                               mode, max_tokens, token_stats):
    style = ("Plain English, no jargon." if mode == "plain"
             else "Technical precision; cite exact symbols, files, and lines.")
    system = (
        "You are DevLoops. An investigation has already gathered evidence from the "
        "codebase by following names through the code. Write the final, complete answer "
        "from the question, the retrieved skills, and the gathered evidence below. Do not "
        "mention the investigation process. Ground every claim in the evidence; if it's insufficient, "
        "say so plainly. NO UNBOUNDED UNIVERSALS: 'no/none/only/all/always/never' "
        "claims are true only of the set the evidence actually shows — bind the scope "
        "('no callers in the ingested index') or drop the quantifier ('the evidence "
        f"shows no X', never 'there is no X'). STYLE: {style}"
    )
    parts = [f"Question: {question}"]
    if retrieved_context:
        parts.append(f"Retrieved skills:\n{retrieved_context}")
    if evidence:
        parts.append(f"Evidence gathered during investigation:\n{evidence}")
    msgs = [{"role": "system", "content": system},
            {"role": "user", "content": "\n\n".join(parts)}]
    # The writer thinks before it answers, and the thinking tokens are taken
    # from max_tokens. Give it its own, larger limit so the answer has room.
    # Anthropic is left alone: its writer runs without reasoning here.
    if synth_target.provider != "anthropic":
        max_tokens = max(max_tokens,
                         int(os.environ.get("WRITER_MAX_TOKENS", "120000")))
    try:
        stream = await litellm.acompletion(
            model=synth_target.model, api_key=synth_target.api_key,
            api_base=synth_target.api_base, max_tokens=max_tokens,
            messages=msgs, stream=True, stream_options={"include_usage": True},
            temperature=0.2,
            **dict(synth_target.extra_params or {}),
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                yield _sse_event({"type": "answer_chunk", "text": chunk.choices[0].delta.content})
            if token_stats is not None and getattr(chunk, "usage", None):
                token_stats["synth_input"]  = token_stats.get("synth_input", 0)  + (chunk.usage.prompt_tokens or 0)
                token_stats["synth_output"] = token_stats.get("synth_output", 0) + (chunk.usage.completion_tokens or 0)
    except Exception as e:
        yield _sse_event({"type": "error", "message": f"Final synthesis failed: {_scrub(str(e))}"})


async def _gather_evidence(question: str, org_redis, org_redis_binary, as_of,
                           target=None):
    """The retrieval, as the question page runs it: embeddings pre-filter →
    Jev scores → Jev follows names (chains). Yields ("status", text) as it
    goes, ("error", text) if Jev scoring fails, and finally
    ("result", {"skills": [...], "leads": [...], "info": {...}}).
    No answer is written here; /ask/stream and /api/retrieve share it."""
    info: dict = {}
    # 1. Embeddings pre-filter: the nearest atomic skills in the selected
    #    store. Jev then scores only those. If the store cannot answer,
    #    Jev scores every atomic skill instead (more work, nothing lost).
    _pre_ids = None
    _k = int(os.environ.get("JEV_PREFILTER_TOP_K", "400"))
    try:
        _t_search = time.time()
        _hits = await asyncio.to_thread(
            lambda: _knn_candidates(question, org_redis_binary,
                                    embedding=None, top_k=_k,
                                    include_obsolete=as_of is not None,
                                    store=_VECTOR_STORE.get(), atomics_only=True,
                                    as_of=as_of))
        info["search_secs"] = round(time.time() - _t_search, 2)
        _pre_ids = [sid for sid, _sc in _hits]
        _m = (f"Embedding search ({_VECTOR_STORE.get()}) returned "
              f"{len(_pre_ids)} skills (asked for {_k}).")
    except Exception as e:
        _m = (f"Embedding search failed ({_scrub(str(e))[:120]}) — "
              f"Jev scores every atomic skill instead.")
    print(f"🧭 {_m}")
    yield "status", _m

    # 2. Jev scores the candidates against the question.
    yield "status", "Scoring skills with Jev..."
    try:
        skills, _ji = await asyncio.to_thread(
            _jev_select, question, org_redis, _pre_ids, as_of)
        info["select"] = _ji
        if _pre_ids and skills:
            # Where the kept seeds sat in the embedding ranking: tells whether
            # JEV_PREFILTER_TOP_K can be lowered without losing seeds.
            _pos = {sid: i + 1 for i, sid in enumerate(_pre_ids)}
            _ranks = sorted(_pos[s["skill_id"]] for s in skills if s.get("skill_id") in _pos)
            if _ranks:
                _rl = (f"kept seeds at knn ranks: median {_ranks[len(_ranks) // 2]}, "
                       f"max {_ranks[-1]} (of {len(_pre_ids)})")
                print(f"🎯 {_rl}")
                info["seed_ranks"] = _ranks
        _msg = (f"Jev kept {_ji['kept']} of {_ji['scored']} skills "
                f"(score >= {_ji['min_score']}, {_ji['above']} above the cut, "
                f"{_ji['failed']} failed) in {_ji['secs']}s, ${_ji['cost']}")
        print(f"🎯 {_msg}")
        yield "status", _msg
    except Exception as e:
        print(f"❌ Jev scoring failed: {_scrub(str(e))}")
        yield "error", f"Jev scoring failed: {_scrub(str(e))[:200]}"
        return

    # 3. Jev follows names from the kept skills (the grep chains).
    _start_leads: list[dict] = []
    if skills and os.environ.get("JEV_EXPAND", "1") == "1":
        yield "status", "Following names from the kept skills..."
        try:
            _jev_mem = JevMemory(question, skills, target)
            _extra, _xi = await asyncio.to_thread(
                _jev_expand, question, org_redis, skills,
                memory=_jev_mem, as_of=as_of)
            skills = skills + _extra
            _jev_mem.add_seen(_extra)
            _start_leads = _jev_mem.new_leads(_xi.get("leads") or [])
            info["expand"] = {k: v for k, v in _xi.items() if k != "leads"}
            _xm = (f"Expansion added {_xi['added']} leads over "
                   f"{_xi['hops']} hop(s) ({_xi['scored']} scored, "
                   f"{_xi['greps']} greps, {len(_start_leads)} open "
                   f"lead(s)) in {_xi['secs']}s, ${_xi['cost']}, "
                   f"{_xi['tok_in']} judge tokens in"
                   + (f"; triage: {_xi['triage_calls']} calls skipped "
                      f"{_xi['triage_skipped']} places"
                      if _xi.get("triage_calls") else ""))
        except Exception as e:
            _xm = ("Expansion failed, continuing without it: "
                   f"{_scrub(str(e))[:120]}")
        print(f"🌱 {_xm}")
        yield "status", _xm
    yield "result", {"skills": skills, "leads": _start_leads, "info": info}


def _print_seed_report(per_seed: list[dict], answer: str) -> None:
    """One line per seed: its Jev score, what its chains cost, what they
    produced, and whether the seed's own symbol appears in the answer."""
    if not per_seed:
        return
    def _cited(d: dict) -> bool:
        sym = d["symbol"] or ""
        if not sym or sym.startswith("<"):           # <module>, <blob>: go by file
            return os.path.basename(d["file"]) in answer
        return sym in answer
    rows = sorted(per_seed, key=lambda d: -(d["score"] or 0))
    total_cost = sum(d["cost"] for d in rows) or 0
    print("🌱 seeds: score · file `symbol` · chain calls · $ · accepted · leads · cited")
    for d in rows:
        d["cited"] = _cited(d)
        print(f"   {d['score'] if d['score'] is not None else '-':>5} "
              f"{d['file']} `{d['symbol']}` · {d['calls']} calls ${d['cost']:.4f} · "
              f"{d['accepted']} accepted · {d['leads']} leads · "
              f"{'cited' if d['cited'] else 'NOT cited'}")
    quiet = [d for d in rows if not d["cited"] and d["accepted"] == 0]
    q_cost = sum(d["cost"] for d in quiet)
    print(f"🌱 seeds summary: {len(rows)} seeds, {sum(d['cited'] for d in rows)} cited; "
          f"{len(quiet)} neither cited nor leading to an accepted body — they spent "
          f"${q_cost:.4f} of ${total_cost:.4f} in chain calls"
          + (f" ({100 * q_cost / total_cost:.0f}%)" if total_cost else ""))


async def _ask_internal_stream(req: AskRequest, max_tokens: int = 27000):
    if not req.question.strip():
        yield _sse_event({"type": "error", "message": "Question cannot be empty"})
        return
    start_time     = time.time()
    token_stats    = {"input": 0, "output": 0}
    error_occurred = False

    if req.vector_store:
        _VECTOR_STORE.set(req.vector_store)

    yield _sse_event({"type": "status", "message": "Connecting to your codebase..."})

    org_redis, org_redis_binary = _redis_clients()

    # ── Historical window: same rank arithmetic as the probe path ──
    as_of = None
    if req.from_commit and req.to_commit:
        as_of = await asyncio.to_thread(
            _resolve_window, org_redis, req.from_commit, req.to_commit)
        if as_of is None:
            yield _sse_event({
                "type": "status",
                "message": "⚠ Selected commits not in the ingestion index — "
                           "answering against current state instead.",
            })

    # The LLM from .env. One call writes the answer, with reasoning ON;
    # Jev does all the searching.
    try:
        target = _llm_target()
        writer = LLMTarget(
            provider     = target.provider,
            model        = target.model,
            api_key      = target.api_key,
            api_base     = target.api_base,
            extra_params = ({} if target.provider == "anthropic"
                            else {"reasoning_effort": "high",
                                  "allowed_openai_params": ["reasoning_effort"]}),
        )
    except MissingSecret as e:
        yield _sse_event({
            "type": "error",
            "message": str(e),
        })
        yield _sse_event({"type": "done"})
        return
    except ValueError as e:             # unknown llm_provider on the org row
        yield _sse_event({
            "type": "error",
            "message": f"LLM provider misconfigured: {e}",
        })
        yield _sse_event({"type": "done"})
        return

    if not os.environ.get("OPENROUTER_API_KEY"):
        yield _sse_event({"type": "error", "message":
            "Questions need OPENROUTER_API_KEY on the server (Jev gathers the evidence)."})
        yield _sse_event({"type": "done"})
        return

    yield _sse_event({"type": "status", "message": "Searching relevant skills..."})

    shown_bodies: dict[tuple, set] = {}
    skills: list[dict] = []
    _start_leads: list[dict] = []
    _ginfo: dict = {}
    async for kind, payload in _gather_evidence(req.question, org_redis,
                                                org_redis_binary, as_of, target):
        if kind == "status":
            yield _sse_event({"type": "status", "message": payload})
        elif kind == "error":
            yield _sse_event({"type": "error", "message": payload})
            yield _sse_event({"type": "done"})
            return
        else:
            skills, _start_leads = payload["skills"], payload["leads"]
            _ginfo = payload.get("info") or {}

    if not skills:
        yield _sse_event({
            "type":    "status",
            "message": "No skills matched the question.",
        })
        context = ""
        yield _sse_event({"type": "sources", "sources": []})
    else:
        context = _build_context(skills, shown_bodies)
        # No search rounds follow: the leads cannot be read later.
        if _start_leads:
            context += (
                "\n\n---\n\n### Places reached but not read\n"
                "DevLoops followed names from the code above and reached "
                "these places, but was not sure they help, so their bodies "
                "are not included. They are not evidence. Do not state "
                "what they contain.\n"
                + "\n".join(f"- {l['file']} `{l['symbol']}` — chain: "
                            f"{l['trail']}" for l in _start_leads))
        sources_payload = [
            {
                "skill_id":     s["skill_id"],
                "name":         s["name"],
                "file_path":    s["file_path"],
                "score":        s["score"],
                "suggested":    s["suggested"],
                "is_composite": s.get("is_composite", False),
                "lifted_by":    s.get("lifted_by", ""),
            }
            for s in skills
        ]
        yield _sse_event({"type": "sources", "sources": sources_payload})

    # 4. One call writes the answer from the gathered bodies.
    try:
        print(f"✍️  writing: {len(skills)} bodies, {len(context)} chars of context")
        yield _sse_event({"type": "status", "message": "Writing answer..."})
        _t_w0, _t_first, _answer_text = time.time(), None, []
        async for event in _final_answer_stream(
            req.question, context, "",
            writer, req.mode, max_tokens, token_stats,
        ):
            if '"answer_chunk"' in event[:40]:
                if _t_first is None:
                    _t_first = time.time()
                _answer_text.append(json.loads(event[6:]).get("text") or "")
            yield event
        _t_w1 = time.time()
        _answer_chars = sum(len(t) for t in _answer_text)
        _print_seed_report((_ginfo.get("expand") or {}).get("per_seed") or [],
                           "".join(_answer_text))

        # One line of numbers for the page: time per phase, cost, writer speed.
        # Output tokens include the writer's reasoning (the provider counts
        # them), so tokens/s is over the whole call, thinking included; the
        # first visible token arrives when the thinking ends.
        _sel, _exp = _ginfo.get("select") or {}, _ginfo.get("expand") or {}
        _out_tok = int(token_stats.get("synth_output") or 0)
        _gen_secs = _t_w1 - _t_w0
        metrics = {
            "search_secs": _ginfo.get("search_secs"),
            "select_secs": _sel.get("secs"), "select_cost": _sel.get("cost"),
            "select_calls": _sel.get("scored"), "seeds": _sel.get("kept"),
            "expand_secs": _exp.get("secs"), "expand_cost": _exp.get("cost"),
            "expand_calls": _exp.get("scored"), "expand_added": _exp.get("added"),
            "triage_calls": _exp.get("triage_calls"), "triage_skipped": _exp.get("triage_skipped"),
            "bodies": len(skills), "context_chars": len(context),
            "writer": f"{writer.provider}/{writer.model}",
            "writer_first_token_secs": round(_t_first - _t_w0, 1) if _t_first else None,
            "writer_secs": round(_t_w1 - _t_w0, 1),
            "writer_in_tokens": int(token_stats.get("synth_input") or 0),
            "writer_out_tokens": _out_tok,
            "writer_tok_per_sec": round(_out_tok / _gen_secs, 1) if _out_tok and _gen_secs > 0 else None,
            "answer_chars": _answer_chars,
            "jev_cost": round((_sel.get("cost") or 0) + (_exp.get("cost") or 0), 4),
            "total_secs": round(time.time() - start_time, 1),
        }
        print(f"📊 {json.dumps(metrics)}")
        yield _sse_event({"type": "metrics", "metrics": metrics})

        yield _sse_event({"type": "done"})

    except Exception as e:
        error_occurred = True
        print(f"❌ _ask_internal_stream crash: {_scrub(str(e))}")
        print(_scrub(traceback.format_exc()))
        yield _sse_event({"type": "error", "message": "Internal error — check server logs"})
        yield _sse_event({"type": "done"})

    finally:
        print(f"⏱  question done in {time.time() - start_time:.1f}s, "
              f"tokens in={token_stats['input']} out={token_stats['output']}"
              f"{' (error)' if error_occurred else ''}")





# ──────────────────────────────────────────────────────────────────────────────
# MFA: Login flow completion (called after /auth/login returns mfa_required=True)
# ──────────────────────────────────────────────────────────────────────────────



# ──────────────────────────────────────────────────────────────────────────────
# MFA: Settings — check status, enroll, complete enrollment, disable
# ──────────────────────────────────────────────────────────────────────────────









PROVIDER_DEFAULTS = {
    "anthropic": {
        "model":        "anthropic/claude-haiku-4-5",
        "api_base":     None,
        "extra_params": {},
    },
    "llmbase": {
        "model":        "openai/accounts/fireworks/models/deepseek-v4p1-flash",
        "api_base":     "https://api.fireworks.ai/inference/v1",
        # reasoning_effort is added per call where the writer/judge needs it.
        "extra_params": {},
    },
}

_llm_cache: Optional[LLMTarget] = None

def _llm_target() -> LLMTarget:
    """The writer/judge model, from .env: LLM_PROVIDER + LLM_API_KEY
    (+ optional LLM_MODEL / LLM_API_BASE)."""
    global _llm_cache
    if _llm_cache is not None:
        return _llm_cache
    provider = (os.getenv("LLM_PROVIDER") or "llmbase").lower()
    defaults = PROVIDER_DEFAULTS.get(provider)
    if defaults is None:
        raise ValueError(f"Unknown LLM_PROVIDER {provider!r}; "
                         f"choose one of {sorted(PROVIDER_DEFAULTS)}")
    key = os.getenv("LLM_API_KEY", "")
    if not key:
        raise MissingSecret("LLM_API_KEY is not set in .env")
    _llm_cache = LLMTarget(
        provider, os.getenv("LLM_MODEL") or defaults["model"], key,
        os.getenv("LLM_API_BASE") or defaults["api_base"], defaults["extra_params"])
    return _llm_cache




# ── Routes ─────────────────────────────────────────────────────────────────────







@app.get("/", response_class=HTMLResponse)
def qa_page():
    return HTMLResponse(HTML)

@app.get("/api/skills/{skill_id}")
async def skill_detail(skill_id: str, to_commit: str = ""):
    org_redis, _ = _redis_clients()

    def _fetch():
        raw = org_redis.get(f"skill:{skill_id}")
        if not raw:
            return None
        s = json.loads(raw)
        as_of = None
        if to_commit:
            r_to = org_redis.zrank("commit_order", to_commit)
            if r_to is not None:
                as_of = {"to_rank": int(r_to)}
        desc = s.get("description_of_skill", "")
        if as_of is not None:
            sk_asof = skills_lib.get_skill_as_of(org_redis, skill_id,
                                                 as_of["to_rank"])
            if sk_asof is not None and not sk_asof.get("_as_of_warning"):
                desc = sk_asof.get("description_of_skill", desc)
        parsed = skills_lib.parse_def_key(s.get("def_key", "") or "")
        out = {
            "skill_id":     skill_id,
            "name":         s.get("skill_name", skill_id),
            "description":  desc,
            "loc":          f"{parsed[0]}:{parsed[2]}" if parsed else "",
            "is_composite": s.get("is_composite", False),
            "is_obsolete":  s.get("isObsolete", False),
        }
        # The body: as of `to_commit` when given, the newest one when not.
        body = _fetch_skill_with_code(skill_id, org_redis, prefer_redis=True,
                                      include_obsolete=True, as_of=as_of) or {}
        out["code"] = body.get("code") or ""
        out["removed_at"] = (body.get("removed_at") or "")[:12]
        if out["is_composite"]:
            out["members"] = _expand_composite_members(org_redis, s, as_of,
                                                       limit=30)
        return out

    result = await asyncio.to_thread(_fetch)
    if result is None:
        raise HTTPException(404, "Skill not found")
    return result

# ── Timeline / range report ───────────────────────────────────────────────────

@app.get("/timeline", response_class=HTMLResponse)
def timeline_page():
    return HTMLResponse(TIMELINE_HTML)


@app.get("/api/timeline/commits")
async def timeline_commits():
    """Ordered commit axis for the range slider. Reads commit_order ZSET +
    commit_meta, one pipeline. Oldest first."""
    org_redis, _ = _redis_clients()

    def _fetch():
        raw = org_redis.zrange("commit_order", 0, -1, withscores=True)
        hashes = [(h.decode() if isinstance(h, bytes) else h, int(s)) for h, s in raw]
        if not hashes:
            return []
        pipe = org_redis.pipeline(transaction=False)
        for h, _ in hashes:
            pipe.get(f"commit_meta:{h}")
        metas = pipe.execute()
        out = []
        for (h, seq), m in zip(hashes, metas):
            goal, date, author = "", "", ""
            if m:
                try:
                    j = json.loads(m)
                    goal = j.get("goal", "")
                    date = j.get("author_date", "") or j.get("ingested_at", "")
                    author = (j.get("author", "") or j.get("author_name", "")
                              or j.get("author_email", ""))
                except (json.JSONDecodeError, TypeError):
                    pass
            out.append({"hash": h, "seq": seq, "goal": goal[:100],
                        "date": date, "author": author[:40]})
        return out

    commits = await asyncio.to_thread(_fetch)
    return {"commits": commits, "total": len(commits)}


@app.get("/api/timeline/skills")
async def timeline_skills(
    from_commit: str,
    to_commit: str,
    page: int = 1,
    page_size: int = 12,
    include: str = "new,updated",
):
    """Skills with events inside [from_commit, to_commit] inclusive, in
    ingestion order, deduped (first event wins ordering, all events badged).
    Server-side pagination."""
    org_redis, _ = _redis_clients()
    include_set = {e.strip() for e in include.split(",")} & {"new", "updated", "obsoleted"}
    if not include_set:
        include_set = {"new", "updated"}
    page = max(1, page)
    page_size = min(max(1, page_size), 50)

    def _fetch():
        r_from = org_redis.zrank("commit_order", from_commit)
        r_to   = org_redis.zrank("commit_order", to_commit)
        if r_from is None or r_to is None:
            return {"error": "commit not found in ingestion index"}
        if r_from > r_to:
            r_from, r_to = r_to, r_from
        hashes = org_redis.zrange("commit_order", r_from, r_to)
        hashes = [h.decode() if isinstance(h, bytes) else h for h in hashes]

        pipe = org_redis.pipeline(transaction=False)
        for h in hashes:
            for ev in ("new", "updated", "obsoleted"):
                pipe.smembers(f"commit_skills:{h}:{ev}")
        flat = pipe.execute()

        # skill_id -> {events, first_commit} preserving ingestion order
        ordered: dict[str, dict] = {}
        for i, h in enumerate(hashes):
            for j, ev in enumerate(("new", "updated", "obsoleted")):
                if ev not in include_set:
                    continue
                for sid in _decode_set(flat[i * 3 + j]):
                    entry = ordered.setdefault(sid, {"events": set(), "commit": h})
                    entry["events"].add(ev)

        sids = list(ordered.keys())
        total = len(sids)
        start = (page - 1) * page_size
        page_ids = sids[start:start + page_size]

        skills = []
        if page_ids:
            values = org_redis.mget([f"skill:{sid}" for sid in page_ids])
            for sid, raw in zip(page_ids, values):
                meta = ordered[sid]
                if not raw:
                    skills.append({"skill_id": sid, "missing": True,
                                   "events": sorted(meta["events"]),
                                   "commit": meta["commit"][:12]})
                    continue
                s = json.loads(raw)
                parsed = skills_lib.parse_def_key(s.get("def_key", "") or "")
                # The body as of the right side of the range. The card gets
                # its first part; the whole body comes from /api/skills/<id>.
                body = _fetch_skill_with_code(
                    sid, org_redis, prefer_redis=True, include_obsolete=True,
                    as_of={"from_rank": int(r_from), "to_rank": int(r_to)}) or {}
                skills.append({
                    "skill_id":     sid,
                    "description":  s.get("description_of_skill", ""),
                    "code":         (body.get("code") or "")[:1500],
                    "removed_at":   (body.get("removed_at") or "")[:12],
                    "symbols":      skills_lib.skill_symbols(s)[:6],
                    "loc":          f"{parsed[0]}:{parsed[2]}" if parsed else "",
                    "is_composite": s.get("is_composite", False),
                    "is_obsolete":  s.get("isObsolete", False),
                    "events":       sorted(meta["events"]),
                    "commit":       meta["commit"][:12],
                })
        return {
            "skills": skills, "total": total, "page": page,
            "page_size": page_size,
            "pages": max(1, (total + page_size - 1) // page_size),
            "commits_in_range": len(hashes),
        }

    result = await asyncio.to_thread(_fetch)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


class TimelineReportRequest(BaseModel):
    from_commit: str
    to_commit:   str
    mode:        str = "technical"
    skill_ids:   list[str] = []

# ── Range report: fan-out probes ──────────────────────────────────────────────

REPORT_CONCURRENCY = min(int(os.environ.get("REPORT_CONCURRENCY", "40")), 20)

_SEV_RANK = {"FLAGRANTLY_MALICIOUS": 7, "SUSPICIOUS": 6, "MAJOR_FLAW": 5,
             "MINOR_FLAW": 4, "FLAW": 4, "ERROR": 3, "INDEX_MISMATCH": 2,
             "UNCLEAR": 2, "DORMANT": 1, "PENDING": 1, "BENIGN": 0}

# Cross-slice findings: claims by one probe about ANOTHER slice's diff.
# Ledger entries, never verdicts — they raise no counter and stamp nothing;
# they mark the target CONTESTED and feed its rerun as unverified leads.
_FINDING_RE = re.compile(
    r"^FINDING\s*:\s*(?P<file>\S+?)@(?P<commit>[0-9a-f]{8,12})\s*[—-]+\s*"
    r"(?P<sev>FLAGRANTLY_MALICIOUS|SUSPICIOUS|MAJOR_FLAW|MINOR_FLAW)\s*"
    r"[—-]+\s*(?P<note>.+)$", re.M | re.I)

# Tolerates markdown decoration models add despite instructions:
# "VERDICT: BENIGN", "**Verdict:** BENIGN", "**Verdict**: BENIGN"
_VERDICT_RE = re.compile(
    r"VERDICT\s*\*{0,2}\s*[:—-]\s*\*{0,2}\s*"
    r"(BENIGN|FLAGRANTLY_MALICIOUS|SUSPICIOUS|MAJOR_FLAW|MINOR_FLAW|FLAW|"
    r"DORMANT|UNCLEAR|INDEX_MISMATCH)\b[^\n]*",
    re.I)

def _resolve_window(org_redis, from_commit: str, to_commit: str) -> Optional[dict]:
    """Rank window on the commit_order axis for time-travel filtering.
    None when either commit isn't indexed — callers degrade to unwindowed."""
    r_from = org_redis.zrank("commit_order", from_commit)
    r_to   = org_redis.zrank("commit_order", to_commit)
    if r_from is None or r_to is None:
        return None
    if r_from > r_to:
        r_from, r_to = r_to, r_from
    return {"from_rank": int(r_from), "to_rank": int(r_to)}

def _mark_if_interrupted(org_redis, meta: dict) -> dict:
    """Read-time truth: progress from the vmap, liveness from the lease.
    A 'running' report with no lease has no owner — its job died."""
    meta = _derive_meta(org_redis, meta)
    rid = meta.get("report_id", "")
    status = meta.get("status")
    if status == "done" and int(meta["pending"]) > 0:
        org_redis.hset(f"report:{rid}", "status", "interrupted")
        meta["status"] = "interrupted"
    elif status == "running" and not _lease_held(rid):
        org_redis.hset(f"report:{rid}", "status", "interrupted")
        meta["status"] = "interrupted"
    return meta

def _report_keys(rid: str) -> tuple[str, str, str]:
    return f"report:{rid}", f"report:{rid}:order", f"report:{rid}:probes"


def _report_all_keys(rid: str) -> list[str]:
    """Every Redis key that belongs to one report. A report never expires:
    these keys go away only when the report is deleted."""
    return [f"report:{rid}", f"report:{rid}:order", f"report:{rid}:probes",
            f"report:{rid}:vmap", f"report:{rid}:cmap",
            f"report:{rid}:findings", f"report:{rid}:conflicts",
            f"report:{rid}:evidence"]


# ── One owner per report: a lease in control Redis ─────────────────────────
# The job renews it every few seconds; resume, auto-resume and ↻ must acquire
# it first. A rolling deploy therefore cannot start a second job on a report
# whose old container is still alive — the old one holds the lease until it
# dies, then the lease expires and the new container picks the report up.
_INSTANCE_ID = secrets.token_hex(6)
REPORT_LEASE_SECONDS = int(os.environ.get("REPORT_LEASE_SECONDS", "120"))
_LEASE_RENEW   = ("if redis.call('GET',KEYS[1])==ARGV[1] then "
                  "return redis.call('EXPIRE',KEYS[1],ARGV[2]) end return 0")
_LEASE_RELEASE = ("if redis.call('GET',KEYS[1])==ARGV[1] then "
                  "return redis.call('DEL',KEYS[1]) end return 0")

def _lease_key(rid: str) -> str: return f"report_lease:{rid}"
def _stop_key(rid: str)  -> str: return f"report_stop:{rid}"

def _lease_acquire(rid: str) -> bool:
    return bool(_redis_text.set(_lease_key(rid), _INSTANCE_ID,
                                nx=True, ex=REPORT_LEASE_SECONDS))

def _lease_renew(rid: str) -> bool:
    return bool(_redis_text.eval(_LEASE_RENEW, 1, _lease_key(rid),
                                 _INSTANCE_ID, REPORT_LEASE_SECONDS))

def _lease_release(rid: str) -> None:
    try:
        _redis_text.eval(_LEASE_RELEASE, 1, _lease_key(rid), _INSTANCE_ID)
    except Exception as e:
        print(f"⚠️  lease release failed (non-fatal): {_scrub(str(e))}")

def _lease_held(rid: str) -> bool:
    try:
        return bool(_redis_text.exists(_lease_key(rid)))
    except Exception:
        return False

def _stop_requested(rid: str) -> bool:
    try:
        return bool(_redis_text.exists(_stop_key(rid)))
    except Exception:
        return False


def _derive_meta(org_redis, meta: dict) -> dict:
    """Progress and tallies are DERIVED from the vmap on every read. There is
    no counter that can drift: the per-probe verdicts are the only state."""
    rid = meta.get("report_id", "")
    vals = [v.decode() if isinstance(v, bytes) else v
            for v in org_redis.hvals(f"report:{rid}:vmap")]
    c: dict[str, int] = {}
    for v in vals:
        c[v] = c.get(v, 0) + 1
    if vals:
        meta["total"] = str(len(vals))
    meta["pending"]    = str(c.get("PENDING", 0))
    meta["errors"]     = str(c.get("ERROR", 0))
    meta["done"]       = str(len(vals) - c.get("PENDING", 0))
    meta["flagrant"]   = str(c.get("FLAGRANTLY_MALICIOUS", 0))
    meta["suspicious"] = str(c.get("SUSPICIOUS", 0))
    meta["major_flaw"] = str(c.get("MAJOR_FLAW", 0))
    return meta


# Stamp a result ONLY if the probe is still open. A second job, a retried
# task or a late callback delivering a result for an already-stamped probe is
# dropped here, atomically, instead of overwriting a verdict.
_STAMP_IF_OPEN = """
if redis.call('HGET', KEYS[2], ARGV[1]) ~= 'PENDING' then return 0 end
redis.call('HSET', KEYS[1], ARGV[1], ARGV[2])
redis.call('HSET', KEYS[2], ARGV[1], ARGV[3])
return 1
"""

def _persist_report_plan(org_redis, rid: str, from_commit: str, to_commit: str,
                         items: list[dict]) -> None:
    meta_k, order_k, probes_k = _report_keys(rid)
    pipe = org_redis.pipeline(transaction=False)
    pipe.hset(meta_k, mapping={
        "report_id":   rid,
        "from_commit": from_commit,
        "to_commit":   to_commit,
        "status":      "running",
        "phase":       "probes",
        "vector_store": _VECTOR_STORE.get(),
        "total":       len(items),
        "created_at":  datetime.utcnow().isoformat(),
    })
    if items:
        pipe.rpush(order_k, *[i["probe_id"] for i in items])
        pipe.hset(probes_k, mapping={
            i["probe_id"]: json.dumps({
                "probe_id": i["probe_id"],
                "skill_id": i["skill_id"], "symbol": i["symbol"],
                "loc": i["loc"], "events": i["events"],
                "commit": i["commit"][:12],
                "commits": [t["commit"][:12] for t in i.get("touches", [])]
                           or [i["commit"][:12]],
                "verdict": "PENDING", "answer": "", "error": "",
            }) for i in items
        })
        pipe.hset(f"report:{rid}:vmap",
                  mapping={i["probe_id"]: "PENDING" for i in items})
        pipe.hset(f"report:{rid}:cmap",
                  mapping={i["probe_id"]:
                           ",".join(t["commit"] for t in i.get("touches", []))
                           or i["commit"]
                           for i in items})
    pipe.zadd("reports_index", {rid: time.time()})
    pipe.execute()

def _finding_key(loc: str, commit: str) -> str:
    return f"{(loc or '').rsplit(':', 1)[0]}@{commit[:12]}"


def _leads_for(org_redis, rid: str, item: dict, exclude_sid: str) -> list:
    """Unverified cross-slice claims targeting this item's slice, all
    sources except itself. One hash field per (target|source) — reads
    need no merge, writes never race."""
    out = []
    pref = _finding_key(item.get("loc") or "", item["commit"]) + "|"
    try:
        for k, v in org_redis.hscan_iter(f"report:{rid}:findings",
                                         match=pref + "*"):
            k = k.decode() if isinstance(k, bytes) else k
            if k.split("|", 1)[1] == exclude_sid:
                continue
            try:
                out.append(json.loads(v if isinstance(v, str) else v.decode()))
            except (json.JSONDecodeError, TypeError):
                continue
    except Exception as e:
        print(f"⚠️  leads read failed (non-fatal): {_scrub(str(e))}")
    # Dedup near-identical claims: N probes reading the same record file the
    # same sentence; volume adds prompt noise and eats iteration budget, not
    # information. Keep the highest-severity exemplar per token cluster and
    # record how many probes corroborated it.
    def _toks(note):
        return set(re.findall(r"[a-z0-9_]{4,}", (note or "").lower()))
    out.sort(key=lambda l: -_SEV_RANK.get(l.get("severity", ""), 0))
    kept, sigs = [], []
    for l in out:
        t = _toks(l.get("note", ""))
        for i, s in enumerate(sigs):
            u = len(t | s)
            if u and len(t & s) / u >= 0.6:
                kept[i]["corroborators"] = kept[i].get("corroborators", 1) + 1
                break
        else:
            sigs.append(t)
            l.setdefault("corroborators", 1)
            kept.append(l)
    return kept


def _rewind_probe(org_redis, rid: str, sid: str) -> None:
    """Reopen one probe (verdict PENDING). The only way a probe becomes
    stampable again. No counters — progress is derived from the vmap."""
    _meta_k, _, probes_k = _report_keys(rid)
    raw = org_redis.hget(probes_k, sid)
    if not raw:
        return
    rec = json.loads(raw)
    rec.update({"verdict": "PENDING", "answer": "", "error": ""})
    pipe = org_redis.pipeline(transaction=False)
    pipe.hset(probes_k, sid, json.dumps(rec))
    pipe.hset(f"report:{rid}:vmap", sid, "PENDING")
    # The record of what the last run read belongs to the last verdict.
    # The next run writes its own, so the two can never be mixed up.
    pipe.hdel(f"report:{rid}:evidence", sid)
    pipe.execute()


_JUDGMENT_RANK = {"BENIGN": 0, "MINOR_FLAW": 1, "FLAW": 1, "MAJOR_FLAW": 2,
                  "SUSPICIOUS": 3, "FLAGRANTLY_MALICIOUS": 4}

def _persist_probe_result(org_redis, rid: str, sid: str,
                          verdict: str, answer: str, error: str,
                          findings: Optional[list] = None,
                          model: str = "",
                          floor_verdict: bool = False,
                          extra: Optional[dict] = None) -> bool:
    meta_k, _, probes_k = _report_keys(rid)
    raw = org_redis.hget(probes_k, sid)
    rec = json.loads(raw) if raw else {"skill_id": sid}
    if extra:
        rec.update(extra)
    if floor_verdict and rec.get("history"):
        # Contested rerun = safety net: it may RAISE severity, never lower it.
        # The prior verdict was stamped from the probe's own reads; a fresh
        # sample that lands lower (or fails to judge) does not overturn it.
        prev = rec["history"][-1].get("verdict", "")
        if prev in _JUDGMENT_RANK and _JUDGMENT_RANK.get(verdict, -1) <= _JUDGMENT_RANK[prev]:
            if verdict != prev:
                answer = ((answer or "") + f"\n\n[SYSTEM: contested rerun "
                          f"returned {verdict}; prior verdict {prev} kept — "
                          "contested reruns can only raise severity.]")
            verdict, error = prev, ""
    rec.update({"verdict": verdict, "answer": answer, "error": error})
    rec.setdefault("history", []).append(
        {"verdict": verdict, "ts": int(time.time()), "model": model})
    rec["history"] = rec["history"][-10:]
    stamped = org_redis.eval(_STAMP_IF_OPEN, 2, probes_k, f"report:{rid}:vmap",
                             sid, json.dumps(rec), verdict)
    if not stamped:
        print(f"↩︎  dropped stamp {verdict} for {sid}: probe is not open "
              f"(already stamped by another run)")
        return False
    pipe = org_redis.pipeline(transaction=False)
    for f in (findings or []):
        fkey = f"{f['file']}@{f['commit'][:12]}|{sid}"
        pipe.hset(f"report:{rid}:findings", fkey, json.dumps(dict(
            f, by=sid, ts=int(time.time()), model=model)))
    pipe.hset(meta_k, "last_progress_at", datetime.utcnow().isoformat())
    pipe.execute()
    return True

def _finalize_report(org_redis, rid: str, status: str = "done") -> None:
    """'stopped' / 'error' pass through. 'done' is never taken on faith: it is
    derived from the vmap — open probes → interrupted, errors → error."""
    now = datetime.utcnow().isoformat()
    if status != "done":
        org_redis.hset(f"report:{rid}", mapping={"status": status,
                                                 "last_progress_at": now})
        return
    m = _derive_meta(org_redis, {"report_id": rid})
    if int(m["pending"]) > 0:
        final = "interrupted"
    elif int(m["errors"]) > 0:
        final = "error"
    else:
        final = "done"
    org_redis.hset(f"report:{rid}", mapping={"status": final, "phase": "done",
                                             "last_progress_at": now})

def _set_report_phase(org_redis, rid: str, phase: str) -> None:
    org_redis.hset(f"report:{rid}", mapping={
        "phase": phase, "last_progress_at": datetime.utcnow().isoformat()})

def _report_phase(org_redis, rid: str) -> str:
    v = org_redis.hget(f"report:{rid}", "phase")
    return (v.decode() if isinstance(v, bytes) else v) or "probes"

def _collect_range_items(org_redis, from_commit: str, to_commit: str) -> list[dict]:
    """One item per skill with a new/updated event in [from, to] inclusive,
    ingestion order, deduped. Carries the commit claim + that skill's new call
    edges in the range (matched by caller def_key)."""
    r_from = org_redis.zrank("commit_order", from_commit)
    r_to   = org_redis.zrank("commit_order", to_commit)
    if r_from is None or r_to is None:
        raise ValueError("commit not found in ingestion index")
    if r_from > r_to:
        r_from, r_to = r_to, r_from
    hashes = [h.decode() if isinstance(h, bytes) else h
              for h in org_redis.zrange("commit_order", r_from, r_to)]

    pipe = org_redis.pipeline(transaction=False)
    for h in hashes:
        pipe.smembers(f"commit_skills:{h}:new")
        pipe.smembers(f"commit_skills:{h}:updated")
        pipe.get(f"commit_meta:{h}")
        pipe.smembers(f"commit_calls:{h}")
        pipe.smembers(f"commit_refs:{h}")
    flat = pipe.execute()

    items: dict[str, dict] = {}          # sid → item, insertion-ordered
    edges_by_commit: dict[str, list] = {}
    refs_by_commit: dict[str, list] = {}
    for i, h in enumerate(hashes):
        base = i * 5
        goal = ""
        if flat[base + 2]:
            try:
                goal = json.loads(flat[base + 2]).get("goal", "")
            except (json.JSONDecodeError, TypeError):
                pass
        for ev, raw in (("new", flat[base]), ("updated", flat[base + 1])):
            for sid in sorted(_decode_set(raw)):
                it = items.setdefault(sid, {"skill_id": sid, "events": set(),
                                            "commit": h, "goal": goal,
                                            "touches": {}})
                it["events"].add(ev)
                t = it["touches"].setdefault(h, {"commit": h, "goal": goal,
                                                 "events": set()})
                t["events"].add(ev)
        edges = []
        for raw in _decode_set(flat[base + 3]):
            try:
                edges.append(json.loads(raw))
            except (json.JSONDecodeError, TypeError):
                continue
        if edges:
            edges_by_commit[h] = edges
        refs = []
        for raw in _decode_set(flat[base + 4]):
            try:
                refs.append(json.loads(raw))
            except (json.JSONDecodeError, TypeError):
                continue
        if refs:
            refs_by_commit[h] = refs

    if not items:
        return []
    sids = list(items.keys())
    values = org_redis.mget([f"skill:{sid}" for sid in sids])
    out = []
    for sid, raw in zip(sids, values):
        it = items[sid]
        if not raw:
            continue
        s = json.loads(raw)
        def_key = s.get("def_key", "") or ""
        parsed = skills_lib.parse_def_key(def_key)
        symbol = parsed[1] if parsed else ""
        # This skill's new outgoing edges in-range (caller def_key prefix match:
        # file+symbol, line-agnostic since drift moves lines)
        my_edges = []
        my_refs = []
        if parsed:
            prefix = f"{parsed[0]}:{parsed[1]}:"
            seen_edges = set()
            for h_e, edges in edges_by_commit.items():
                for e in edges:
                    if not (e.get("caller") or "").startswith(prefix):
                        continue
                    k = (e.get("callee"), e.get("line"))
                    if k in seen_edges:
                        continue
                    seen_edges.add(k)
                    my_edges.append({**e, "commit": h_e})
            seen_refs = set()
            for h_r, refs in refs_by_commit.items():
                for e in refs:
                    if not (e.get("referrer") or "").startswith(prefix):
                        continue
                    k = (e.get("target"), e.get("line"), e.get("kind"))
                    if k in seen_refs:
                        continue
                    seen_refs.add(k)
                    my_refs.append({**e, "commit": h_r})
        out.append({
            "skill_id":    sid,
            "symbol":      symbol,
            "description": s.get("description_of_skill", ""),
            "loc":         f"{parsed[0]}:{parsed[2]}" if parsed else "",
            "is_composite": s.get("is_composite", False),
            "events":      sorted(it["events"]),
            "commit":      it["commit"],
            "goal":        it["goal"],
            "touches":     [{"commit": t["commit"], "goal": t["goal"],
                             "events": sorted(t["events"])}
                            for t in it["touches"].values()],
            "new_edges":   my_edges,
            "new_refs":    my_refs,
        })
    return out


# Any skill touched by >1 in-range commit splits into per-diff units. The
# xz sandbox.c page is the evidence: the shared 3-touch probe rationalized
# the sabotage; the focused single-commit probe caught it.
PROBE_SPLIT_THRESHOLD = int(os.environ.get("PROBE_SPLIT_THRESHOLD", "1"))

def _expand_probe_units(items: list[dict]) -> list[dict]:
    """A skill with more than PROBE_SPLIT_THRESHOLD in-range touches is split
    into one probe unit per touching commit (full attention per diff). At or
    below the threshold, the skill stays a single range probe. probe_id is the
    vmap/probes/cmap key: '<sid>' for whole-skill, '<sid>@<commit12>' for
    per-diff units."""
    units: list[dict] = []
    for it in items:
        touches = it.get("touches") or []
        if len(touches) <= PROBE_SPLIT_THRESHOLD:
            units.append({**it, "probe_id": it["skill_id"]})
            continue
        all_commits = [t["commit"][:12] for t in touches]
        for t in touches:
            units.append({
                **it,
                "probe_id":        f"{it['skill_id']}@{t['commit'][:12]}",
                "touches":         [t],
                "commit":          t["commit"],
                "goal":            t["goal"],
                "events":          sorted(t["events"]),
                "sibling_commits": [c for c in all_commits
                                    if c != t["commit"][:12]],
                "new_edges":       [e for e in it.get("new_edges", [])
                                    if e.get("commit") == t["commit"]],
                "new_refs":        [e for e in it.get("new_refs", [])
                                    if e.get("commit") == t["commit"]],
            })
    return units


def _probe_context(org_redis, org_redis_binary, question: str, item: dict,
                   as_of: Optional[dict] = None) -> str:
    """The target's body as of the probed commit, and nothing else. Every
    other thing the judge sees is gathered by the probe itself: the same
    commit's other changes, callers and referrers, and Jev's name chains."""
    sk = _fetch_skill_with_code(item["skill_id"], org_redis,
                                prefer_redis=True, include_obsolete=True,
                                as_of=as_of)
    if not sk:
        return ""
    sk["name"] = (f"🎯 TARGET UNDER INVESTIGATION — skill {item['skill_id']} "
                  f"({item.get('symbol', '')})")
    return _build_context([{**sk, "score": 1.0, "symbol": item.get("symbol", "")}])

import difflib

def _asof_description(_redis, sid: str, sk: dict, to_rank: int) -> Optional[str]:
    """None = not presentable in this window (formed after the probed commit,
    or provenance unresolvable — fail closed); else the description as of
    to_rank. Descriptions are the only store artifact written with hindsight,
    so every reader of another skill's description must pass through here."""
    cr = _redis.zrank("commit_order", sk.get("created_commit") or "__none__")
    if cr is None:
        cr = _redis.zrank("commit_order", sk.get("commit_hash") or "__none__")
    if cr is None or int(cr) > to_rank:
        return None
    sk_asof = skills_lib.get_skill_as_of(_redis, sid, to_rank)
    if sk_asof is None or sk_asof.get("_as_of_warning"):
        return None
    return sk_asof.get("description_of_skill", "")



_DIFF_MAX_LINES = int(os.environ.get("PROBE_DIFF_MAX_LINES", "6000"))


def _touch_diffs(org_redis, item: dict) -> list[dict]:
    """Per in-range touching commit: unified diff of the skill's body vs its
    previous stored version, from the code_at: per-commit store. The version
    chain = skill_history snapshots + current record (each carries the
    commit_hash and def_key of that state). Missing bodies (description-only
    updates, pre-code_at data) yield status entries, never failures."""
    sid = item["skill_id"]
    raw = org_redis.get(f"skill:{sid}")
    if not raw:
        return []
    sk = json.loads(raw)
    chain: list[tuple[str, str]] = []
    for raw_e in org_redis.lrange(f"skill_history:{sid}", 0, -1):
        try:
            e = json.loads(raw_e if isinstance(raw_e, str) else raw_e.decode())
        except (json.JSONDecodeError, TypeError):
            continue
        if e.get("commit_hash") and e.get("def_key"):
            chain.append((e["commit_hash"], e["def_key"]))
    if sk.get("commit_hash") and sk.get("def_key"):
        chain.append((sk["commit_hash"], sk["def_key"]))
    if not chain:
        return []
    pipe = org_redis.pipeline(transaction=False)
    for c, _dk in chain:
        pipe.zrank("commit_order", c)
    ranks = pipe.execute()
    versions = sorted(
        {(int(r), c, dk) for (c, dk), r in zip(chain, ranks) if r is not None},
        key=lambda t: t[0])
    by_commit = {c: (r, dk) for r, c, dk in versions}

    def _body(commit: str, dk: str) -> Optional[str]:
        v = org_redis.hget(f"code_at:{commit}:{dk}", "body")
        return (v.decode() if isinstance(v, bytes) else v) if v is not None else None

    out = []
    for t in item.get("touches", []):
        h = t["commit"]
        cur = by_commit.get(h)
        if cur is None:
            out.append({"commit": h, "status":
                        "no stored body version at this commit (description-only "
                        "update or pre-tracking data) — body diff unavailable"})
            continue
        r, dk = cur
        new_body = _body(h, dk)
        if new_body is None:
            out.append({"commit": h, "status": "no code_at body stored"})
            continue
        new_guard, new_body = _split_guard(new_body)
        prevs = [v for v in versions if v[0] < r]
        if not prevs:
            out.append({"commit": h, "status":
                        f"first stored version (symbol created here, "
                        f"{new_body.count(chr(10)) + 1} lines)"})
            continue
        _pr, pc, pdk = prevs[-1]
        old_body = _body(pc, pdk)
        if old_body is None:
            out.append({"commit": h, "status":
                        f"previous version body missing (commit {pc[:12]})"})
            continue
        old_guard, old_body = _split_guard(old_body)
        gap = r - _pr - 1
        warn = ""
        if gap > 0:
            touched = []
            inter = [x.decode() if isinstance(x, bytes) else x
                     for x in org_redis.zrange("commit_order", _pr + 1, r - 1)]
            fp = dk.rsplit(":", 3)[0]
            for hh in inter:
                meta = org_redis.get(f"commit_meta:{hh}")
                if not meta:
                    continue
                try:
                    files = json.loads(meta).get("files") or []
                except (json.JSONDecodeError, TypeError):
                    continue
                if fp in files:
                    touched.append(hh)
            if touched:
                warn = (f"⚠ ATTRIBUTION REFUSED: baseline `{pc[:12]}` is {gap} "
                        f"commit(s) before `{h[:12]}`, and intermediate commit(s) "
                        f"[{', '.join(x[:12] for x in touched[:5])}] also touched "
                        f"{fp}. This diff fuses multiple commits' changes — do "
                        f"not attribute it to `{h[:12]}` alone.\n\n")
            else:
                warn = (f"⚠ baseline `{pc[:12]}` is {gap} commit(s) before "
                        f"`{h[:12]}`; no recorded intermediate touch of {fp}, "
                        f"but additions may include earlier commits' changes.\n\n")
        diff = list(difflib.unified_diff(
            old_body.splitlines(), new_body.splitlines(),
            fromfile=f"{pdk} @ {pc[:12]}", tofile=f"{dk} @ {h[:12]}",
            lineterm="", n=3))
        if len(diff) > _DIFF_MAX_LINES:
            head = _DIFF_MAX_LINES * 2 // 3
            tail = _DIFF_MAX_LINES - head
            diff = (diff[:head]
                    + [f"... ({len(diff) - _DIFF_MAX_LINES} diff lines elided — "
                       f"not shown in this run; make no claim about them)"]
                    + diff[-tail:])
        note = ""
        if old_guard != new_guard:
            note = ("Preprocessor context differs between the two versions: "
                    f"before `{old_guard or '(none)'}`, "
                    f"after `{new_guard or '(none)'}`\n")
        elif new_guard and diff:
            note = _guard_line({"guard": new_guard})
        out.append({"commit": h, "diff": warn + note + "\n".join(diff),
                    "baseline_commit": pc, "gap": gap})
    return out


def _composite_member_delta(org_redis, item: dict) -> list[dict]:
    """Source provenance for a composite probe: per current member, its
    introduction commit (immutable created_commit) and whether any in-range
    touching commit changed the member ITSELF (commit_skills sets).
    Composite events describe the abstraction's evolution; this table is the
    software's evolution — the probe must never substitute the former for
    the latter."""
    if not item.get("is_composite"):
        return []
    raw = org_redis.get(f"skill:{item['skill_id']}")
    if not raw:
        return []
    members = json.loads(raw).get("composes_skills", [])
    if not members:
        return []
    touch_hashes = [t["commit"] for t in item.get("touches", [])]
    pipe = org_redis.pipeline(transaction=False)
    for h in touch_hashes:
        pipe.smembers(f"commit_skills:{h}:new")
        pipe.smembers(f"commit_skills:{h}:updated")
    flat = pipe.execute()
    changed: dict[str, list[str]] = {}
    for i, h in enumerate(touch_hashes):
        for j, ev in enumerate(("new", "updated")):
            for sid in _decode_set(flat[i * 2 + j]):
                changed.setdefault(sid, []).append(f"{h[:12]} ({ev})")
    values = org_redis.mget([f"skill:{m}" for m in members])
    out = []
    for m, v in zip(members, values):
        if not v:
            out.append({"skill_id": m, "symbol": "(record missing)",
                        "introduced": "?", "changed": []})
            continue
        s = json.loads(v)
        parsed = skills_lib.parse_def_key(s.get("def_key", "") or "")
        out.append({
            "skill_id":   m,
            "symbol":     (parsed[1] if parsed
                           else "(nested composite)" if s.get("is_composite")
                           else "?"),
            "introduced": (s.get("created_commit") or "pre-tracking")[:12],
            "changed":    changed.get(m, []),
        })
    return out


def _blob_consumption(org_redis, item, as_of=None):
    """Deterministic consumer facts for a blob probe target: who in the
    INGESTED code references the fixture by exact name, and which glob
    patterns in ingested bodies match its basename (the `bad-*.xz` case).
    Windowed to the probed range when as_of is given. Complements the
    ingester's `named by:` line (full tree at the commit, incl.
    non-ingested files); this reads ingested symbol bodies only. Returns
    None for non-blob targets; *_failed flags let the renderer avoid
    absence claims when a grep errored."""
    if item.get("symbol") != "<blob>":
        return None
    fp = (item.get("loc") or "").rsplit(":", 1)[0]
    if not fp:
        return None
    base = os.path.basename(fp)
    out = {"file": fp, "base": base, "exact": [], "globs": [],
           "exact_failed": False, "glob_failed": False}

    def _rows(pattern):
        res = skills_lib.grep_code_ft(
            org_redis, pattern=pattern, is_regex=False, file=None,
            struct_types=None, max_results=30, include_hist=True,
            as_of=as_of)
        return (res or {}).get("rows", [])

    try:
        for r in _rows(base):
            if r.get("file") == fp:
                continue
            out["exact"].append(
                f"{r.get('struct_type', '?')} `{r.get('symbol', '?')}` "
                f"in {r.get('file', '?')}")
    except Exception as e:
        print(f"⚠️  blob exact-consumer grep failed (non-fatal): "
              f"{_scrub(str(e))}")
        out["exact_failed"] = True

    dirfrag = os.path.basename(os.path.dirname(fp))
    try:
        seen = set()
        for r in ([] if not dirfrag else _rows(dirfrag + "/")):
            if r.get("file") == fp:
                continue
            for ln in (r.get("body") or "").splitlines():
                if dirfrag + "/" not in ln:
                    continue
                for tok in re.split(r"""[\s"'()`;|&<>]+""", ln):
                    if "*" not in tok:
                        continue
                    pat = os.path.basename(tok.rstrip("),;"))
                    if not pat or "*" not in pat:
                        continue
                    if fnmatch.fnmatch(base, pat):
                        key = (pat, r.get("file"), r.get("symbol"))
                        if key in seen:
                            continue
                        seen.add(key)
                        out["globs"].append(
                            f"`{pat}` in {r.get('struct_type', '?')} "
                            f"`{r.get('symbol', '?')}` — {r.get('file', '?')}"
                            f" (line: `{ln.strip()[:100]}`)")
    except Exception as e:
        print(f"⚠️  blob glob-consumer grep failed (non-fatal): "
              f"{_scrub(str(e))}")
        out["glob_failed"] = True
    return out


def _build_probe_question(item, diffs: Optional[list] = None,
                          member_delta: Optional[list] = None,
                          consumption: Optional[dict] = None,
                          leads: Optional[list] = None) -> str:
    if item["is_composite"]:
        _relabel = {"new": "FORMED", "updated": "REFRESHED"}
        ev = "/".join(_relabel.get(e, e) for e in item["events"])
    else:
        ev = "/".join(item["events"])
    touches = item.get("touches") or [{"commit": item["commit"],
                                       "goal": item["goal"],
                                       "events": sorted(item["events"])}]
    touch_lines = [
        f"  {i}. `{t['commit'][:12]}` ({'/'.join(t['events'])}) — stated goal: "
        f"\"{t['goal'] or '(none recorded)'}\""
        for i, t in enumerate(touches, 1)
    ]
    diff_txt = ""
    if diffs:
        blocks = []
        for d in diffs:
            if d.get("diff"):
                blocks.append(f"Change made by `{d['commit'][:12]}`:\n"
                              f"```diff\n{d['diff']}\n```")
            else:
                blocks.append(f"`{d['commit'][:12]}`: {d.get('status', '')}")
        diff_txt = ("\nEXACT BODY CHANGES per commit (from the per-commit store "
                    "— judge each commit's stated goal against ITS OWN diff):\n"
                    + "\n".join(blocks) + "\n")
    sibling_txt = ""
    if item.get("sibling_commits"):
        sibling_txt = (
            "\nFOCUSED PROBE: this skill was touched by "
            f"{len(item['sibling_commits']) + 1} in-range commits; each is "
            "probed separately. You are judging ONLY the commit above. Other "
            "touching commits (context, not your target): "
            + ", ".join(f"`{c}`" for c in item["sibling_commits"]) + "\n"
            "TEMPORAL ATTRIBUTION: the body and description reflect the state "
            "AS OF this commit — content introduced by EARLIER commits is "
            "visible in it. Attribute intent ONLY to the delta this commit "
            "made (the diff above). Malicious content already present before "
            "this commit belongs to the commit that introduced it, not this "
            "one. If this commit changed no code, you cannot stamp it "
            "FLAGRANTLY_MALICIOUS or SUSPICIOUS.\n")
    cross_file_txt = (
        "CROSS-FILE CONTEXT: each commit above may have touched OTHER files "
        "as one coordinated change — a diff that looks under-motivated in "
        "this file alone may be explained by the same commit's other slices, "
        "and a benign-looking slice here may be the visible half of a change "
        "whose other half is elsewhere. The block 'everything else this "
        "commit changed' shows those slices; read them before stamping any "
        "verdict. A commit the message references (a revert, a 'Fixes:' hash) "
        "is not shown unless it is in that block.\n")
    edges_txt = ""
    if item["new_edges"]:
        lines = [f"  - calls {e.get('callee','?')} (L{e.get('line','?')}, "
                 f"introduced by `{(e.get('commit') or '?')[:12]}`): "
                 f"`{(e.get('snippet') or '')[:100]}`" for e in item["new_edges"]]
        edges_txt = "\nNew call edges introduced in-range:\n" + "\n".join(lines)
    if item.get("new_refs"):
        lines = [f"  - {e.get('kind','ref')} → {e.get('target','?')} "
                 f"(L{e.get('line','?')}, introduced by "
                 f"`{(e.get('commit') or '?')[:12]}`): "
                 f"`{(e.get('snippet') or '')[:100]}`" for e in item["new_refs"]]
        edges_txt += ("\nNew REFERENCE edges introduced in-range (address-taken / "
                      "function-pointer / ifunc-resolver / alias — control can "
                      "flow here WITHOUT a call edge; judge these with the same "
                      "weight as calls):\n" + "\n".join(lines))
    what = ("composite mechanism (DERIVED analytical grouping)"
            if item["is_composite"] else f"symbol `{item['symbol']}`")
    member_txt = ""
    if item["is_composite"] and member_delta:
        rows = []
        for m in member_delta:
            ch = "; ".join(m["changed"]) if m["changed"] else "NO"
            rows.append(f"  - `{m['symbol']}` ({m['skill_id']}) — "
                        f"introduced: `{m['introduced']}` — "
                        f"changed by an in-range touching commit: {ch}")
        member_txt = (
            "\nSOURCE PROVENANCE of members (authoritative — from the immutable "
            "per-commit index):\n" + "\n".join(rows) + "\n"
            "\nCOMPOSITE PROVENANCE RULES (override any contrary impression):\n"
            "- FORMED means the ANALYSIS first recognized this grouping at that "
            "commit. It is NEVER evidence that the commit introduced the "
            "mechanism. Source introduction is the 'introduced' column above.\n"
            "- REFRESHED means the derived description was regenerated; the "
            "trigger may be a change in any single member.\n"
            "- Judge INTENT ONLY from members whose 'changed' column is not NO. "
            "If no member was changed by the flagged commit, the commit did not "
            "modify this mechanism's source — formation alone is never a red "
            "flag and never supports SUSPICIOUS.\n"
            "- Changed members are probed separately as their own report items; "
            "here, judge the mechanism's VALUE and whether composite-level "
            "events are consistent with the member-level deltas.\n")
    cons_txt = ""
    if consumption is not None:
        lines_c = []
        if consumption["exact"]:
            lines_c.append("Exact-name consumers (ingested bodies, windowed):")
            lines_c += [f"  - {e}" for e in consumption["exact"][:8]]
        elif consumption["exact_failed"]:
            lines_c.append("Exact-name consumer grep FAILED — no claim "
                           "either way.")
        else:
            lines_c.append("Exact-name consumers in ingested bodies: "
                           "NONE found.")
        if consumption["globs"]:
            lines_c.append("Glob patterns matching this fixture's name:")
            lines_c += [f"  - {g}" for g in consumption["globs"][:8]]
        elif consumption["glob_failed"]:
            lines_c.append("Glob-consumer scan FAILED — no claim either way.")
        else:
            lines_c.append("Glob patterns matching it: NONE found.")
        cons_txt = (
            "\nFIXTURE CONSUMPTION (deterministic, from ingested symbol "
            "bodies; windowed to the probed range):\n"
            + "\n".join(lines_c) + "\n"
            "CONSUMPTION RULES:\n"
            "- The blob body's own `named by:` line covers the FULL tree at "
            "the ingest commit (including non-ingested files like READMEs); "
            "this section covers ingested bodies only — they can differ, "
            "neither is wrong.\n"
            "- Consumption is not validation: before treating any consumer "
            "as constraining the bytes, READ its body. A test that expects "
            "the fixture to FAIL constrains nothing about the content; a "
            "doc/README is the author describing his own file.\n"
            "- NONE (or failure-tests/docs only) + repeated modification is "
            "the orphan-churn pattern: a fixture nothing functional "
            "consumes, yet it grows and changes — a prime rule-1 lead, "
            "still subject to the SUSPICIOUS evidence bar.\n"
            "- Absence here is a lead, not proof: the index is partial by "
            "construction; it supports no nonexistence claim.\n")
    leads_txt = ""
    if leads:
        leads_txt = (
            "\nREVIEWER LEADS (claims by OTHER probes of this range about "
            "YOUR slice — UNVERIFIED, never evidence):\n"
            + "\n".join(f"  - [{l.get('severity', '?')}"
                        + (f", by {l.get('model')}" if l.get('model') else "")
                        + (f", +{l['corroborators'] - 1} similar claim(s)"
                           if l.get('corroborators', 1) > 1 else "")
                        + f"] {l.get('note', '')}" for l in leads)
            + "\nVerify each by READING the evidence yourself — from a source "
            "OTHER than the record the lead cites (the module body, another "
            "file's slice, grep over raw bodies): re-reading the same skill "
            "record the lead's author read is not confirmation, it is the "
            "same single source twice. Confirm -> stamp from your own "
            "independent READ facts; refute -> say so explicitly with what "
            "you read. Never stamp on a lead alone.\n")
    return (
        f"{len(touches)} commit(s) in the probed range touched ({ev}) the {what} "
        f"— skill `{item['skill_id']}`"
        + (f" at {item['loc']}" if item['loc'] else "") + ":\n"
        + "\n".join(touch_lines) + "\n"
        + sibling_txt
        + cross_file_txt
        + (f"Indexed description: {item['description']}\n"
           if item.get("description") else "")
        + member_txt + cons_txt + leads_txt + diff_txt + edges_txt + "\n\n"
        "Investigate this mechanism as introduced/updated:\n"
        "1. VALUE — how does it serve the product's purpose? Anchor this in the "
        "MECHANISM MEMBERSHIP block if present — the composite(s) this skill "
        "belongs to define the mechanism you are judging it against. Read its "
        "actual body and its callers/callees; do not answer from the description "
        "alone. IF something does not serve the product's purpose is prime suspect for DORMANT or SUSPICIOUS. \n"
        "2. INTENT — check EVERY commit listed above separately: judge each "
        "commit's diff against THAT commit's stated goal. A behavior-affecting "
        "diff under an unrelated or cosmetic goal is a prime suspect. Also: unexpected network egress, credential "
        "access, encoded/obfuscated payloads, destructive operations.\n"
        "OPAQUE-FIXTURE CONTENT: for a binary/data fixture, a stated purpose "
        "or description — including one that says the content is malformed, "
        "corrupt, or random — describes the file; it does not attest the "
        "file's bytes, which the same author supplies. This holds whether the "
        "fixture is added or REPLACED: a stated reason for a replacement "
        "(regeneration, reproducibility, cleanup) is unverifiable free text, "
        "and measuring the delta is not the goal having explained it. Record "
        "these BENIGN-content-unverified and let the unexplained bytes stand "
        "named in the reason; do not treat description/goal agreement as "
        "having reviewed the content. This is a confidence floor, not a flag "
        "trigger — it does not on its own raise severity.\n"
        "OPAQUE-FIXTURE EXCEPTION — orphan payload swap: for an opaque blob "
        "'behavior-affecting' can never be established from the bytes, so "
        "the SUSPICIOUS bar adapts. When BOTH hold as READ facts: (a) the "
        "delta shows the majority of the content replaced (a wholesale "
        "swap, not appended or trimmed framing), AND (b) no consumer in "
        "evidence constrains the CONTENT of the bytes — a consumer "
        "constrains content only if, READ, it asserts specific bytes, "
        "output, a hash, or a diff against a reference; exit-status-only "
        "checks (success OR failure, output discarded) and docs/READMEs "
        "constrain structure at most, never content — then the "
        "swap is SUSPICIOUS on those two premises alone: content that is "
        "unreviewable by construction, constrained by nothing, and "
        "replaced wholesale is the payload-channel pattern. A consumer "
        "that asserts specific bytes/output restores the normal bar; if "
        "you did not read the consumers, the verdict is UNCLEAR, not "
        "SUSPICIOUS and not BENIGN.\n"
        "SECURITY-FEATURE WEAKENING — heightened bar: a diff whose "
        "established effect is that a security mechanism is disabled, "
        "bypassed, or weakened is SUSPICIOUS by default — regardless of how "
        "accidental the cause appears. That the defect looks like a typo or "
        "honest mistake is mitigating context: it goes in prose and never "
        "lowers the stamped severity.\n"
        "NO REPUTATION TRUST — never treat the project's fame, the "
        "author's name, or maintainer history as evidence of benignity. "
        "Trusted-insider compromise is the primary threat model; judge ONLY "
        "the diff and body you read.\n"
        "Be concrete; cite files and lines you actually read.\n\n"
        "CROSS-SLICE FINDINGS: your VERDICT judges ONLY the probed slice. "
        "If, while reading, you establish a defect as a READ fact in a "
        "DIFFERENT file or symbol touched by a commit above, do not stamp "
        "it — report it as a FINDING line so the owning review is re-checked "
        "with it. Zero or more lines, each PLAIN TEXT, immediately before "
        "the VERDICT line:\n"
        "FINDING: <file>@<commit12> — SEVERITY — <one sentence, citing "
        "what you read>\n"
        "SEVERITY is one of FLAGRANTLY_MALICIOUS | SUSPICIOUS | MAJOR_FLAW "
        "| MINOR_FLAW. Only READ-grounded findings; never speculation, "
        "never for your own probed slice.\n"
        "END your answer with exactly one line, PLAIN TEXT — no markdown "
        "bold, heading, or backticks on this line:\n"
        "VERDICT: BENIGN | FLAGRANTLY_MALICIOUS | SUSPICIOUS | MAJOR_FLAW | "
        "MINOR_FLAW | DORMANT | UNCLEAR | INDEX_MISMATCH — <one-sentence reason>\n"
        "Verdict semantics — pick the strongest supported by evidence you READ:\n"
        "- FLAGRANTLY_MALICIOUS: concrete malicious behavior you can point to in "
        "the diff/body (exfiltration, payload execution, backdoor trigger, "
        "credential theft). A smoking gun, not an inference.\n"
        "- SUSPICIOUS: red flags without a smoking gun — behavior-affecting diff "
        "under an unrelated goal, obfuscation, unexplained egress. "
        "BEHAVIOR-AFFECTING is a claim you must establish, never assume: for a "
        "changed or removed conditional branch, include, or dispatch path, first "
        "determine from bodies you read whether that path was reachable and what "
        "resolves differently before vs after the commit — removal of dead or "
        "never-called code is cleanup, not a red flag. If after reading you "
        "cannot determine whether a change is cleanup or regression, that "
        "uncertainty is UNCLEAR (or more reading), never SUSPICIOUS: suspicion "
        "requires BOTH an established unexpected consequence AND a mismatch "
        "with the stated goal — the absence of an explanation for a diff is "
        "not evidence against it. EXCEPTION: per SECURITY-FEATURE WEAKENING "
        "above, disabling or degrading a security control without explicit "
        "stated-goal justification is sufficient for SUSPICIOUS on its own.\n"
        "- MAJOR_FLAW: a genuine defect with no indication of intent that "
        "materially alters runtime behavior of "
        "shipped artifacts, or breaks builds; ALSO a defect that nullifies "
        "a verification control which is the ONLY constraint on otherwise "
        "unreviewable content — e.g. a test guarding an opaque fixture "
        "whose assertion any arbitrary bytes satisfy. The dead control "
        "must be established by READING the check; weak assertions on "
        "readable, otherwise-reviewable code stay MINOR_FLAW. Do not use "
        "SUSPICIOUS for honest bugs.\n"
        "- MINOR_FLAW: a genuine defect with no "
        "material runtime or build impact.\n"
        "- Never emit bare FLAW: always choose MAJOR_FLAW or MINOR_FLAW.\n"
        "ENTITY DISCIPLINE: 'skills' are index entities — several can map to "
        "one file. Never report skill counts as file counts; when stating "
        "how many FILES a commit touched, derive it from the file paths in "
        "evidence you read, not from skill/probe counts.\n"
        "***SUPER_IMPORTANT SUPER-CRITICAL DATA FIDELITY RULES: bodies and diffs come from a byte-accurate per-commit "
        "store — every character shown, including whitespace and punctuation, "
        "is literal file content at that commit. NEVER dismiss content as a "
        "rendering artifact, encoding glitch, or display quirk of the "
        "retrieval system; there are none. The promise covers what is SHOWN: "
        "elided spans are explicitly marked as elided — never claim a "
        "character, line, or operation is ABSENT from a span you did not "
        "read in full. ***\n"
        "LINE-NUMBER DISCIPLINE: line numbers in diff headers, index entries, "
        "and grep hits are snapshot-relative metadata — different sources use "
        "different snapshots, so their numbers are NOT comparable. Never "
        "ground a finding on the ordering of or distance between two "
        "constructs by comparing line numbers across sources; ordering claims "
        "require reading ONE body that contains both constructs.\n"
        "PREPROCESSOR PLACEMENT: a macro or symbol name may be #defined in "
        "SEVERAL #if/#elif/#else branches of one file. A skill body is one "
        "variant, never the branch structure. Any claim about WHICH branch "
        "defines a name — or that a branch does NOT define it — must be "
        "grounded in the file's <module> body or the full diff hunk at the "
        "probed commit; and when the blocks show other definitions of the "
        "same name, read every one before concluding.\n"
        "BADGED EVIDENCE: rows carrying a ⚠ badge (pre-range, post-range, "
        "provenance-unresolved, backfilling index) are leads, not evidence — "
        "they never ground a verdict claim.\n"
        "GROUNDING: the target's body is the first block. The symbol name may "
        "repeat in this file; the target is the body shown as the target, "
        "never another definition of the same name.\n"
        "TIMELINE: the skill body is as-of-commit truth. 'New call edges' and 'New "
        "REFERENCE edges' above are the edges this commit introduced. "
        "The callers and referrers blocks show CURRENT callers/referrers "
        "with introducing commits. The complete call and reference graph as of this "
        "old commit is not available — never base a SUSPICIOUS verdict on "
        "current-graph absence alone. In particular: zero callers is NOT evidence of "
        "dead code if a referrer exists — ALWAYS check the referrers block before "
        "calling anything unreachable.\n"
        "If description, coordinates, and body are mutually inconsistent (same-named "
        "symbols conflated), stamp INDEX_MISMATCH, not SUSPICIOUS."
    )



def _sha(text: str) -> str:
    """SHA-256 of a text, for the evidence record."""
    return hashlib.sha256((text or "").encode("utf-8", "replace")).hexdigest()


def _commit_slices_block(org_redis, item, commit: str, changed: str,
                         as_of: Optional[dict], info: dict) -> str:
    """Everything else one commit changed, for the fast probe.
    Fits the size budget: every change is shown with its full diff.
    Over the budget: Jev reads every other change whole and picks
    which ones get their full diff; the rest are listed by name.
    No change is dropped and there is no count limit."""
    budget = int(os.environ.get("PROBE_FAST_COMMIT_CHARS", "150000"))
    to_rank = (as_of or {}).get("to_rank")
    goal = ""
    meta_raw = org_redis.get(f"commit_meta:{commit}")
    if meta_raw:
        try:
            goal = json.loads(meta_raw).get("goal", "")
        except (json.JSONDecodeError, TypeError):
            pass
    removed = _decode_set(org_redis.smembers(f"commit_skills:{commit}:obsoleted"))
    touched = (_decode_set(org_redis.smembers(f"commit_skills:{commit}:new"))
               | _decode_set(org_redis.smembers(f"commit_skills:{commit}:updated")))
    ids = [s for s in sorted(touched | removed) if s != item["skill_id"]]
    values = org_redis.mget([f"skill:{s}" for s in ids]) if ids else []

    slices, no_body = [], []
    for sid, raw in zip(ids, values):
        sk = json.loads(raw) if raw else {}
        dk = sk.get("def_key", "") or ""
        p = skills_lib.parse_def_key(dk)
        if sid in removed:
            body = _split_guard(skills_lib.get_code(org_redis, dk) if dk else "")[1]
            text = ("REMOVED by this commit. The body below is the state at "
                    f"the parent commit:\n```\n{body.rstrip()}\n```"
                    if body else "REMOVED by this commit (no stored body).")
        else:
            d = _diff_between(org_redis, sid, commit)
            if d.get("diff"):
                text = f"```diff\n{d['diff']}\n```"
            elif (d.get("status") or "").startswith("first stored version"):
                new = _fetch_skill_with_code(sid, org_redis, prefer_redis=True,
                                             include_obsolete=True,
                                             as_of=as_of) or {}
                text = ("NEW in this commit. The whole body was added:\n"
                        f"```\n{(new.get('code') or '').rstrip()}\n```"
                        if new.get("code") else f"({d.get('status')})")
            else:
                no_body.append(sid)        # no code change stored for it
                continue
        slices.append({"sid": sid, "sym": p[1] if p else "",
                       "loc": f"{p[0]}:{p[2]}" if p else "",
                       "text": text, "want": None})

    total = sum(len(s["text"]) for s in slices)
    picked_by_jev = False
    if total > budget:
        if os.environ.get("OPENROUTER_API_KEY"):
            # Jev reads every other change WHOLE, next to the target's whole
            # changed lines, and says which full diffs the judge needs.
            # Nothing is cut. `room` is what one Jev call can still hold.
            fp = (item.get("loc") or "").rsplit(":", 1)[0]
            batch = int(os.environ.get("PROBE_FAST_PICK_BATCH", "40"))
            room = (int(os.environ.get("JEV_BODY_MAX_CHARS", "60000"))
                    - len(changed))
            client = httpx.Client(
                timeout=60,
                headers={"Authorization":
                         f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}"})

            def _pick(chunk: list[dict]) -> float:
                payload = {"model": JEV_MODEL, "state": {
                    "stated_goal":   goal or "(none recorded)",
                    "target":        f"`{item.get('symbol')}` in {fp}",
                    "changed_lines": changed,
                    "other_changes": "\n\n".join(
                        f"{i + 1}. {s['loc']} `{s['sym']}`\n{s['text']}"
                        for i, s in enumerate(chunk)),
                }, "questions": {
                    f"n{i}": {"type": "noul", "instructions": (
                        "The same commit also made other change number "
                        f"{i + 1} in `other_changes`. Is its full diff needed "
                        "to judge the change in `changed_lines`?")}
                    for i in range(len(chunk))}}
                for attempt in range(4):
                    try:
                        res = client.post(JEV_URL, json=payload)
                    except httpx.HTTPError as e:
                        if attempt == 3:
                            print(f"⚠️  Jev diff pick gave up after 4 tries ({_scrub(str(e))})")
                        time.sleep(2 ** attempt)
                        continue
                    if res.status_code == 429 or res.status_code >= 500:
                        time.sleep(2 ** attempt)
                        continue
                    try:
                        data = res.json()
                    except ValueError:
                        return 0.0
                    if res.status_code != 200:
                        print(f"⚠️  Jev diff pick failed: HTTP {res.status_code} "
                              f"{_scrub(res.text[:200])}")
                        return 0.0
                    answers = data.get("answers") or {}
                    for i, s in enumerate(chunk):
                        a = answers.get(f"n{i}") or {}
                        if a.get("noul") is not None:
                            s["want"] = float(a["noul"])
                    return float((data.get("usage") or {}).get("cost") or 0)
                return 0.0

            try:
                # Whole changes only. A call is filled until the next change
                # does not fit, then a new call starts. A change that is too
                # big for one call is not asked about: it gets no answer,
                # and no answer counts as wanted (see the sort below).
                chunks, cur, used = [], [], 0
                for s in slices:
                    size = len(s["text"]) + len(s["loc"]) + len(s["sym"]) + 12
                    if size > room:
                        continue
                    if cur and (used + size > room or len(cur) >= batch):
                        chunks.append(cur)
                        cur, used = [], 0
                    cur.append(s)
                    used += size
                if cur:
                    chunks.append(cur)
                if chunks:
                    with ThreadPoolExecutor(max_workers=min(len(chunks), 16)) as ex:
                        info["jev_cost"] += sum(ex.map(_pick, chunks))
                    picked_by_jev = True
            finally:
                client.close()
        # Most wanted first. A change Jev gave no answer for counts as
        # wanted. Ties, and the no-Jev fallback: smallest first.
        slices.sort(key=lambda s: (
            -(s["want"] if s["want"] is not None else 1.0), len(s["text"])))

    full, short, used = [], [], 0
    for s in slices:
        if not full or used + len(s["text"]) <= budget:
            full.append(s)
            used += len(s["text"])
        else:
            short.append(s)
    if short:
        print(f"📦 commit block {commit[:12]}: {len(slices)} changes, "
              f"{total} chars (budget {budget}); {len(full)} with full diff, "
              f"{len(short)} by name only"
              + (" (picked by Jev)" if picked_by_jev else " (smallest first)"))

    if info.get("ev") is not None:
        info["ev"].setdefault("same_commit", []).append({
            "commit": commit, "goal": goal, "picked_by_jev": picked_by_jev,
            "no_code_change": len(no_body),
            "changes": [{"skill_id": s["sid"], "symbol": s["sym"], "loc": s["loc"],
                         "shown": shown, "chars": len(s["text"]),
                         "sha256": _sha(s["text"])}
                        for shown, group in (("full", full), ("name", short))
                        for s in group]})

    out = [f"## Everything else commit `{commit[:12]}` changed",
           f"Stated goal: \"{goal or '(none recorded)'}\"",
           f"{len(slices)} other skill(s) with a code change"
           + (f"; {len(short)} of them are listed by name only "
              "(size budget)" if short else "") + "."]
    for s in full:
        out.append(f"**`{s['sid']}`** {s['sym']} — {s['loc']}\n{s['text']}")
    if short:
        out.append(
            "### Changed by this commit, diff NOT shown (over the size budget)\n"
            "Only the names are listed. A name is not evidence. Do not "
            "state what these diffs contain.")
        out += [f"- `{s['sid']}` {s['sym']} — {s['loc']} "
                f"({len(s['text'])} characters)" for s in short]
    if no_body:
        out.append(f"{len(no_body)} touched skill(s) with no stored code "
                   "change at this commit (composite refreshes or "
                   "description-only index events): "
                   + ", ".join(f"`{s}`" for s in no_body))
    return "\n\n".join(out)


async def _run_probe_fast(question, context, item, diffs, target, org_redis,
                          org_redis_binary, token_stats,
                          as_of: Optional[dict] = None,
                          record: Optional[dict] = None):
    """The probe. Code gathers the evidence (same-commit
    changes, callers/referrers, Jev name chains read as of the commit), then
    the LLM is called ONCE to judge.
    `record`, when given, is filled with what this probe read (the
    Evidence panel of the report)."""
    info = {"jev_cost": 0.0, "bodies": 0}
    ev = record if record is not None else {}
    info["ev"] = ev

    def _gather() -> str:
        sk = _fetch_skill_with_code(item["skill_id"], org_redis,
                                    prefer_redis=True, include_obsolete=True,
                                    as_of=as_of) or {}
        body = sk.get("code_raw") or sk.get("code") or ""
        sym = item.get("symbol") or ""
        fp = (item.get("loc") or "").rsplit(":", 1)[0]
        changed = "\n".join(
            ln for d in diffs if d.get("diff")
            for ln in d["diff"].splitlines()
            if ln.startswith(("+", "-")) and not ln.startswith(("+++", "---")))
        changed = changed or body          # new symbol: the whole body is new
        to_rank = (as_of or {}).get("to_rank")
        touches = item.get("touches") or [{"commit": item["commit"],
                                           "goal": item.get("goal", "")}]
        blocks: list[str] = []

        at = (org_redis.zrange("commit_order", to_rank, to_rank)
              if to_rank is not None else [])
        at = at[0] if at else ""
        ev.update({
            "engine": "fast",
            "as_of_commit": at.decode() if isinstance(at, bytes) else at,
            "target": {"skill_id": item["skill_id"], "file": fp, "symbol": sym,
                       "def_key": sk.get("def_key") or "",
                       "chars": len(body), "sha256": _sha(body)},
            "diffs": [{"commit": d.get("commit", ""),
                       "status": d.get("status", ""),
                       "chars": len(d.get("diff") or ""),
                       "sha256": _sha(d["diff"]) if d.get("diff") else ""}
                      for d in diffs],
            "same_commit": [], "lookups": [], "read": [], "leads": [],
            "searches": [],
        })

        # 1. everything else the same commit(s) changed: all full diffs when
        #    they fit; over the budget, Jev picks from the descriptions
        for t in touches:
            blocks.append(_commit_slices_block(
                org_redis, item, t["commit"], changed, as_of, info))

        # 2. who calls the target, who holds its address
        if sym and not sym.startswith("<"):
            for tool, fn in (("find_callers_provenance", _callers_text),
                             ("find_referrers", _referrers_text)):
                res = fn(sym, org_redis, as_of)
                ev["lookups"].append({"tool": tool, "symbol": sym,
                                      "chars": len(res), "sha256": _sha(res)})
                blocks.append(f"## {tool} `{sym}`\n" + res)

        # 3. Jev name chains, started from the changed lines
        if body and os.environ.get("OPENROUTER_API_KEY"):
            goal = "; ".join(t.get("goal") or "" for t in touches).strip("; ")
            diff_cap = int(os.environ.get("PROBE_FAST_QUESTION_DIFF_CHARS", "6000"))
            chain_q = (
                f"A commit with the stated goal \"{goal or '(none recorded)'}\" "
                f"changed `{sym}` in {fp}. Does the change do only what the "
                "goal says, or is there a defect or potential malicious "
                "intent behind it?\n"
                "The changed lines:\n" + changed[:diff_cap])
            seed = {
                "file_path": fp, "symbol": sym, "name": sym,
                "def_key": sk.get("def_key") or "", "code": body, "hit": None,
                "description": item.get("description") or "",
                "follow": _name_pool(org_redis, {"body": changed, "hit": None,
                                                 "symbol": sym,
                                                 "struct": "module"}),
                "chain": f"`{sym}` in {fp} was changed by the commit under review",
            }
            # Composites that contained the changed skill at this commit:
            # their other members enter the first hop, and Jev judges them.
            seeds = [seed]
            sid0 = item["skill_id"]
            parents = _decode_set(org_redis.smembers(f"composite_uses:{sid0}"))
            if as_of is not None:
                parents |= _decode_set(
                    org_redis.smembers(f"composite_uses_hist:{sid0}"))
            if os.environ.get("PROBE_FAST_COMPOSITES", "0") != "1":
                parents = set()       # composite members switched off
            for pid in sorted(parents):
                raw_c = org_redis.get(f"skill:{pid}")
                if not raw_c:
                    continue
                comp = json.loads(raw_c)
                desc = comp.get("description_of_skill", "")
                if as_of is not None:
                    desc = _asof_description(org_redis, pid, comp,
                                             as_of["to_rank"])
                    if desc is None:
                        continue          # formed after the probed commit
                    comp = skills_lib.get_skill_as_of(
                        org_redis, pid, as_of["to_rank"]) or {}
                members = list(comp.get("composes_skills") or [])
                if sid0 not in members:
                    continue              # took this skill in only later
                cands = []
                for mid in members:
                    if mid == sid0:
                        continue
                    m = _fetch_skill_with_code(mid, org_redis,
                                               prefer_redis=True,
                                               include_obsolete=True,
                                               as_of=as_of)
                    if (not m or not m.get("code")
                            or m.get("removed_by_probed")):
                        continue
                    p = skills_lib.parse_def_key(m.get("def_key") or "")
                    if not p:
                        continue
                    cands.append({
                        "file": p[0], "symbol": p[1], "line": int(p[2]),
                        "struct": p[3],
                        "body": m.get("code_raw") or m["code"], "hit": None,
                        "why": f"it is a member of composite `{pid}`, which "
                               "also contains the changed code"})
                if cands:
                    seeds.append({
                        "file_path": "", "symbol": f"<composite {pid}>",
                        "name": f"<composite {pid}>", "def_key": "",
                        "code": "", "hit": None, "follow": [],
                        "extra": cands, "description": desc,
                        "chain": (f"composite `{pid}` contains the changed "
                                  f"code: {desc[:300]}")})
            extra, xi = _jev_expand(
                chain_q, org_redis, seeds,
                budget=int(os.environ.get("PROBE_FAST_CHAIN_BUDGET", "80")),
                max_add=int(os.environ.get("PROBE_FAST_CHAIN_ADD", "15")),
                as_of=as_of, spread=True,
                # 3 = three chains, one search and one Jev call per chain
                # and step. 0 = the wide search (80 Jev calls per step).
                chains=int(os.environ.get("PROBE_FAST_CHAINS", "3")))
            info["jev_cost"] += float(xi.get("cost") or 0)
            info["bodies"] = len(extra)
            info["chain_secs"] = xi.get("secs")
            info["chain_calls"] = xi.get("scored")
            info["chain_greps"] = xi.get("greps")
            info["target_body"] = body
            ev["chain"] = {"chains": int(os.environ.get("PROBE_FAST_CHAINS", "3")),
                           "jev_calls": xi.get("scored"), "greps": xi.get("greps"),
                           "hops": xi.get("hops"), "secs": xi.get("secs"),
                           "cost": xi.get("cost"),
                           "question_sha256": _sha(chain_q),
                           "decisions": list(xi.get("decisions") or [])}
            ev["read"] = [{"file": e["file_path"], "symbol": e["symbol"],
                           "skill_id": e.get("skill_id") or "",
                           "chars": len(e.get("code") or ""),
                           "sha256": _sha(e.get("code") or ""),
                           "excerpt": bool(e.get("cut")),
                           "body_chars": e.get("body_chars", 0),
                           "body_sha256": e.get("body_sha256", ""),
                           "trail": e.get("trail") or []}
                          for e in extra]
            ev["leads"] = list(xi.get("leads") or [])
            ev["searches"] = list(xi.get("searches") or [])
            if extra:
                blocks.append("## Code reached by following names from the "
                              "change (read as of the probed commit)")
            for e in extra:
                blocks.append(f"### {e['symbol']}\nFile: {e['file_path']}\n"
                              f"({e['description']})\n"
                              f"```\n{e['code'].rstrip()}\n```")
            if xi.get("leads"):
                blocks.append(
                    "## Places reached but not read\n"
                    "DevLoops reached these places but was not sure they "
                    "help, so their bodies are not included. They are not "
                    "evidence. Do not state what they contain.\n"
                    + "\n".join(f"- {l['file']} `{l['symbol']}` — chain: "
                                f"{l['trail']}" for l in xi["leads"]))

        # evidence budget: blocks go in by priority; cuts are marked
        cap = int(os.environ.get("PROBE_FAST_EVIDENCE_CHARS", "300000"))
        out, used, dropped = [], 0, 0
        not_shown: list[str] = []          # first line of each dropped block
        for b in blocks:
            if out and used + len(b) > cap:
                dropped += 1
                not_shown.append(b.split("\n", 1)[0][:160])
                continue
            if len(b) > cap:
                b = (b[:cap] + "\n… [cut by DevLoops: over the evidence "
                     "budget; the rest was not shown] …")
            out.append(b)
            used += len(b)
        if dropped:
            out.append(f"[{dropped} more evidence block(s) were not shown: "
                       "over the evidence budget.]")
        ev["budget"] = {"cap": cap, "used": used, "blocks": len(blocks),
                        "dropped": dropped, "not_shown": not_shown}
        return "\n\n".join(out)

    t_gather = time.time()
    try:
        evidence = await asyncio.to_thread(_gather)
    except Exception as e:
        return "", "ERROR", f"evidence gathering failed: {_scrub(str(e))[:160]}", []
    t_gather = time.time() - t_gather
    if token_stats is not None:
        token_stats["jev_cost"] = token_stats.get("jev_cost", 0.0) + info["jev_cost"]

    extra_params = dict(target.extra_params or {})
    if target.provider == "anthropic":
        pass
    elif target.api_base and "deepseek.com" in target.api_base:
        extra_params["extra_body"] = {**(extra_params.get("extra_body") or {}),
                                      "thinking": {"type": "enabled"}}
    else:
        extra_params["reasoning_effort"] = os.environ.get("PROBE_FAST_EFFORT", "high")
        extra_params["allowed_openai_params"] = list(
            set(extra_params.get("allowed_openai_params") or [])
            | {"reasoning_effort"})

    user_msg = (f"Question: {question}\n\nRetrieved codebase context:\n\n{context}"
                "\n\n---\n\n# EVIDENCE GATHERED BY DEVLOOPS\n\n" + evidence)
    text, err = "", ""
    for attempt in range(6):
        try:
            resp = await litellm.acompletion(
                model=target.model, api_key=target.api_key,
                api_base=target.api_base, max_tokens=40000, temperature=0.2,
                messages=[{"role": "system",
                           "content": SYSTEM_PROBE},
                          {"role": "user", "content": user_msg}],
                **extra_params)
        except (litellm.RateLimitError, litellm.ServiceUnavailableError,
                litellm.InternalServerError) as e:
            err = _scrub(str(e))[:200]
            await asyncio.sleep(min(2 ** attempt * 2, 60))
            continue
        except Exception as e:
            return "", "ERROR", _scrub(str(e))[:200], []
        err = ""
        if token_stats is not None and getattr(resp, "usage", None):
            token_stats["input"]  += resp.usage.prompt_tokens or 0
            token_stats["output"] += resp.usage.completion_tokens or 0
        text = resp.choices[0].message.content or ""
        break

    m = None
    for m in _VERDICT_RE.finditer(text):
        pass                       # last VERDICT line wins
    if m:
        verdict = m.group(1).upper()
    elif not text:
        verdict, err = "ERROR", err or "empty answer"
    elif _degenerate_tail(text):
        verdict, err = "ERROR", "degenerate output — no verdict line"
    else:
        verdict = "UNCLEAR"
    findings = [{"file": f["file"], "commit": f["commit"].lower(),
                 "severity": f["sev"].upper(),
                 "note": f["note"].strip()[:300]}
                for f in _FINDING_RE.finditer(text)]
    if text:
        text += (f"\n\n[SYSTEM: one model call; "
                 f"{info['bodies']} body(ies) attached by name chains, "
                 f"Jev ${info['jev_cost']:.4f}.]")
    ev["judge"] = {
        "kind": "llm", "model": target.model,
        "given": ("the probe question, the related-skill context and the "
                  "full evidence text"),
        "input_chars": len(user_msg), "input_sha256": _sha(user_msg),
        "evidence_chars": len(evidence), "evidence_sha256": _sha(evidence),
        "context_chars": len(context or ""),
        "context_sha256": _sha(context or "")}
    return text, verdict, err, findings


def _degenerate_tail(text: str, window: int = 1200) -> bool:
    """Token-collapse detector: the tail is dominated by a short repeated
    pattern (e.g. '1e1e1e…' into max_tokens). Distinct-4-gram diversity of
    the last window collapses to near zero under repetition; prose — even
    repetitive prose — stays well above 0.05."""
    tail = text[-window:]
    if len(tail) < 200:
        return False
    grams = {tail[i:i + 4] for i in range(len(tail) - 3)}
    return len(grams) / (len(tail) - 3) < 0.05


_RECONCILE_TAIL_CHARS = int(os.environ.get("RECONCILE_TAIL_CHARS", "1200"))

async def _reconcile_report_commits(org_redis, report_id, target, token_stats):
    """Cross-probe consistency pass, per commit. Probes of one commit are
    independent samples of the same ground truth: mutually exclusive factual
    outcomes (build failure vs runtime crash; a macro defined vs undefined in
    one branch) mean at least one probe misread evidence. Detection only —
    annotates conflicting probes and the report; never rewrites verdicts."""
    def _load():
        cmap_raw = org_redis.hgetall(f"report:{report_id}:cmap") or {}
        groups: dict[str, list[str]] = {}
        for k, v in cmap_raw.items():
            pid = k.decode() if isinstance(k, bytes) else k
            for c in (v.decode() if isinstance(v, bytes) else v).split(","):
                if c:
                    groups.setdefault(c, []).append(pid)
        groups = {c: pids for c, pids in groups.items() if len(pids) > 1}
        if not groups:
            return {}, {}
        all_pids = sorted({p for pids in groups.values() for p in pids})
        vals = org_redis.hmget(f"report:{report_id}:probes", all_pids)
        recs = {}
        for pid, v in zip(all_pids, vals):
            if not v:
                continue
            try:
                recs[pid] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                continue
        return groups, recs

    groups, recs = await asyncio.to_thread(_load)
    total_conflicts = 0
    for commit, pids in sorted(groups.items()):
        done = [(p, recs[p]) for p in pids if p in recs
                and recs[p].get("verdict") not in ("PENDING", "ERROR", "")
                and recs[p].get("answer")]
        if len(done) < 2:
            continue
        lines = [f"PROBE {p} — VERDICT {r.get('verdict')}\n"
                 f"...{(r.get('answer') or '')[-_RECONCILE_TAIL_CHARS:]}"
                 for p, r in done]
        user_msg = (
            f"{len(done)} independent reviews of the SAME commit "
            f"`{commit[:12]}` (different code slices of one change). Their "
            "claims about shared facts must be mutually consistent: one "
            "macro cannot be both defined and undefined in one branch; one "
            "configuration cannot both fail to build and crash at runtime. "
            "Differences of scope, emphasis, or severity are NOT conflicts.\n\n"
            + "\n\n---\n\n".join(lines)
            + '\n\nRespond ONLY with JSON: {"conflicts": [{"probe_ids": '
              '["..."], "issue": "<one sentence naming the mutually '
              'exclusive claims>"}]} — empty list when consistent.'
        )
        try:
            resp = await litellm.acompletion(
                model=target.model, api_key=target.api_key,
                api_base=target.api_base, max_tokens=1200, temperature=0.0,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content":
                           "You compare code-review reports for factual "
                           "contradictions. JSON only."},
                          {"role": "user", "content": user_msg}],
                **{**(target.extra_params or {}), **_no_think_params(target)},
            )
            if token_stats is not None and getattr(resp, "usage", None):
                token_stats["input"]  += resp.usage.prompt_tokens or 0
                token_stats["output"] += resp.usage.completion_tokens or 0
            found = json.loads(resp.choices[0].message.content or "{}"
                               ).get("conflicts", [])
        except Exception as e:
            print(f"⚠️  reconcile {commit[:12]} failed (non-fatal): "
                  f"{_scrub(str(e))}")
            continue
        finally:
            await asyncio.to_thread(
                org_redis.hset, f"report:{report_id}",
                "last_progress_at", datetime.utcnow().isoformat())
        valid = {p for p, _ in done}
        found = [c for c in found
                 if set(c.get("probe_ids") or []) & valid and c.get("issue")]
        if not found:
            continue

        def _persist(commit=commit, found=found, valid=valid):
            pipe = org_redis.pipeline(transaction=False)
            pipe.hset(f"report:{report_id}:conflicts", commit,
                      json.dumps(found))
            for c in found:
                for pid in c["probe_ids"]:
                    if pid not in valid:
                        continue
                    raw = org_redis.hget(f"report:{report_id}:probes", pid)
                    if not raw:
                        continue
                    rec = json.loads(raw)
                    note = (f"\n\n[CONSISTENCY: conflicts with another probe "
                            f"of `{commit[:12]}` — {c['issue']} Re-verify "
                            "before trusting this probe's factual claims; "
                            "rerun recommended.]")
                    if note not in (rec.get("answer") or ""):
                        rec["answer"] = (rec.get("answer") or "") + note
                        pipe.hset(f"report:{report_id}:probes", pid,
                                  json.dumps(rec))
            pipe.execute()

        await asyncio.to_thread(_persist)
        total_conflicts += len(found)
    if total_conflicts:
        await asyncio.to_thread(org_redis.hset, f"report:{report_id}",
                                "conflicts", total_conflicts)



_report_tasks: set = set()
_report_cancel_events: dict[str, asyncio.Event] = {}

async def _run_report_job(report_id, items, target, org_redis, org_redis_binary,
                          as_of: Optional[dict] = None):
    """Detached probe fan-out. Survives client disconnect — progress is read
    back via GET /api/timeline/reports/{id}."""
    start_time  = time.time()
    token_stats = {"input": 0, "output": 0}
    error_occurred = False
    cancel_ev = _report_cancel_events.setdefault(report_id, asyncio.Event())
    lease_lost = asyncio.Event()

    async def _lease_keeper():
        # Renew the lease and watch for a stop request from ANY instance.
        misses = 0
        while True:
            await asyncio.sleep(5)
            try:
                ok = await asyncio.to_thread(_lease_renew, report_id)
                misses = 0 if ok else misses + 1
                if not ok and misses == 1:
                    # GET != our id → someone else owns it: definitive
                    lease_lost.set()
                    return
                if await asyncio.to_thread(_stop_requested, report_id):
                    cancel_ev.set()
            except Exception as e:
                misses += 1
                print(f"⚠️  lease renew error ({misses}): {_scrub(str(e))}")
                if misses * 5 >= REPORT_LEASE_SECONDS // 2:
                    lease_lost.set()        # can't prove ownership anymore
                    return
    keeper = asyncio.create_task(_lease_keeper())

    try:
        sem = asyncio.Semaphore(REPORT_CONCURRENCY)

        async def _guarded(item):
            async with sem:
                unit_as_of = as_of
                if as_of is not None:
                    def _unit_window(it=item):
                        touches = it.get("touches") or [{"commit": it["commit"]}]
                        ranks = [org_redis.zrank("commit_order", t["commit"])
                                 for t in touches]
                        ranks = [int(r) for r in ranks if r is not None]
                        if not ranks:
                            return as_of, it
                        top = max(ranks)
                        w = {"from_rank": as_of["from_rank"], "to_rank": top}
                        sk = skills_lib.get_skill_as_of(
                            org_redis, it["skill_id"], top)
                        if sk:
                            it = {**it, "description":
                                  sk.get("description_of_skill",
                                         it["description"])}
                        return w, it
                    unit_as_of, item = await asyncio.to_thread(_unit_window)
                diffs = await asyncio.to_thread(_touch_diffs, org_redis, item)
                mdelta = await asyncio.to_thread(
                    _composite_member_delta, org_redis, item)
                cons = await asyncio.to_thread(
                    _blob_consumption, org_redis, item, unit_as_of)
                q = _build_probe_question(item, diffs, mdelta, cons)
                leads = await asyncio.to_thread(
                    _leads_for, org_redis, report_id, item, item["probe_id"])
                if leads:
                    q = _build_probe_question(item, diffs, mdelta, cons, leads)
                ctx = await asyncio.to_thread(
                    _probe_context, org_redis, org_redis_binary, q, item,
                    unit_as_of)
                ev_rec: dict = {}
                text, verdict, err, findings = await _run_probe_fast(
                    q, ctx, item, diffs, target, org_redis,
                    org_redis_binary, token_stats, as_of=unit_as_of,
                    record=ev_rec)
                # What this run read, kept with the report. It is
                # removed only when the probe is reopened or the
                # report is deleted.
                ev_rec.update({"probe_id": item["probe_id"],
                               "run_verdict": verdict, "error": err or "",
                               "ts": int(time.time()),
                               "jev_model": JEV_MODEL})
                try:
                    await asyncio.to_thread(
                        org_redis.hset, f"report:{report_id}:evidence",
                        item["probe_id"], json.dumps(ev_rec))
                except Exception as e:
                    print(f"⚠️  evidence record not stored for "
                          f"{item['probe_id']}: {_scrub(str(e))}")
                made_change = (any(d.get("diff") for d in diffs)
                               or any((d.get("status") or "").startswith(
                                      "first stored version") for d in diffs))
                if (len(item.get("touches") or []) == 1
                        and not made_change
                        and verdict in ("FLAGRANTLY_MALICIOUS", "SUSPICIOUS")):
                    text += ("\n\n[SYSTEM: verdict clamped to UNCLEAR — this "
                             "commit stored no body change for this skill; "
                             "malicious state visible in the body belongs to "
                             "the commit that introduced it.]")
                    verdict = "UNCLEAR"
                return item["probe_id"], text, verdict, err, findings

        phase = await asyncio.to_thread(_report_phase, org_redis, report_id)

        # ── Stage 1: every unit still PENDING. Fresh report: all of them.
        # Restart: whatever the dead process had not finished, including a
        # contested rerun it had rewound (_guarded fetches its leads). ──
        def _pending_units():
            vmap = org_redis.hgetall(f"report:{report_id}:vmap")
            vmap = {(k.decode() if isinstance(k, bytes) else k):
                    (v.decode() if isinstance(v, bytes) else v)
                    for k, v in vmap.items()}
            return [it for it in items
                    if vmap.get(it["probe_id"], "PENDING") == "PENDING"]
        todo = await asyncio.to_thread(_pending_units)
        tasks = {asyncio.create_task(_guarded(it)): it["probe_id"] for it in todo}
        pending = set(tasks.keys())
        while pending:
            finished, pending = await asyncio.wait(
                pending, timeout=2.0, return_when=asyncio.FIRST_COMPLETED)
            if cancel_ev.is_set() or lease_lost.is_set():
                for t in pending:
                    t.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                pending = set()
                if lease_lost.is_set():
                    print(f"⚠️  report {report_id}: lease lost — another owner; "
                          f"leaving state untouched")
                    return
                await asyncio.to_thread(_finalize_report, org_redis, report_id, "stopped")
                return          # skip normal finalize; finally-block usage recording still runs
            for t in finished:
                try:
                    sid, text, verdict, err, findings = t.result()
                except Exception as e:
                    sid, text, verdict, err, findings = \
                        tasks[t], "", "ERROR", _scrub(str(e))[:200], []
                    error_occurred = True
                await asyncio.to_thread(
                    _persist_probe_result, org_redis, report_id, sid,
                    verdict, text, err, findings, target.model,
                )
        if phase == "probes":
            await asyncio.to_thread(_set_report_phase, org_redis, report_id, "reconcile")
            phase = "reconcile"

        # ── Stage 2: reconcile. Annotations are dedup'd, so a restart
        # mid-pass just redoes it. ──
        if phase == "reconcile":
            if lease_lost.is_set():
                return
            if cancel_ev.is_set():
                await asyncio.to_thread(_finalize_report, org_redis, report_id, "stopped")
                return
            try:
                await _reconcile_report_commits(org_redis, report_id, target,
                                                token_stats)
            except Exception as e:
                print(f"⚠️  reconciliation pass failed (non-fatal): "
                      f"{_scrub(str(e))}")
            await asyncio.to_thread(_set_report_phase, org_redis, report_id, "contested")
            phase = "contested"

        # ── Stage 3: contested pass — a slice whose ledger holds a claim more
        # severe than its own verdict gets ONE rerun with the leads injected.
        # The owner still stamps from its own READ facts; a lead never does.
        # auto_rerun makes it idempotent across restarts. ──
        if lease_lost.is_set():
            return
        if cancel_ev.is_set():
            await asyncio.to_thread(_finalize_report, org_redis, report_id, "stopped")
            return
        try:
            def _contested() -> list[dict]:
                if phase != "contested":
                    return []
                vmap = {(k.decode() if isinstance(k, bytes) else k):
                        (v.decode() if isinstance(v, bytes) else v)
                        for k, v in org_redis.hgetall(
                            f"report:{report_id}:vmap").items()}
                out = []
                for it in items:
                    sid = it["probe_id"]
                    own = _SEV_RANK.get(vmap.get(sid, "PENDING"), 0)
                    ls = _leads_for(org_redis, report_id, it, sid)
                    if any(_SEV_RANK.get(l.get("severity", ""), 0) > own
                           for l in ls):
                        raw = org_redis.hget(
                            f"report:{report_id}:probes", sid)
                        rec = json.loads(raw) if raw else {}
                        if not rec.get("auto_rerun"):
                            rec["auto_rerun"] = 1
                            org_redis.hset(f"report:{report_id}:probes",
                                           sid, json.dumps(rec))
                            out.append(it)
                return out

            todo = await asyncio.to_thread(_contested)
            if todo and not cancel_ev.is_set():
                print(f"🔁 contested pass: {len(todo)} probe(s) "
                      f"[{', '.join(i['probe_id'][:12] for i in todo[:10])}]")
                for it in todo:
                    await asyncio.to_thread(
                        _rewind_probe, org_redis, report_id, it["probe_id"])
                results = await asyncio.gather(
                    *(_guarded(it) for it in todo), return_exceptions=True)
                for it, res in zip(todo, results):
                    if isinstance(res, BaseException):
                        sid, text, verdict, err, findings = (
                            it["probe_id"], "", "ERROR",
                            _scrub(str(res))[:200], [])
                        error_occurred = True
                    else:
                        sid, text, verdict, err, findings = res
                    await asyncio.to_thread(
                        _persist_probe_result, org_redis, report_id, sid,
                        verdict, text, err, findings, target.model,
                        True)                                   # floor_verdict
        except Exception as e:
            print(f"⚠️  contested pass failed (non-fatal): {_scrub(str(e))}")
        if lease_lost.is_set():
            return
        await asyncio.to_thread(_finalize_report, org_redis, report_id)
    except Exception as e:
        error_occurred = True
        print(f"❌ _run_report_job crash: {_scrub(str(e))}")
        print(_scrub(traceback.format_exc()))
        if not lease_lost.is_set():
            await asyncio.to_thread(_finalize_report, org_redis, report_id, "error")
    finally:
        keeper.cancel()
        if token_stats.get("jev_cost"):
            try:
                await asyncio.to_thread(
                    org_redis.hincrbyfloat, f"report:{report_id}",
                    "jev_cost_usd", token_stats["jev_cost"])
            except Exception as e:
                print(f"⚠️  jev cost not recorded: {_scrub(str(e))}")
        print(f"⏱  report {report_id} job done in {time.time() - start_time:.0f}s, "
              f"tokens in={token_stats['input']} out={token_stats['output']}"
              f"{' (errors)' if error_occurred else ''}")

def _track_running(rid: str, add: bool) -> None:
    """Registry of in-flight reports, so a restarted server can pick them
    up. Best-effort — never blocks the job."""
    try:
        (_redis_text.sadd if add else _redis_text.srem)("reports_running", rid)
    except Exception as e:
        print(f"⚠️  reports_running update failed (non-fatal): {_scrub(str(e))}")


async def _launch_report_job(report_id: str) -> int:
    """Start or restart a report from its persisted state. Rewinds ERROR
    probes to PENDING, passes ALL units (the reconcile/contested stages need
    the whole range), and lets _run_report_job read the stage from Redis.
    Returns -1 if the report does not exist, else the number of units."""
    if not await asyncio.to_thread(_lease_acquire, report_id):
        return -2                              # owned by a live job elsewhere
    org_redis, org_redis_binary = _redis_clients()

    def _prepare():
        org_redis.delete(_stop_key(report_id))   # a launch is intent to run
        meta = {k.decode() if isinstance(k, bytes) else k:
                v.decode() if isinstance(v, bytes) else v
                for k, v in org_redis.hgetall(f"report:{report_id}").items()}
        if not meta:
            return None, None
        items = _expand_probe_units(
            _collect_range_items(org_redis, meta["from_commit"], meta["to_commit"]))
        vals = org_redis.hmget(f"report:{report_id}:probes",
                               [i["probe_id"] for i in items])
        pipe = org_redis.pipeline(transaction=False)
        for it, raw in zip(items, vals):
            if not raw:
                continue
            rec = json.loads(raw)
            if rec.get("verdict") == "ERROR":
                rec.update({"verdict": "PENDING", "answer": "", "error": ""})
                pipe.hset(f"report:{report_id}:probes", it["probe_id"], json.dumps(rec))
                pipe.hset(f"report:{report_id}:vmap", it["probe_id"], "PENDING")
        pipe.hset(f"report:{report_id}", mapping={
            "status": "running",
            "last_progress_at": datetime.utcnow().isoformat()})
        pipe.execute()
        return meta, items

    meta, items = await asyncio.to_thread(_prepare)
    if meta is None:
        _track_running(report_id, False)
        _lease_release(report_id)
        return -1
    if not items:
        await asyncio.to_thread(_finalize_report, org_redis, report_id)
        _track_running(report_id, False)
        _lease_release(report_id)
        return 0

    _report_cancel_events.pop(report_id, None)        # fresh event for this run
    target = _llm_target()
    as_of = await asyncio.to_thread(
        _resolve_window, org_redis, meta["from_commit"], meta["to_commit"])
    # One flow for every report: the narrow evidence gathering (Jev), then
    # the LLM judges every changed skill.
    task = asyncio.create_task(_run_report_job(
        report_id, items, target, org_redis, org_redis_binary, as_of=as_of))
    _report_tasks.add(task)
    _track_running(report_id, True)
    task.add_done_callback(_report_tasks.discard)
    task.add_done_callback(lambda _t, rid=report_id: _track_running(rid, False))
    task.add_done_callback(lambda _t, rid=report_id: _lease_release(rid))
    return len(items)


@app.on_event("startup")
async def _autoresume_reports():
    """A redeploy kills in-flight report tasks. Their state (stage + every
    probe verdict) is in Redis, so pick each one up where it stopped."""
    try:
        members = _redis_text.smembers("reports_running") or set()
    except Exception as e:
        print(f"⚠️  autoresume: database unavailable: {_scrub(str(e))}")
        return
    for rid in list(members):
        rid = rid.decode() if isinstance(rid, bytes) else rid
        if "|" in rid:                      # entry from the old cloud format
            _redis_text.srem("reports_running", rid)
            rid = rid.rpartition("|")[2]
        try:
            n = await _launch_report_job(rid)
            if n == -2:
                print(f"⏭  report {rid} still owned by another instance — skipping")
            else:
                print(f"🔁 autoresume report {rid}: {n} unit(s)")
        except Exception as e:
            print(f"⚠️  autoresume {rid} failed: {_scrub(str(e))}")

@app.post("/api/timeline/report")
async def timeline_report(req: TimelineReportRequest):
    """Create the report record, launch probes detached, return immediately.
    Client polls GET /api/timeline/reports/{report_id} for progress."""
    org_redis, org_redis_binary = _redis_clients()
    try:
        _llm_target()                      # fail now if the key is missing
    except (MissingSecret, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        items = await asyncio.to_thread(
            _collect_range_items, org_redis, req.from_commit, req.to_commit,
        )
        items = _expand_probe_units(items)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if not os.environ.get("OPENROUTER_API_KEY"):
        raise HTTPException(status_code=400,
                            detail="Reports need OPENROUTER_API_KEY on the server "
                                   "(Jev gathers the evidence).")
    report_id = secrets.token_hex(8)
    await asyncio.to_thread(
        _persist_report_plan, org_redis, report_id,
        req.from_commit, req.to_commit, items,
    )
    await _launch_report_job(report_id)
    return {"report_id": report_id, "total": len(items)}

@app.post("/api/timeline/reports/{report_id}/stop")
async def stop_report(report_id: str):
    if _lease_held(report_id):
        # Owner may be this process or another instance: the flag reaches both
        # (the job's lease keeper polls it); the local event just makes it faster.
        _redis_text.set(_stop_key(report_id), "1", ex=3600)
        ev = _report_cancel_events.get(report_id)
        if ev:
            ev.set()
        return {"success": True}
    # No owner: Redis says running, but the job died. Mark it interrupted now.
    org_redis, _ = _redis_clients()

    def _orphan_stop():
        status = org_redis.hget(f"report:{report_id}", "status")
        status = status.decode() if isinstance(status, bytes) else status
        if status is None:
            return "Report not found or expired"
        if status != "running":
            return f"Report is not running (status: {status})"
        org_redis.hset(f"report:{report_id}", "status", "interrupted")
        return ""

    err = await asyncio.to_thread(_orphan_stop)
    if err:
        raise HTTPException(400, err)
    return {"success": True, "orphaned": True}

@app.post("/api/timeline/reports/{report_id}/resume")
async def resume_report(report_id: str):
    try:
        n = await _launch_report_job(report_id)
    except (MissingSecret, ValueError) as e:
        raise HTTPException(400, str(e))
    if n == -2:
        raise HTTPException(409, "Report is already running")
    if n < 0:
        raise HTTPException(404, "Report not found or expired")
    return {"success": True, "resumed": n}


@app.delete("/api/timeline/reports/{report_id}")
async def delete_report(report_id: str):
    """Delete a report and all its keys. A running report is cancelled first
    and given a moment to stop; deletion proceeds regardless — the job's
    writes after deletion recreate nothing visible (vmap/probes keys are
    written with hset on a deleted hash, then expire is never renewed, and
    the report is gone from reports_index so no listing resolves it)."""
    org_redis, _ = _redis_clients()
    meta_k, order_k, probes_k = _report_keys(report_id)

    exists = await asyncio.to_thread(org_redis.exists, meta_k)
    if not exists:
        # Still purge a dangling index entry so ghosts don't linger in the list
        await asyncio.to_thread(org_redis.zrem, "reports_index", report_id)
        raise HTTPException(status_code=404, detail="Report not found or expired")

    # Running in this process → signal cancel and give the job a beat to
    # observe it (the fan-out checks the event every 2s).
    if _lease_held(report_id):
        _redis_text.set(_stop_key(report_id), "1", ex=3600)
        ev = _report_cancel_events.get(report_id)
        if ev:
            ev.set()
        await asyncio.sleep(6)          # keeper polls every 5 s
        _redis_text.delete(_lease_key(report_id))

    def _purge():
        pipe = org_redis.pipeline(transaction=False)
        pipe.delete(*_report_all_keys(report_id))
        pipe.zrem("reports_index", report_id)
        pipe.execute()

    await asyncio.to_thread(_purge)
    _report_cancel_events.pop(report_id, None)
    return {"success": True, "deleted": report_id}


@app.get("/api/timeline/reports")
async def list_reports(limit: int = 20):
    org_redis, _ = _redis_clients()
    limit = min(max(1, limit), 50)

    def _fetch():
        # Reports made before expiry was removed still carry a time limit.
        # Lift it once, for every report in the index.
        every = [r.decode() if isinstance(r, bytes) else r
                 for r in org_redis.zrange("reports_index", 0, -1)]
        pipe = org_redis.pipeline(transaction=False)
        for rid in every:
            pipe.ttl(f"report:{rid}")
        timed = [rid for rid, t in zip(every, pipe.execute()) if t and t > 0]
        if timed:
            pipe = org_redis.pipeline(transaction=False)
            for rid in timed:
                for k in _report_all_keys(rid):
                    pipe.persist(k)
            pipe.execute()

        rids = [r.decode() if isinstance(r, bytes) else r
                for r in org_redis.zrevrange("reports_index", 0, limit - 1)]
        if not rids:
            return []
        pipe = org_redis.pipeline(transaction=False)
        for rid in rids:
            pipe.hgetall(f"report:{rid}")
        out = []
        for rid, meta in zip(rids, pipe.execute()):
            if not meta:
                org_redis.zrem("reports_index", rid)
                continue
            m = {(k.decode() if isinstance(k, bytes) else k):
                 (v.decode() if isinstance(v, bytes) else v)
                 for k, v in meta.items()}
            out.append(_mark_if_interrupted(org_redis, m))
        return out

    return {"reports": await asyncio.to_thread(_fetch)}


@app.get("/api/timeline/reports/{report_id}")
async def get_report(report_id: str, page: int = 1, page_size: int = 10,
                     verdict: str = "", commit: str = ""):
    org_redis, _ = _redis_clients()
    page = max(1, page)
    page_size = min(max(1, page_size), 30)
    _ALLOWED = {"PENDING", "BENIGN", "FLAGRANTLY_MALICIOUS", "SUSPICIOUS",
                "MAJOR_FLAW", "MINOR_FLAW", "FLAW",
                "DORMANT", "UNCLEAR", "INDEX_MISMATCH", "ERROR"}
    wanted = {v.strip().upper() for v in verdict.split(",") if v.strip()} & _ALLOWED
    commit_prefixes = [c.lower() for c in re.split(r"[\s,]+", commit.strip()) if c]

    def _fetch():
        meta = org_redis.hgetall(f"report:{report_id}")
        if not meta:
            return None
        meta = {(k.decode() if isinstance(k, bytes) else k):
                (v.decode() if isinstance(v, bytes) else v) for k, v in meta.items()}
        meta = _mark_if_interrupted(org_redis, meta)
        total = int(meta.get("total", 0))
        start = (page - 1) * page_size

        order = [s.decode() if isinstance(s, bytes) else s
                 for s in org_redis.lrange(f"report:{report_id}:order", 0, -1)]

        # ── cmap: skill_id → full commit hash (backfilled for old reports) ──
        cmap_raw = {(k.decode() if isinstance(k, bytes) else k):
                    (v.decode() if isinstance(v, bytes) else v)
                    for k, v in org_redis.hgetall(f"report:{report_id}:cmap").items()}
        cmap = {s: [c for c in v.split(",") if c] for s, v in cmap_raw.items()}
        if len(cmap) < len(order):
            missing = [s for s in order if s not in cmap]
            vals = org_redis.hmget(f"report:{report_id}:probes", missing)
            all_hashes = [h.decode() if isinstance(h, bytes) else h
                          for h in org_redis.zrange("commit_order", 0, -1)]
            by_prefix = {h[:12]: h for h in all_hashes}
            writes = {}
            for s, v in zip(missing, vals):
                try:
                    c = json.loads(v).get("commit", "") if v else ""
                except (json.JSONDecodeError, TypeError):
                    c = ""
                full = by_prefix.get(c, c)   # old probes store the anchor prefix only
                cmap[s] = [full] if full else []
                if full:
                    writes[s] = full         # single-touch degradation for old reports
            if writes:
                pipe = org_redis.pipeline(transaction=False)
                pipe.hset(f"report:{report_id}:cmap", mapping=writes)
                pipe.execute()

        # ── per-commit summary, first-appearance order ──
        # Dropdown covers every TOUCHING commit; grouping stays on the anchor
        # (first touch) so each probe renders exactly once.
        commit_seq, counts = [], {}
        for s in order:
            for c in cmap.get(s, []):
                if c not in counts:
                    counts[c] = 0
                    commit_seq.append(c)
                counts[c] += 1          # count = probes touched by this commit
        goals = {}
        if commit_seq:
            pipe = org_redis.pipeline(transaction=False)
            for c in commit_seq:
                pipe.get(f"commit_meta:{c}")
            for c, m in zip(commit_seq, pipe.execute()):
                g = ""
                if m:
                    try:
                        g = json.loads(m).get("goal", "")
                    except (json.JSONDecodeError, TypeError):
                        pass
                goals[c] = g
        # ── filters: commit prefix, then verdicts ──
        vmap = {(k.decode() if isinstance(k, bytes) else k):
                (v.decode() if isinstance(v, bytes) else v)
                for k, v in org_redis.hgetall(f"report:{report_id}:vmap").items()}

        # ── findings ledger: unverified cross-slice claims per target ──
        fin_by_target: dict[str, list] = {}
        for fk, fv in (org_redis.hgetall(f"report:{report_id}:findings")
                       or {}).items():
            fk = fk.decode() if isinstance(fk, bytes) else fk
            fv = fv.decode() if isinstance(fv, bytes) else fv
            try:
                fin_by_target.setdefault(
                    fk.split("|", 1)[0], []).append(json.loads(fv))
            except (json.JSONDecodeError, TypeError):
                continue

        worst_by_commit: dict[str, str] = {}
        contested_commits: set[str] = set()
        for s in order:
            v = vmap.get(s, "PENDING")
            for c in cmap.get(s, []):
                if _SEV_RANK.get(v, 0) > _SEV_RANK.get(
                        worst_by_commit.get(c, "BENIGN"), 0):
                    worst_by_commit[c] = v
        commits_out = [{"commit": c[:12], "count": counts[c],
                        "worst": worst_by_commit.get(c, "PENDING"),
                        "goal": (goals.get(c) or "")[:80]} for c in commit_seq]

        keep = order
        if commit_prefixes:
            keep = [s for s in keep
                    if any(c.lower().startswith(p)
                           for c in cmap.get(s, [])
                           for p in commit_prefixes)]

        # Verdict tallies for the (commit-filtered) set — drives the filter-row
        # counts in the UI. One dict pass; vmap is one HGETALL.
        verdict_counts: dict[str, int] = {}
        for s in keep:
            vd = vmap.get(s, "PENDING")
            verdict_counts[vd] = verdict_counts.get(vd, 0) + 1

        if wanted:
            keep = [s for s in keep if vmap.get(s, "PENDING") in wanted]

        filtered = bool(commit_prefixes) or bool(wanted)
        filtered_total = len(keep) if filtered else None
        sids = keep[start:start + page_size]
        pages = max(1, ((filtered_total if filtered else total)
                        + page_size - 1) // page_size)

        probes = []
        if sids:
            vals = org_redis.hmget(f"report:{report_id}:probes", sids)
            for s, v in zip(sids, vals):
                if not v:
                    continue
                rec = json.loads(v)
                touch = cmap.get(s, [])
                rec.setdefault("commit", touch[0][:12] if touch else "")
                rec.setdefault("commits", [c[:12] for c in touch])
                floc = (rec.get("loc") or "").rsplit(":", 1)[0]
                fl = []
                for c12 in rec["commits"]:
                    fl += fin_by_target.get(f"{floc}@{c12}", [])
                fl = [f for f in fl if f.get("by") != s]
                if fl:
                    rec["findings_in"] = fl
                    own = _SEV_RANK.get(rec.get("verdict", ""), 0)
                    rec["contested"] = any(
                        _SEV_RANK.get(f.get("severity", ""), 0) > own
                        for f in fl)
                probes.append(rec)
        conflicts = {}
        for ck, cv in (org_redis.hgetall(f"report:{report_id}:conflicts")
                       or {}).items():
            ck = ck.decode() if isinstance(ck, bytes) else ck
            cv = cv.decode() if isinstance(cv, bytes) else cv
            try:
                conflicts[ck[:12]] = json.loads(cv)
            except (json.JSONDecodeError, TypeError):
                continue
        out = {"meta": meta, "probes": probes, "page": page,
               "page_size": page_size, "pages": pages,
               "commits": commits_out,
               "verdict_counts": verdict_counts,
               "conflicts": conflicts}
        if filtered_total is not None:
            out["filtered_total"] = filtered_total
        return out

    result = await asyncio.to_thread(_fetch)
    if result is None:
        raise HTTPException(status_code=404, detail="Report not found or expired")
    return result

async def _rerun_single_probe(report_id, item, target, org_redis,
                              org_redis_binary,
                              restore_status: str,
                              as_of: Optional[dict] = None):
    token_stats = {"input": 0, "output": 0}
    start = time.time()
    err_flag = False
    try:
        unit_as_of = as_of
        if as_of is not None:
            def _unit_window(it=item):
                touches = it.get("touches") or [{"commit": it["commit"]}]
                ranks = [org_redis.zrank("commit_order", t["commit"])
                         for t in touches]
                ranks = [int(r) for r in ranks if r is not None]
                if not ranks:
                    return as_of, it
                top = max(ranks)
                w = {"from_rank": as_of["from_rank"], "to_rank": top}
                sk = skills_lib.get_skill_as_of(
                    org_redis, it["skill_id"], top)
                if sk:
                    it = {**it, "description":
                          sk.get("description_of_skill", it["description"])}
                return w, it
            unit_as_of, item = await asyncio.to_thread(_unit_window)
        diffs = await asyncio.to_thread(_touch_diffs, org_redis, item)
        mdelta = await asyncio.to_thread(
            _composite_member_delta, org_redis, item)
        cons = await asyncio.to_thread(
            _blob_consumption, org_redis, item, unit_as_of)
        leads = await asyncio.to_thread(
            _leads_for, org_redis, report_id, item, item["probe_id"])
        q = _build_probe_question(item, diffs, mdelta, cons, leads)
        ctx = await asyncio.to_thread(
            _probe_context, org_redis, org_redis_binary, q, item,
            unit_as_of)
        ev_rec: dict = {}
        try:
            text, verdict, err, findings = await asyncio.wait_for(
                _run_probe_fast(q, ctx, item, diffs, target, org_redis,
                                org_redis_binary, token_stats,
                                as_of=unit_as_of, record=ev_rec),
                timeout=int(os.environ.get("PROBE_TIMEOUT_SECONDS", "1500")),
            )
        except asyncio.TimeoutError:
            text, verdict, err, findings = \
                "", "ERROR", "probe re-run timed out", []
        ev_rec.update({"probe_id": item["probe_id"],
                       "run_verdict": verdict, "error": err or "",
                       "ts": int(time.time()), "jev_model": JEV_MODEL})
        try:
            await asyncio.to_thread(
                org_redis.hset, f"report:{report_id}:evidence",
                item["probe_id"], json.dumps(ev_rec))
        except Exception as e:
            print(f"⚠️  evidence record not stored for "
                  f"{item['probe_id']}: {_scrub(str(e))}")
        made_change = (any(d.get("diff") for d in diffs)
                       or any((d.get("status") or "").startswith(
                              "first stored version") for d in diffs))
        if (len(item.get("touches") or []) == 1
                and not made_change
                and verdict in ("FLAGRANTLY_MALICIOUS", "SUSPICIOUS")):
            text += ("\n\n[SYSTEM: verdict clamped to UNCLEAR — this "
                     "commit stored no body change for this skill; "
                     "malicious state visible in the body belongs to "
                     "the commit that introduced it.]")
            verdict = "UNCLEAR"
        err_flag = verdict == "ERROR"
        await asyncio.to_thread(
            _persist_probe_result, org_redis, report_id,
            item["probe_id"], verdict, text, err, findings, target.model,
        )
    except Exception as e:
        err_flag = True
        print(f"❌ _rerun_single_probe crash: {_scrub(str(e))}")
        await asyncio.to_thread(
            _persist_probe_result, org_redis, report_id,
            item["probe_id"], "ERROR", "", _scrub(str(e))[:200],
        )
    finally:
        # Settle status from the vmap: done / error when nothing is open,
        # otherwise back to what it was. Never stamps done over open probes.
        def _settle():
            m = _derive_meta(org_redis, {"report_id": report_id})
            if int(m["pending"]) > 0:
                final = restore_status if restore_status != "running" else "interrupted"
            elif int(m["errors"]) > 0:
                final = "error"
            else:
                final = "done"
            org_redis.hset(f"report:{report_id}", mapping={
                "status": final, "last_progress_at": datetime.utcnow().isoformat()})
        await asyncio.to_thread(_settle)
        _lease_release(report_id)
        print(f"⏱  probe re-run done in {time.time() - start:.0f}s, "
              f"tokens in={token_stats['input']} out={token_stats['output']}"
              f"{' (error)' if err_flag else ''}")


@app.get("/api/timeline/reports/{report_id}/probes/{skill_id}/evidence")
async def get_probe_evidence(report_id: str, skill_id: str):
    """What the probe's last run read. None when the probe has not run yet."""
    org_redis, _ = _redis_clients()
    raw = await asyncio.to_thread(
        org_redis.hget, f"report:{report_id}:evidence", skill_id)
    if isinstance(raw, bytes):
        raw = raw.decode()
    try:
        return {"evidence": json.loads(raw) if raw else None}
    except (json.JSONDecodeError, TypeError):
        return {"evidence": None}


@app.post("/api/timeline/reports/{report_id}/probes/{skill_id}/rerun")
async def rerun_probe(report_id: str, skill_id: str):
    org_redis, org_redis_binary = _redis_clients()
    meta_k, _, probes_k = _report_keys(report_id)

    def _prepare():
        meta = org_redis.hgetall(meta_k)
        if not meta:
            return None, None, "Report not found or expired"
        meta = {(k.decode() if isinstance(k, bytes) else k):
                (v.decode() if isinstance(v, bytes) else v)
                for k, v in meta.items()}
        raw = org_redis.hget(probes_k, skill_id)
        if not raw:
            return None, None, "Probe not found in this report"
        prev = json.loads(raw)
        if prev.get("verdict") == "PENDING":
            return None, None, "Probe is already running"
        # Rebuild the item from the range (goal/edges/desc may need refetch)
        items = _expand_probe_units(
            _collect_range_items(org_redis, meta["from_commit"], meta["to_commit"]))
        item = next((i for i in items if i["probe_id"] == skill_id), None)
        if item is None:
            return None, None, "Skill no longer resolvable in this range"
        pipe = org_redis.pipeline(transaction=False)
        prev["verdict"], prev["answer"], prev["error"] = "PENDING", "", ""
        pipe.hset(probes_k, skill_id, json.dumps(prev))
        pipe.hset(f"report:{report_id}:vmap", skill_id, "PENDING")
        pipe.hset(meta_k, mapping={
            "status": "running",
            "last_progress_at": datetime.utcnow().isoformat(),
        })
        pipe.execute()
        return meta, item, ""

    if not await asyncio.to_thread(_lease_acquire, report_id):
        raise HTTPException(409, "Report is running — wait for it to finish before re-running a probe")
    meta, item, err = await asyncio.to_thread(_prepare)
    if err:
        _lease_release(report_id)
        raise HTTPException(status_code=400 if "running" in err else 404, detail=err)

    try:
        target = _llm_target()
    except (MissingSecret, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    as_of = await asyncio.to_thread(
        _resolve_window, org_redis, meta["from_commit"], meta["to_commit"])
    task = asyncio.create_task(_rerun_single_probe(
        report_id, item, target, org_redis, org_redis_binary,
        restore_status=meta.get("status", "done"),
        as_of=as_of,
    ))
    _report_tasks.add(task)
    _track_running(report_id, True)
    task.add_done_callback(_report_tasks.discard)
    task.add_done_callback(lambda _t, rid=report_id: _track_running(rid, False))
    return {"success": True, "skill_id": skill_id}

























@app.get("/api/ingest/status")
async def ingest_status():
    """Progress of the local ingestion (`python next_claude.py …`) and of
    the embedding pass, as the two write them to Redis."""
    r = _redis_text
    def _read():
        ing = r.hgetall("ingest_run") or {}
        # A run that stopped writing (Ctrl+C, crash) leaves status=running;
        # the alive keys expire, and the page shows it as interrupted.
        ing["alive"] = bool(r.exists("ingest_run_alive"))
        emb = {}
        for key in r.scan_iter("embed_run:*", count=100):
            if key.startswith("embed_run_alive:"):
                continue
            name = key.split(":", 1)[1]
            emb[name] = r.hgetall(key) or {}
            emb[name]["alive"] = bool(r.exists(f"embed_run_alive:{name}"))
        return {"ingest": ing, "embed": emb}
    return await asyncio.to_thread(_read)


# ── Retrieval API (used by unified_brain_mcp.py for Cursor / Claude Code) ────
# Every row carries coordinates: file, symbol, line (1-based, as ingested),
# struct, def_key. Bodies are returned whole; nothing is summarised.

class RetrieveRequest(BaseModel):
    question: str
    from_commit: str = ""     # optional window: both set → evidence as of to_commit
    to_commit: str = ""


# One retrieval at a time: a second call waits for the first instead of
# running its Jev threads beside it (two at once doubled the open sockets
# and made DNS fail on macOS). Nothing is dropped; it queues.
_RETRIEVE_LOCK = asyncio.Lock()


def _coords(def_key: str) -> dict:
    p = skills_lib.parse_def_key(def_key or "")
    if not p:
        return {"def_key": def_key, "file": "", "symbol": "", "line": 0, "struct": ""}
    return {"def_key": def_key, "file": p[0], "symbol": p[1], "line": p[2], "struct": p[3]}


def _evidence_row(s: dict) -> dict:
    row = _coords(s.get("def_key") or "")
    if not row["file"]:
        row["file"], row["symbol"] = s.get("file_path", ""), s.get("symbol", "")
    row.update({
        "skill_id": s.get("skill_id", ""),
        "score": s.get("score"),
        "how": ("chain: " + " → ".join(s["trail"])) if s.get("trail") else "scored by Jev",
        "is_obsolete": bool(s.get("is_obsolete")),
        "reconstructed": bool(s.get("reconstructed")),
        "guard": s.get("guard") or "",
        "code": s.get("code") or "",
    })
    return row


def _snippet(body: str, pattern: str, is_regex: bool, first_line: int, around: int = 2) -> dict:
    lines = body.splitlines()
    rx = re.compile(pattern if is_regex else re.escape(pattern))
    for i, ln in enumerate(lines):
        if rx.search(ln):
            lo, hi = max(0, i - around), min(len(lines), i + around + 1)
            return {"hit_line": first_line + i,
                    "snippet": "\n".join(f"{first_line + j}: {lines[j]}" for j in range(lo, hi))}
    return {"hit_line": None, "snippet": ""}


@app.post("/api/retrieve")
async def api_retrieve(req: RetrieveRequest):
    """The question page's retrieval without the answer: embeddings →
    Jev scoring → Jev chains. Returns the evidence bodies with coordinates."""
    if not req.question.strip():
        raise HTTPException(400, "question is empty")
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise HTTPException(400, "OPENROUTER_API_KEY is not set (Jev gathers the evidence)")
    org_redis, org_redis_binary = _redis_clients()
    as_of, window = None, ""
    if req.from_commit and req.to_commit:
        as_of = await asyncio.to_thread(_resolve_window, org_redis, req.from_commit, req.to_commit)
        window = (f"{req.from_commit[:12]}..{req.to_commit[:12]}" if as_of
                  else "requested commits are not in the index — current state used")
    try:
        target = _llm_target()
    except Exception:
        target = None                    # only CHAIN_JUDGE=llm needs it
    log, result = [], None
    t0 = time.time()
    async with _RETRIEVE_LOCK:
        async for kind, payload in _gather_evidence(req.question, org_redis,
                                                    org_redis_binary, as_of, target):
            if kind == "status":
                log.append(payload)
            elif kind == "error":
                raise HTTPException(502, payload)
            else:
                result = payload
    chars = sum(len(s.get("code") or "") for s in result["skills"])
    print(f"📦 retrieve: {len(result['skills'])} bodies, {chars} chars "
          f"(~{chars // 4} tokens) handed over in {time.time() - t0:.1f}s")
    return {
        "question": req.question,
        "window": window,
        "evidence": [_evidence_row(s) for s in result["skills"]],
        "leads": [{"file": l["file"], "symbol": l["symbol"], "trail": l["trail"]}
                  for l in result["leads"]],
        "log": log,
        "info": result["info"],
    }


@app.get("/api/grep")
async def api_grep(pattern: str, file: str = "", regex: bool = False,
                   max_results: int = 50, include_hist: bool = False,
                   from_commit: str = "", to_commit: str = ""):
    """Exact substring (or regex) search over every stored body."""
    if not pattern:
        raise HTTPException(400, "pattern is empty")
    org_redis, _ = _redis_clients()
    as_of = None
    if from_commit and to_commit:
        as_of = await asyncio.to_thread(_resolve_window, org_redis, from_commit, to_commit)

    def _run():
        res = skills_lib.grep_code_ft(
            org_redis, pattern=pattern, is_regex=regex, file=file or None,
            struct_types=None, max_results=max_results, exact_total=True,
            include_hist=include_hist, as_of=as_of) or {"rows": [], "total_matched": 0}
        rows = []
        for r in res["rows"]:
            row = _coords(r.get("def_key") or "")
            row.update(_snippet(r.get("body") or "", pattern, regex, row["line"] or 1))
            if r.get("as_of_commit"):
                row["as_of_commit"] = r["as_of_commit"]
            if r.get("post_range_body"):
                row["post_range_body"] = True
            rows.append(row)
        return {"pattern": pattern, "total_matched": res.get("total_matched", len(rows)),
                "rows": rows}
    return await asyncio.to_thread(_run)


@app.get("/api/symbol/{name}")
async def api_symbol(name: str):
    """Where a name is defined, who calls it, who takes its address."""
    org_redis, _ = _redis_clients()

    def _run():
        defs = []
        for key in sorted(org_redis.smembers(f"symbol_name:{name}") or []):
            p = skills_lib.parse_symbol_key(key)
            if not p:
                continue
            dk = key[len("symbol:"):]
            ids = org_redis.lrange(f"symbol:{dk}", 0, -1)
            defs.append({**_coords(dk), "skill_id": ids[-1] if ids else "",
                         "has_body": bool(org_redis.exists(f"code:{dk}"))})
        callers = [_coords(dk) for dk in sorted(org_redis.smembers(f"called_by:{name}") or [])]
        refs = [{**_coords(r["def_key"]), "kind": r["kind"], "ref_line": r["line"],
                 "snippet": r["snippet"]} for r in skills_lib.find_referrers(org_redis, name)]
        return {"name": name, "definitions": defs, "callers": callers, "referrers": refs}
    return await asyncio.to_thread(_run)


@app.get("/api/body")
async def api_body(def_key: str, commit: str = ""):
    """One body, now or as of a commit."""
    org_redis, _ = _redis_clients()

    def _run():
        code = (skills_lib.get_code_as_of(org_redis, def_key, commit) if commit
                else skills_lib.get_code(org_redis, def_key))
        return {**_coords(def_key), "commit": commit, "code": code or "",
                "found": bool(code)}
    return await asyncio.to_thread(_run)


@app.get("/api/history")
async def api_history(def_key: str):
    """The versions of a position: which commits changed it."""
    org_redis, _ = _redis_clients()

    def _run():
        ids = org_redis.lrange(f"symbol:{def_key}", 0, -1)
        out = []
        for sid in ids:
            raw = org_redis.get(f"skill:{sid}")
            sk = json.loads(raw) if raw else {}
            versions = []
            for e in org_redis.lrange(f"skill_history:{sid}", 0, -1):
                try:
                    d = json.loads(e)
                except (TypeError, ValueError):
                    continue
                versions.append({"commit": d.get("commit_hash", ""), "def_key": d.get("def_key", "")})
            out.append({"skill_id": sid, "current_commit": sk.get("commit_hash", ""),
                        "created_commit": sk.get("created_commit", ""),
                        "is_obsolete": bool(sk.get("isObsolete")), "versions": versions})
        return {**_coords(def_key), "skills": out}
    return await asyncio.to_thread(_run)


@app.get("/api/commit/{commit}")
async def api_commit(commit: str):
    """What one commit did to the skills: new, updated, obsoleted."""
    org_redis, _ = _redis_clients()

    def _run():
        full = commit
        if org_redis.zscore("commit_order", commit) is None:      # prefix given
            full = next((h for h in org_redis.zrange("commit_order", 0, -1)
                         if h.startswith(commit)), "")
            if not full:
                raise HTTPException(404, "commit not in the index")
        raw = org_redis.get(f"commit_meta:{full}")
        meta = json.loads(raw) if raw else {}
        out = {"commit": full, "seq": int(org_redis.zscore("commit_order", full) or 0),
               "goal": meta.get("goal", ""), "author": meta.get("author", ""),
               "author_date": meta.get("author_date", ""), "files": meta.get("files", [])}
        for ev in ("new", "updated", "obsoleted"):
            rows = []
            for sid in sorted(org_redis.smembers(f"commit_skills:{full}:{ev}") or []):
                r = org_redis.get(f"skill:{sid}")
                sk = json.loads(r) if r else {}
                rows.append({"skill_id": sid, **_coords(sk.get("def_key", ""))})
            out[ev] = rows
        return out
    return await asyncio.to_thread(_run)


@app.get("/health")
def health():
    return {"status": "ok", "db": DB_PATH}











 



@app.post("/ask/stream")
async def ask_stream(req: AskRequest):
    """Streaming variant of /ask. Returns Server-Sent Events."""
    return StreamingResponse(
        _ask_internal_stream(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control":      "no-cache",
            "X-Accel-Buffering":  "no",  # prevents nginx buffering
        },
    )



# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("codebase_qa_service:app", host="127.0.0.1",
                port=int(os.getenv("PORT", "8000")),
                timeout_graceful_shutdown=2)
    os._exit(0)   # don't wait for worker threads stuck in an LLM call
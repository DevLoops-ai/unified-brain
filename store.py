"""
store.py — the one-file database of unified-brain (SQLite).

One file per repository. It offers the same calls the code used to make on
Redis (get/set, hashes, sets, sorted sets, lists, pipelines), so the rest
of the code reads and writes exactly the records it always did, plus two
things Redis did with modules:

  * grep over stored bodies — an FTS5 trigram index over every body field
    of code:, code_hist: and code_at: records (exact substring search).
  * nearest-vector search over the code-vector rows (cvec_at:…) — a
    sqlite-vec table per store, exact cosine distance, filtered by commit
    rank, latest and obsolete flags.

    db = store.open("/repo/.unified-brain.db")        # text view (str in, str out)
    rb = db.binary()                                   # bytes view, same file
"""
from __future__ import annotations

import functools
import hashlib
import os
import queue
import sqlite3
import threading
import time
from typing import Iterable, Optional

try:
    import sqlite_vec
    SQLITE_VEC_AVAILABLE = True
except ImportError:                       # vectors then fall back to numpy
    sqlite_vec = None
    SQLITE_VEC_AVAILABLE = False

DB_FILE_NAME = ".unified-brain.db"

# Connections are shared by all threads through a small pool: a thread
# borrows one for the duration of a Store call and returns it. A thread
# that finds none free waits. Without the pool every thread opened its
# own connection (3 files each in WAL mode), and 128 Jev threads hit
# macOS's default limit of 256 open files.
POOL_SIZE = 8

# Keys whose `body` field is indexed for grep.
_BODY_PREFIXES = ("code:", "code_hist:", "code_at:")
# Chunk-vector rows: <prefix>:<skill_id>:<version>:<chunk>. Mean rows
# (<prefix>_mean:…) and version lists (<prefix>_ver:…) are plain records.
_VEC_PREFIXES = ("cvec_at", "cvecq_at")

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
CREATE TABLE IF NOT EXISTS kv     (key TEXT PRIMARY KEY, value BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS hashes (key TEXT NOT NULL, field TEXT NOT NULL, value BLOB NOT NULL,
                                   PRIMARY KEY (key, field));
CREATE TABLE IF NOT EXISTS sets   (key TEXT NOT NULL, member BLOB NOT NULL, PRIMARY KEY (key, member));
CREATE TABLE IF NOT EXISTS zsets  (key TEXT NOT NULL, member BLOB NOT NULL, score REAL NOT NULL,
                                   PRIMARY KEY (key, member));
CREATE INDEX IF NOT EXISTS zsets_score ON zsets (key, score, member);
CREATE TABLE IF NOT EXISTS lists  (key TEXT NOT NULL, pos INTEGER NOT NULL, value BLOB NOT NULL,
                                   PRIMARY KEY (key, pos));
CREATE TABLE IF NOT EXISTS expires (key TEXT PRIMARY KEY, at REAL NOT NULL);
-- Bodies are stored once per distinct text (a current body and its newest
-- per-commit copy are the same text); body_keys maps each record to it.
CREATE TABLE IF NOT EXISTS bodies (id INTEGER PRIMARY KEY, sha TEXT UNIQUE NOT NULL, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS body_keys (key TEXT PRIMARY KEY, body_id INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS body_keys_body ON body_keys (body_id);
CREATE VIRTUAL TABLE IF NOT EXISTS bodies_fts USING fts5(
    body, content='bodies', content_rowid='id', tokenize='trigram');
CREATE TRIGGER IF NOT EXISTS bodies_ai AFTER INSERT ON bodies BEGIN
  INSERT INTO bodies_fts(rowid, body) VALUES (new.id, new.body);
END;
CREATE TRIGGER IF NOT EXISTS bodies_ad AFTER DELETE ON bodies BEGIN
  INSERT INTO bodies_fts(bodies_fts, rowid, body) VALUES ('delete', old.id, old.body);
END;
CREATE TABLE IF NOT EXISTS vec_tables (prefix TEXT PRIMARY KEY, dims INTEGER NOT NULL,
                                        tbl TEXT, partitioned INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS vec_rows (key TEXT PRIMARY KEY, prefix TEXT NOT NULL, rowid_in_vec INTEGER NOT NULL);
"""


def _b(v) -> bytes:
    if isinstance(v, bytes):
        return v
    if isinstance(v, bool):
        return b"1" if v else b"0"
    if isinstance(v, (int, float)):
        return str(v).encode()
    return str(v).encode()


def _s(v) -> str:
    return v.decode() if isinstance(v, bytes) else str(v)


def open(path: str, decode_responses: bool = True) -> "Store":
    return Store(path, decode_responses=decode_responses)


def db_path_for_repo(repo_path: str) -> str:
    return os.path.join(os.path.abspath(repo_path), DB_FILE_NAME)


def _borrowed(fn):
    """Runs the method with a pooled connection held in thread-local
    storage; nested Store calls on the same thread reuse it."""
    @functools.wraps(fn)
    def wrapper(self, *a, **kw):
        if getattr(self._local, "conn", None) is not None:
            return fn(self, *a, **kw)
        c = self._take()
        self._local.conn = c
        try:
            return fn(self, *a, **kw)
        finally:
            self._local.conn = None
            self._pool.put(c)
    return wrapper


class Store:
    """One SQLite file; `decode_responses` chooses str or bytes results."""

    def __init__(self, path: str, decode_responses: bool = True):
        self.path = os.path.abspath(path)
        self.decode_responses = decode_responses
        self._local = threading.local()
        self._lock = threading.RLock()
        self._pool: queue.LifoQueue = queue.LifoQueue()
        self._pool_lock = threading.Lock()
        self._state = {"made": 0}           # shared with binary() views
        self._init_schema()

    @_borrowed
    def _init_schema(self) -> None:
        c = self._conn()
        c.executescript(_SCHEMA)
        cols = {r[1] for r in c.execute("PRAGMA table_info(vec_tables)")}
        if "tbl" not in cols:
            # files from before the partitioned layout: the table was vec_<prefix>
            c.execute("ALTER TABLE vec_tables ADD COLUMN tbl TEXT")
            c.execute("ALTER TABLE vec_tables ADD COLUMN partitioned INTEGER NOT NULL DEFAULT 0")
            c.execute("UPDATE vec_tables SET tbl = 'vec_' || prefix WHERE tbl IS NULL")

    # ── connections ─────────────────────────────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, timeout=60, isolation_level=None,
                            check_same_thread=False)
        c.execute("PRAGMA busy_timeout=60000")
        if SQLITE_VEC_AVAILABLE:
            c.enable_load_extension(True)
            sqlite_vec.load(c)
            c.enable_load_extension(False)
        return c

    def _take(self) -> sqlite3.Connection:
        try:
            return self._pool.get_nowait()
        except queue.Empty:
            pass
        with self._pool_lock:
            if self._state["made"] < POOL_SIZE:
                self._state["made"] += 1
                return self._connect()
        return self._pool.get()

    def _conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            raise RuntimeError("Store call outside a borrowed connection")
        return c

    def binary(self) -> "Store":
        """The same file, bytes results; shares the connection pool."""
        s = Store.__new__(Store)
        s.path, s.decode_responses = self.path, False
        s._local, s._lock = self._local, self._lock
        s._pool, s._pool_lock, s._state = self._pool, self._pool_lock, self._state
        return s

    def _out(self, v):
        if v is None:
            return None
        if isinstance(v, memoryview):
            v = bytes(v)
        if self.decode_responses and isinstance(v, bytes):
            try:
                return v.decode()
            except UnicodeDecodeError:
                return v
        return v

    def _outk(self, v):            # hash field names and keys: always str
        return v.decode() if isinstance(v, bytes) else v

    def ping(self) -> bool:
        self._conn().execute("SELECT 1")
        return True

    def close(self) -> None:
        while True:
            try:
                self._pool.get_nowait().close()
                self._state["made"] -= 1
            except queue.Empty:
                break

    # ── expiry ──────────────────────────────────────────────────────────
    def _alive(self, key: str) -> bool:
        c = self._conn()
        row = c.execute("SELECT at FROM expires WHERE key=?", (key,)).fetchone()
        if row and row[0] <= time.time():
            self._delete_key(c, key)
            return False
        return True

    def expire(self, key: str, seconds: int) -> bool:
        if not self.exists(key):
            return False
        self._conn().execute("INSERT OR REPLACE INTO expires(key, at) VALUES (?, ?)",
                             (key, time.time() + int(seconds)))
        return True

    def ttl(self, key: str) -> int:
        if not self.exists(key):
            return -2
        row = self._conn().execute("SELECT at FROM expires WHERE key=?", (key,)).fetchone()
        return int(row[0] - time.time()) if row else -1

    def persist(self, key: str) -> bool:
        return self._conn().execute("DELETE FROM expires WHERE key=?", (key,)).rowcount > 0

    # ── keys ────────────────────────────────────────────────────────────
    def _delete_key(self, c: sqlite3.Connection, key: str) -> int:
        n = 0
        for t in ("kv", "hashes", "sets", "zsets", "lists", "expires"):
            n += c.execute(f"DELETE FROM {t} WHERE key=?", (key,)).rowcount
        self._body_drop(c, key)
        self._vec_delete(c, key)
        return 1 if n else 0

    def delete(self, *keys: str) -> int:
        c = self._conn()
        return sum(self._delete_key(c, k) for k in keys)

    def exists(self, *keys: str) -> int:
        c = self._conn(); n = 0
        for k in keys:
            if not self._alive(k):
                continue
            for t in ("kv", "hashes", "sets", "zsets", "lists"):
                if c.execute(f"SELECT 1 FROM {t} WHERE key=? LIMIT 1", (k,)).fetchone():
                    n += 1; break
        return n

    def type(self, key: str) -> str:
        c = self._conn()
        if not self._alive(key):
            return "none"
        for t, name in (("kv", "string"), ("hashes", "hash"), ("sets", "set"),
                        ("zsets", "zset"), ("lists", "list")):
            if c.execute(f"SELECT 1 FROM {t} WHERE key=? LIMIT 1", (key,)).fetchone():
                return name
        return "none"

    def scan_iter(self, match: str = "*", count: int = 1000) -> Iterable[str]:
        like = match.replace("%", "\\%").replace("_", "\\_").replace("*", "%").replace("?", "_")
        c = self._conn()
        seen, out = set(), []
        for t in ("kv", "hashes", "sets", "zsets", "lists"):
            for (k,) in c.execute(f"SELECT DISTINCT key FROM {t} WHERE key LIKE ? ESCAPE '\\'", (like,)).fetchall():
                if k not in seen and self._alive(k):
                    seen.add(k); out.append(k)
        return iter(out)

    def rename(self, src: str, dst: str) -> bool:
        c = self._conn()
        if not self.exists(src):
            raise KeyError(f"no such key {src}")
        self._delete_key(c, dst)
        for t in ("kv", "hashes", "sets", "zsets", "lists", "expires", "body_keys"):
            c.execute(f"UPDATE {t} SET key=? WHERE key=?", (dst, src))
        self._vec_rename(c, src, dst)
        return True

    def copy(self, src: str, dst: str, replace: bool = False) -> bool:
        c = self._conn()
        if not self.exists(src):
            return False
        if self.exists(dst):
            if not replace:
                return False
            self._delete_key(c, dst)
        c.execute("INSERT INTO kv SELECT ?, value FROM kv WHERE key=?", (dst, src))
        c.execute("INSERT INTO hashes SELECT ?, field, value FROM hashes WHERE key=?", (dst, src))
        c.execute("INSERT INTO sets SELECT ?, member FROM sets WHERE key=?", (dst, src))
        c.execute("INSERT INTO zsets SELECT ?, member, score FROM zsets WHERE key=?", (dst, src))
        c.execute("INSERT INTO lists SELECT ?, pos, value FROM lists WHERE key=?", (dst, src))
        c.execute("INSERT INTO body_keys SELECT ?, body_id FROM body_keys WHERE key=?", (dst, src))
        self._vec_sync(c, dst)
        return True

    # ── strings ─────────────────────────────────────────────────────────
    def get(self, key: str):
        if not self._alive(key):
            return None
        row = self._conn().execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return self._out(row[0]) if row else None

    def set(self, key: str, value, ex: Optional[int] = None, nx: bool = False) -> Optional[bool]:
        c = self._conn()
        if nx and self.exists(key):
            return None
        c.execute("INSERT OR REPLACE INTO kv(key, value) VALUES (?, ?)", (key, _b(value)))
        c.execute("DELETE FROM expires WHERE key=?", (key,))
        if ex is not None:
            c.execute("INSERT OR REPLACE INTO expires(key, at) VALUES (?, ?)", (key, time.time() + int(ex)))
        return True

    def mget(self, keys: list[str]) -> list:
        return [self.get(k) for k in keys]

    def incr(self, key: str, amount: int = 1) -> int:
        cur = self.get(key)
        n = int(_s(cur) if cur is not None else 0) + amount
        self.set(key, n)
        return n

    # ── hashes ──────────────────────────────────────────────────────────
    def hset(self, key: str, field=None, value=None, mapping: Optional[dict] = None) -> int:
        c = self._conn()
        items = {}
        if field is not None:
            items[self._outk(field)] = value
        if mapping:
            for f, v in mapping.items():
                items[self._outk(f)] = v
        n = 0
        for f, v in items.items():
            cur = c.execute("SELECT 1 FROM hashes WHERE key=? AND field=?", (key, f)).fetchone()
            if f == "body" and key.startswith(_BODY_PREFIXES):
                # The text lives once in `bodies`; the hash keeps a marker.
                c.execute("INSERT OR REPLACE INTO hashes(key, field, value) VALUES (?, ?, ?)", (key, f, b""))
                self._body_put(c, key, _s(v))
            else:
                c.execute("INSERT OR REPLACE INTO hashes(key, field, value) VALUES (?, ?, ?)", (key, f, _b(v)))
            n += 0 if cur else 1
        self._vec_sync(c, key, items)
        return n

    def _body_of(self, c: sqlite3.Connection, key: str) -> Optional[bytes]:
        row = c.execute("SELECT b.body FROM body_keys k JOIN bodies b ON b.id = k.body_id WHERE k.key=?",
                        (key,)).fetchone()
        return row[0].encode() if row else None

    def hget(self, key: str, field):
        if not self._alive(key):
            return None
        c = self._conn()
        f = self._outk(field)
        if f == "body" and key.startswith(_BODY_PREFIXES):
            return self._out(self._body_of(c, key))
        row = c.execute("SELECT value FROM hashes WHERE key=? AND field=?", (key, f)).fetchone()
        return self._out(row[0]) if row else None

    def hmget(self, key: str, fields, *more) -> list:
        if isinstance(fields, (str, bytes)):
            fields = [fields, *more]
        return [self.hget(key, f) for f in fields]

    def hgetall(self, key: str) -> dict:
        if not self._alive(key):
            return {}
        c = self._conn()
        rows = c.execute("SELECT field, value FROM hashes WHERE key=?", (key,)).fetchall()
        out = {}
        for f, v in rows:
            if f == "body" and key.startswith(_BODY_PREFIXES):
                v = self._body_of(c, key) or b""
            out[f if self.decode_responses else f.encode()] = self._out(v)
        return out

    def hvals(self, key: str) -> list:
        return list(self.hgetall(key).values())

    def hexists(self, key: str, field) -> bool:
        return self.hget(key, field) is not None

    def hdel(self, key: str, *fields) -> int:
        c = self._conn(); n = 0
        for f in fields:
            n += c.execute("DELETE FROM hashes WHERE key=? AND field=?", (key, self._outk(f))).rowcount
            if self._outk(f) == "body":
                self._body_drop(c, key)
        return n

    def hincrbyfloat(self, key: str, field, amount: float) -> float:
        cur = self.hget(key, field)
        v = float(_s(cur) if cur is not None else 0) + float(amount)
        self.hset(key, field, v)
        return v

    def hscan_iter(self, key: str, match: Optional[str] = None, count: int = 1000):
        import fnmatch
        return iter([(f, v) for f, v in self.hgetall(key).items()
                     if match is None or fnmatch.fnmatchcase(self._outk(f), match)])

    # ── sets ────────────────────────────────────────────────────────────
    def sadd(self, key: str, *members) -> int:
        c = self._conn(); n = 0
        for m in members:
            n += c.execute("INSERT OR IGNORE INTO sets(key, member) VALUES (?, ?)", (key, _b(m))).rowcount
        return n

    def srem(self, key: str, *members) -> int:
        c = self._conn(); n = 0
        for m in members:
            n += c.execute("DELETE FROM sets WHERE key=? AND member=?", (key, _b(m))).rowcount
        return n

    def smembers(self, key: str) -> set:
        if not self._alive(key):
            return set()
        return {self._out(m) for (m,) in self._conn().execute("SELECT member FROM sets WHERE key=?", (key,))}

    def scard(self, key: str) -> int:
        return self._conn().execute("SELECT COUNT(*) FROM sets WHERE key=?", (key,)).fetchone()[0]

    def sismember(self, key: str, member) -> bool:
        return bool(self._conn().execute("SELECT 1 FROM sets WHERE key=? AND member=?", (key, _b(member))).fetchone())

    # ── sorted sets ─────────────────────────────────────────────────────
    def zadd(self, key: str, mapping: dict, nx: bool = False) -> int:
        c = self._conn(); n = 0
        for m, score in mapping.items():
            if nx and c.execute("SELECT 1 FROM zsets WHERE key=? AND member=?", (key, _b(m))).fetchone():
                continue
            cur = c.execute("SELECT 1 FROM zsets WHERE key=? AND member=?", (key, _b(m))).fetchone()
            c.execute("INSERT OR REPLACE INTO zsets(key, member, score) VALUES (?, ?, ?)", (key, _b(m), float(score)))
            n += 0 if cur else 1
        return n

    def zrem(self, key: str, *members) -> int:
        c = self._conn(); n = 0
        for m in members:
            n += c.execute("DELETE FROM zsets WHERE key=? AND member=?", (key, _b(m))).rowcount
        return n

    def zscore(self, key: str, member) -> Optional[float]:
        row = self._conn().execute("SELECT score FROM zsets WHERE key=? AND member=?", (key, _b(member))).fetchone()
        return float(row[0]) if row else None

    def zcard(self, key: str) -> int:
        return self._conn().execute("SELECT COUNT(*) FROM zsets WHERE key=?", (key,)).fetchone()[0]

    def _zall(self, key: str, desc: bool = False) -> list:
        order = "score DESC, member DESC" if desc else "score ASC, member ASC"
        return self._conn().execute(f"SELECT member, score FROM zsets WHERE key=? ORDER BY {order}", (key,)).fetchall()

    def zrank(self, key: str, member) -> Optional[int]:
        mb = _b(member)
        for i, (m, _sc) in enumerate(self._zall(key)):
            if bytes(m) == mb:
                return i
        return None

    @staticmethod
    def _slice(rows: list, start: int, end: int) -> list:
        n = len(rows)
        if start < 0: start += n
        if end < 0: end += n
        return rows[max(start, 0):end + 1] if end >= start else []

    def zrange(self, key: str, start: int, end: int, withscores: bool = False, desc: bool = False) -> list:
        rows = self._slice(self._zall(key, desc), start, end)
        return [(self._out(m), float(s)) for m, s in rows] if withscores else [self._out(m) for m, _ in rows]

    def zrevrange(self, key: str, start: int, end: int, withscores: bool = False) -> list:
        return self.zrange(key, start, end, withscores=withscores, desc=True)

    def zrevrangebyscore(self, key: str, max, min, start: Optional[int] = None, num: Optional[int] = None) -> list:
        hi = float("inf") if max in ("+inf", "inf") else float(max)
        lo = float("-inf") if min in ("-inf",) else float(min)
        rows = [(m, s) for m, s in self._zall(key, desc=True) if lo <= s <= hi]
        if start is not None:
            rows = rows[start:start + (num or len(rows))]
        return [self._out(m) for m, _ in rows]

    # ── lists ───────────────────────────────────────────────────────────
    def _list_bounds(self, c, key):
        row = c.execute("SELECT MIN(pos), MAX(pos) FROM lists WHERE key=?", (key,)).fetchone()
        return row if row and row[0] is not None else (None, None)

    def rpush(self, key: str, *values) -> int:
        c = self._conn()
        lo, hi = self._list_bounds(c, key)
        pos = 0 if hi is None else hi + 1
        for v in values:
            c.execute("INSERT INTO lists(key, pos, value) VALUES (?, ?, ?)", (key, pos, _b(v))); pos += 1
        return self.llen(key)

    def lpush(self, key: str, *values) -> int:
        c = self._conn()
        lo, hi = self._list_bounds(c, key)
        pos = 0 if lo is None else lo - 1
        for v in values:
            c.execute("INSERT INTO lists(key, pos, value) VALUES (?, ?, ?)", (key, pos, _b(v))); pos -= 1
        return self.llen(key)

    def llen(self, key: str) -> int:
        return self._conn().execute("SELECT COUNT(*) FROM lists WHERE key=?", (key,)).fetchone()[0]

    def lrange(self, key: str, start: int, end: int) -> list:
        if not self._alive(key):
            return []
        rows = self._conn().execute("SELECT value FROM lists WHERE key=? ORDER BY pos", (key,)).fetchall()
        return [self._out(v) for (v,) in self._slice(rows, start, end)]

    def lrem(self, key: str, count: int, value) -> int:
        c = self._conn()
        if count == 0:
            return c.execute("DELETE FROM lists WHERE key=? AND value=?", (key, _b(value))).rowcount
        rows = c.execute("SELECT pos FROM lists WHERE key=? AND value=? ORDER BY pos " + ("ASC" if count > 0 else "DESC"),
                         (key, _b(value))).fetchall()[:abs(count)]
        for (p,) in rows:
            c.execute("DELETE FROM lists WHERE key=? AND pos=?", (key, p))
        return len(rows)

    # ── the three scripts the service used to run inside Redis ──────────
    def eval(self, script: str, numkeys: int, *args):
        keys, argv = list(args[:numkeys]), list(args[numkeys:])
        if "HGET" in script and "HSET" in script:          # stamp a result if the probe is still open
            probes_k, vmap_k = keys
            sid, payload, verdict = argv
            if _s(self.hget(vmap_k, sid) or "") != "PENDING":
                return 0
            self.hset(probes_k, sid, payload)
            self.hset(vmap_k, sid, verdict)
            return 1
        if "EXPIRE" in script:                                # renew a lease you own
            (k,), (owner, secs) = keys, argv
            if _s(self.get(k) or "") != _s(owner):
                return 0
            return 1 if self.expire(k, int(secs)) else 0
        if "DEL" in script:                                   # release a lease you own
            (k,), (owner,) = keys, argv
            if _s(self.get(k) or "") != _s(owner):
                return 0
            return self.delete(k)
        raise NotImplementedError("unknown script")

    # ── pipeline ────────────────────────────────────────────────────────
    def pipeline(self, transaction: bool = True) -> "Pipeline":
        return Pipeline(self)

    # ── grep: bodies that may contain every token ───────────────────────
    def grep_keys(self, tokens: list[str], prefix: str, limit: Optional[int] = None) -> list[str]:
        """Keys (code:…, code_hist:…, code_at:…) whose body contains every
        token, as a substring, case-folded. Trigram FTS answers tokens of 3+
        characters; shorter ones are checked with LIKE. The caller still
        verifies the full pattern on the body."""
        c = self._conn()
        toks = [t for t in tokens if t]
        if not toks:
            return []
        fts = [t for t in toks if len(t) >= 3]
        short = [t for t in toks if len(t) < 3]
        params: list = []
        if fts:
            match = " AND ".join('"' + t.replace('"', '""') + '"' for t in fts)
            sql = ("SELECT k.key FROM bodies_fts f JOIN body_keys k ON k.body_id = f.rowid "
                   "JOIN bodies b ON b.id = f.rowid "
                   "WHERE bodies_fts MATCH ? AND k.key LIKE ? ESCAPE '\\'")
            params += [match, prefix.replace("_", "\\_") + "%"]
        else:
            sql = ("SELECT k.key FROM body_keys k JOIN bodies b ON b.id = k.body_id "
                   "WHERE k.key LIKE ? ESCAPE '\\'")
            params += [prefix.replace("_", "\\_") + "%"]
        for t in short:
            sql += " AND instr(lower(b.body), ?) > 0"
            params.append(t.lower())
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [k for (k,) in c.execute(sql, params)]

    # ── body index upkeep ───────────────────────────────────────────────
    def _body_put(self, c: sqlite3.Connection, key: str, body: str) -> None:
        sha = hashlib.sha256(body.encode()).hexdigest()
        row = c.execute("SELECT id FROM bodies WHERE sha=?", (sha,)).fetchone()
        bid = row[0] if row else c.execute("INSERT INTO bodies(sha, body) VALUES (?, ?)", (sha, body)).lastrowid
        old = c.execute("SELECT body_id FROM body_keys WHERE key=?", (key,)).fetchone()
        c.execute("INSERT OR REPLACE INTO body_keys(key, body_id) VALUES (?, ?)", (key, bid))
        if old and old[0] != bid:
            self._body_gc(c, old[0])

    def _body_gc(self, c: sqlite3.Connection, body_id: int) -> None:
        if not c.execute("SELECT 1 FROM body_keys WHERE body_id=? LIMIT 1", (body_id,)).fetchone():
            c.execute("DELETE FROM bodies WHERE id=?", (body_id,))

    def _body_drop(self, c: sqlite3.Connection, key: str) -> None:
        old = c.execute("SELECT body_id FROM body_keys WHERE key=?", (key,)).fetchone()
        if old:
            c.execute("DELETE FROM body_keys WHERE key=?", (key,))
            self._body_gc(c, old[0])

    def optimize(self) -> None:
        """Merge the text index after a big write (the ingest calls it)."""
        self._conn().execute("INSERT INTO bodies_fts(bodies_fts) VALUES ('optimize')")

    # ── vectors ─────────────────────────────────────────────────────────
    @staticmethod
    def _vec_prefix(key: str) -> Optional[str]:
        for p in _VEC_PREFIXES:
            if key.startswith(p + ":") and key.count(":") >= 3:
                return p
        return None

    # ── vector tables ───────────────────────────────────────────────────
    # `latest` and `obsolete` are PARTITION KEYs: sqlite-vec keeps the rows
    # of each (latest, obsolete) pair in their own chunks, so a question
    # about the current state scans only the live latest rows (a small
    # part of the file) instead of every stored version. A partition key
    # cannot be UPDATEd, so a row whose flags change is deleted and
    # re-inserted with the same rowid. Older files have an unpartitioned
    # table; migrate_vec_tables() rebuilds it.
    def _vec_table(self, c: sqlite3.Connection, prefix: str) -> Optional[str]:
        row = c.execute("SELECT tbl FROM vec_tables WHERE prefix=?", (prefix,)).fetchone()
        return row[0] if row else None

    def _vec_create(self, c: sqlite3.Connection, tbl: str, dims: int) -> None:
        c.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS {tbl} USING vec0("
                  f"embedding float[{int(dims)}] distance_metric=cosine, "
                  f"latest INTEGER PARTITION KEY, obsolete INTEGER PARTITION KEY, "
                  f"skill_id TEXT, def_key TEXT, from_rank INTEGER, to_rank INTEGER)")

    def ensure_vec_table(self, prefix: str, dims: int) -> bool:
        c = self._conn()
        if not SQLITE_VEC_AVAILABLE:
            return False
        if self._vec_table(c, prefix):
            return True
        tbl = f"vec_{prefix}_p"
        self._vec_create(c, tbl, dims)
        c.execute("INSERT INTO vec_tables(prefix, dims, tbl, partitioned) VALUES (?, ?, ?, 1)",
                  (prefix, int(dims), tbl))
        return True

    def vec_tables_to_migrate(self) -> list[str]:
        """Prefixes whose vector table is the old unpartitioned layout."""
        c = self._conn()
        if not SQLITE_VEC_AVAILABLE:
            return []
        return [r[0] for r in c.execute("SELECT prefix FROM vec_tables WHERE partitioned = 0")]

    def migrate_vec_tables(self, log=print) -> None:
        """Rebuilds unpartitioned vector tables as partitioned ones. Rows
        keep their rowids, so vec_rows stays valid. One transaction per
        table; the old table is dropped at the end."""
        c = self._conn()
        for prefix in self.vec_tables_to_migrate():
            old = self._vec_table(c, prefix)
            dims = c.execute("SELECT dims FROM vec_tables WHERE prefix=?", (prefix,)).fetchone()[0]
            new = f"vec_{prefix}_p"
            total = c.execute(f"SELECT count(*) FROM {old}").fetchone()[0]
            log(f"🔧 vector table {old}: {total} rows → {new} (partitioned by latest/obsolete)")
            c.execute(f"DROP TABLE IF EXISTS {new}")
            self._vec_create(c, new, dims)
            done, t0 = 0, time.time()
            last = 0
            while True:
                batch = c.execute(f"SELECT rowid, embedding, skill_id, def_key, from_rank, to_rank, "
                                  f"latest, obsolete FROM {old} WHERE rowid > ? ORDER BY rowid LIMIT 2000",
                                  (last,)).fetchall()
                if not batch:
                    break
                c.execute("BEGIN")
                c.executemany(f"INSERT INTO {new}(rowid, embedding, latest, obsolete, skill_id, def_key, "
                              f"from_rank, to_rank) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                              [(r[0], r[1], int(r[6] or 0), int(r[7] or 0), r[2], r[3],
                                int(r[4] or 0), int(r[5] or 0)) for r in batch])
                c.execute("COMMIT")
                last = batch[-1][0]
                done += len(batch)
                if done % 20000 < 2000:
                    log(f"   {done}/{total} rows, {time.time() - t0:.0f}s")
            c.execute("UPDATE vec_tables SET tbl=?, partitioned=1 WHERE prefix=?", (new, prefix))
            c.execute(f"DROP TABLE {old}")
            log(f"   done: {done} rows in {time.time() - t0:.0f}s")

    def _vec_sync(self, c: sqlite3.Connection, key: str, changed: Optional[dict] = None) -> None:
        """Mirror a chunk-vector hash row into its vec0 table."""
        p = self._vec_prefix(key)
        if p is None or not SQLITE_VEC_AVAILABLE:
            return
        rows = dict(c.execute("SELECT field, value FROM hashes WHERE key=?", (key,)).fetchall())
        emb = rows.get("embedding")
        if emb is None:
            return
        dims = len(emb) // 4
        if not self._vec_table(c, p):
            self.ensure_vec_table(p, dims)
        tbl = self._vec_table(c, p)
        skill_id, def_key = _s(rows.get("skill_id", b"")), _s(rows.get("def_key", b""))
        from_rank, to_rank = (int(_s(rows.get("from_rank", b"0")) or 0),
                              int(_s(rows.get("to_rank", b"0")) or 0))
        latest, obsolete = (int(_s(rows.get("latest", b"0")) == "1"),
                            int(_s(rows.get("obsolete", b"0")) == "1"))
        cur = c.execute("SELECT rowid_in_vec FROM vec_rows WHERE key=?", (key,)).fetchone()
        if cur and changed is not None and "embedding" not in {self._outk(k) for k in changed}:
            have = c.execute(f"SELECT latest, obsolete FROM {tbl} WHERE rowid=?", (cur[0],)).fetchone()
            if have and (int(have[0]), int(have[1])) == (latest, obsolete):
                c.execute(f"UPDATE {tbl} SET skill_id=?, def_key=?, from_rank=?, to_rank=? WHERE rowid=?",
                          (skill_id, def_key, from_rank, to_rank, cur[0]))
                return
            # a partition key changed: the row moves (same rowid)
            c.execute(f"DELETE FROM {tbl} WHERE rowid=?", (cur[0],))
            c.execute(f"INSERT INTO {tbl}(rowid, embedding, latest, obsolete, skill_id, def_key, from_rank, to_rank) "
                      f"VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                      (cur[0], bytes(emb), latest, obsolete, skill_id, def_key, from_rank, to_rank))
            return
        if cur:
            c.execute(f"DELETE FROM {tbl} WHERE rowid=?", (cur[0],))
            c.execute("DELETE FROM vec_rows WHERE key=?", (key,))
        rid = c.execute(f"INSERT INTO {tbl}(embedding, latest, obsolete, skill_id, def_key, from_rank, to_rank) "
                        f"VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (bytes(emb), latest, obsolete, skill_id, def_key, from_rank, to_rank)).lastrowid
        c.execute("INSERT INTO vec_rows(key, prefix, rowid_in_vec) VALUES (?, ?, ?)", (key, p, rid))

    def _vec_delete(self, c: sqlite3.Connection, key: str) -> None:
        if not SQLITE_VEC_AVAILABLE:
            return
        cur = c.execute("SELECT prefix, rowid_in_vec FROM vec_rows WHERE key=?", (key,)).fetchone()
        if cur:
            tbl = self._vec_table(c, cur[0])
            if tbl:
                c.execute(f"DELETE FROM {tbl} WHERE rowid=?", (cur[1],))
            c.execute("DELETE FROM vec_rows WHERE key=?", (key,))

    def _vec_rename(self, c: sqlite3.Connection, src: str, dst: str) -> None:
        if not SQLITE_VEC_AVAILABLE:
            return
        c.execute("UPDATE vec_rows SET key=? WHERE key=?", (dst, src))

    def knn(self, prefix: str, vector: bytes, k: int, *, as_of_rank: Optional[int] = None,
            latest_only: bool = False, include_obsolete: bool = True) -> list[dict]:
        """The k nearest chunk rows of one store (cosine distance, exact).
        as_of_rank: only versions valid at that commit rank
        (from_rank <= rank < to_rank). latest_only: only each skill's
        newest version. Rows: {skill_id, def_key, vector_distance}."""
        c = self._conn()
        tbl = self._vec_table(c, prefix) if SQLITE_VEC_AVAILABLE else None
        if not tbl:
            return []
        where, params = ["embedding MATCH ?", "k = ?"], [vector, int(k)]
        if as_of_rank is not None:
            where += ["from_rank <= ?", "to_rank > ?"]; params += [int(as_of_rank), int(as_of_rank)]
        elif latest_only:
            where.append("latest = 1")
        if not include_obsolete:
            where.append("obsolete = 0")
        rows = c.execute(f"SELECT skill_id, def_key, distance FROM {tbl} WHERE " + " AND ".join(where)
                         + " ORDER BY distance", params).fetchall()
        return [{"skill_id": s, "def_key": d, "vector_distance": float(dist)} for s, d, dist in rows]


for _name, _fn in list(vars(Store).items()):
    if callable(_fn) and not _name.startswith("_") and _name not in ("binary", "pipeline", "close"):
        setattr(Store, _name, _borrowed(_fn))
del _name, _fn


class Pipeline:
    """Queues calls; execute() runs them in one transaction and returns
    the list of their results."""

    def __init__(self, store: Store):
        self._store = store
        self._calls: list[tuple[str, tuple, dict]] = []

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        def q(*a, **kw):
            self._calls.append((name, a, kw)); return self
        return q

    def execute(self) -> list:
        s = self._store
        if getattr(s._local, "conn", None) is not None:
            return self._run()
        c = s._take()
        s._local.conn = c
        try:
            return self._run()
        finally:
            s._local.conn = None
            s._pool.put(c)

    def _run(self) -> list:
        s = self._store
        c = s._conn()
        out = []
        with s._lock:
            c.execute("BEGIN")
            try:
                for name, a, kw in self._calls:
                    out.append(getattr(s, name)(*a, **kw))
                c.execute("COMMIT")
            except Exception:
                c.execute("ROLLBACK"); raise
        self._calls = []
        return out
"""Durable Studio storage: SQLite (transactional) for jobs, events, findings, decisions and releases; files for raw bytes, staged rows and
release snapshots. Everything the Studio knows survives a process restart. Raw files and release snapshots are content-hash checked on read.

Events form a hash chain: each row's hash covers the previous row's hash, so editing or deleting history is detectable (verify_chain).
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources(source_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, classification TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs(
  job_id TEXT PRIMARY KEY, seq INTEGER UNIQUE NOT NULL, source_id TEXT NOT NULL, filename TEXT, format TEXT, sha256 TEXT, bytes INTEGER,
  target TEXT NOT NULL, scope TEXT NOT NULL DEFAULT '', classification TEXT NOT NULL, operator TEXT, status TEXT NOT NULL, blocking INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, elapsed_ms INTEGER, error_code TEXT, error_message TEXT, duplicate_of TEXT, supersedes TEXT,
  content_hash TEXT, manifest TEXT, profile TEXT, findings_summary TEXT);
CREATE INDEX IF NOT EXISTS jobs_lookup ON jobs(source_id, sha256, target, scope);
CREATE TABLE IF NOT EXISTS findings(id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL, stage TEXT, severity TEXT, code TEXT, row INTEGER, field TEXT, message TEXT, detail TEXT);
CREATE INDEX IF NOT EXISTS findings_job ON findings(job_id);
CREATE TABLE IF NOT EXISTS events(
  seq INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, ts TEXT NOT NULL, stage TEXT NOT NULL, kind TEXT NOT NULL, message TEXT, counts TEXT, elapsed_ms INTEGER, error TEXT,
  prev_hash TEXT NOT NULL, hash TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS events_job ON events(job_id);
CREATE TABLE IF NOT EXISTS decisions(decision_id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL, decision TEXT NOT NULL, reviewer TEXT NOT NULL, reason TEXT NOT NULL, at TEXT NOT NULL, detail TEXT);
CREATE TABLE IF NOT EXISTS releases(
  release_id INTEGER PRIMARY KEY AUTOINCREMENT, dataset TEXT NOT NULL, scope TEXT NOT NULL DEFAULT '', version INTEGER NOT NULL, job_id TEXT NOT NULL, content_hash TEXT NOT NULL,
  path TEXT NOT NULL, rows INTEGER NOT NULL, status TEXT NOT NULL, parent_release_id INTEGER, created_at TEXT NOT NULL, approved_by TEXT NOT NULL, UNIQUE(dataset, scope, version));
CREATE TABLE IF NOT EXISTS discovery_runs(
  run_id TEXT PRIMARY KEY, entity_id TEXT NOT NULL, as_of TEXT NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL, job_id TEXT, selected INTEGER NOT NULL DEFAULT 0, path TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS discovery_runs_entity ON discovery_runs(entity_id, created_at);
CREATE TABLE IF NOT EXISTS current_release(dataset TEXT NOT NULL, scope TEXT NOT NULL DEFAULT '', release_id INTEGER, PRIMARY KEY(dataset, scope));
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class StoreError(Exception):
    pass


class IntegrityError(StoreError):
    """A stored file no longer matches its recorded hash."""


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class StudioStore:
    def __init__(self, root, clock=None):
        self.root = Path(root)
        self.clock = clock or utcnow
        for sub in ("raw", "staging", "releases", "discovery"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "studio.db"
        boot = sqlite3.connect(self.db_path, timeout=30)
        try:
            boot.execute("PRAGMA journal_mode=WAL")
            boot.executescript(SCHEMA)
        finally:
            boot.close()

    # ------------------------------------------------------------------ plumbing
    @contextmanager
    def _tx(self):
        conn = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            conn.close()

    def _one(self, sql, args=()):
        with self._tx() as c:
            row = c.execute(sql, args).fetchone()
        return dict(row) if row else None

    def _all(self, sql, args=()):
        with self._tx() as c:
            return [dict(r) for r in c.execute(sql, args).fetchall()]

    # ------------------------------------------------------------------ raw bytes
    def put_raw(self, data: bytes) -> str:
        sha = hashlib.sha256(data).hexdigest()
        path = self.root / "raw" / sha[:2] / sha
        if path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
                raise IntegrityError(f"stored raw file {sha} does not match its hash")
        else:
            _atomic_write(path, data)
        return sha

    def read_raw(self, sha: str) -> bytes:
        data = (self.root / "raw" / sha[:2] / sha).read_bytes()
        if hashlib.sha256(data).hexdigest() != sha:
            raise IntegrityError(f"stored raw file {sha} was altered")
        return data

    # ------------------------------------------------------------------ sources and jobs
    def register_source(self, source_id: str, classification: str) -> None:
        with self._tx() as c:
            c.execute("INSERT OR IGNORE INTO sources(source_id, created_at, classification) VALUES (?,?,?)", (source_id, self.clock(), classification))

    def find_existing(self, source_id, sha, target, scope):
        return self._one("SELECT * FROM jobs WHERE source_id=? AND sha256=? AND target=? AND scope=? AND status NOT IN ('FAILED','REJECTED_INPUT') ORDER BY seq DESC LIMIT 1",
                         (source_id, sha, target, scope))

    def new_job(self, *, source_id, filename, fmt, sha, nbytes, target, scope, classification, operator, supersedes=None, duplicate_of=None, status="ACQUIRING") -> dict:
        now = self.clock()
        with self._tx() as c:
            seq = c.execute("SELECT COALESCE(MAX(seq),0)+1 FROM jobs").fetchone()[0]
            job_id = f"job-{seq:05d}-{(sha or '00000000')[:8]}"
            c.execute("INSERT INTO jobs(job_id, seq, source_id, filename, format, sha256, bytes, target, scope, classification, operator, status, created_at, updated_at, supersedes, duplicate_of)"
                      " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (job_id, seq, source_id, filename, fmt, sha, nbytes, target, scope, classification, operator, status, now, now, supersedes, duplicate_of))
        return self.get_job(job_id)

    def update_job(self, job_id, **fields) -> None:
        if not fields:
            return
        for k in ("manifest", "profile", "findings_summary"):
            if k in fields and not isinstance(fields[k], str) and fields[k] is not None:
                fields[k] = canonical_json(fields[k])
        fields["updated_at"] = self.clock()
        cols = ", ".join(f"{k}=?" for k in fields)
        with self._tx() as c:
            c.execute(f"UPDATE jobs SET {cols} WHERE job_id=?", (*fields.values(), job_id))   # noqa: S608 - column names come from this module only

    def get_job(self, job_id) -> dict | None:
        row = self._one("SELECT * FROM jobs WHERE job_id=?", (job_id,))
        if row:
            for k in ("manifest", "profile", "findings_summary"):
                row[k] = json.loads(row[k]) if row.get(k) else None
            row["blocking"] = bool(row["blocking"])
        return row

    def list_jobs(self, limit=100) -> list:
        rows = self._all("SELECT job_id, seq, source_id, filename, format, sha256, bytes, target, scope, status, blocking, created_at, updated_at, elapsed_ms, error_code, duplicate_of FROM jobs ORDER BY seq DESC LIMIT ?", (limit,))
        for r in rows:
            r["blocking"] = bool(r["blocking"])
        return rows

    # ------------------------------------------------------------------ events (hash chained)
    def _event(self, c, job_id, stage, kind, message="", counts=None, elapsed_ms=None, error=None) -> dict:
        body = {"job_id": job_id, "ts": self.clock(), "stage": stage, "kind": kind, "message": message, "counts": counts, "elapsed_ms": elapsed_ms, "error": error}
        last = c.execute("SELECT hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        prev = last["hash"] if last else "0" * 64
        h = sha256_text(prev + canonical_json(body))
        c.execute("INSERT INTO events(job_id, ts, stage, kind, message, counts, elapsed_ms, error, prev_hash, hash) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (job_id, body["ts"], stage, kind, message, canonical_json(counts) if counts is not None else None, elapsed_ms, canonical_json(error) if error is not None else None, prev, h))
        return {**body, "hash": h}

    def add_event(self, job_id, stage, kind, message="", counts=None, elapsed_ms=None, error=None) -> dict:
        with self._tx() as c:
            return self._event(c, job_id, stage, kind, message, counts, elapsed_ms, error)

    def events(self, job_id=None, limit=1000) -> list:
        sql, args = ("SELECT * FROM events WHERE job_id=? ORDER BY seq LIMIT ?", (job_id, limit)) if job_id else ("SELECT * FROM events ORDER BY seq DESC LIMIT ?", (limit,))
        rows = self._all(sql, args)
        for r in rows:
            r["counts"] = json.loads(r["counts"]) if r["counts"] else None
            r["error"] = json.loads(r["error"]) if r["error"] else None
        return rows

    def events_since(self, seq: int = 0, job_id=None, limit=500) -> list:
        """Ledger rows after `seq`, oldest first (what a polling or streaming client has not seen yet)."""
        sql, args = (("SELECT * FROM events WHERE seq>? AND job_id=? ORDER BY seq LIMIT ?", (seq, job_id, limit)) if job_id else ("SELECT * FROM events WHERE seq>? ORDER BY seq LIMIT ?", (seq, limit)))
        rows = self._all(sql, args)
        for r in rows:
            r["counts"] = json.loads(r["counts"]) if r["counts"] else None
            r["error"] = json.loads(r["error"]) if r["error"] else None
        return rows

    def last_seq(self) -> int:
        return (self._one("SELECT COALESCE(MAX(seq),0) AS s FROM events") or {"s": 0})["s"]

    def verify_chain(self) -> dict:
        prev, n = "0" * 64, 0
        for r in self._all("SELECT * FROM events ORDER BY seq"):
            body = {"job_id": r["job_id"], "ts": r["ts"], "stage": r["stage"], "kind": r["kind"], "message": r["message"],
                    "counts": json.loads(r["counts"]) if r["counts"] else None, "elapsed_ms": r["elapsed_ms"], "error": json.loads(r["error"]) if r["error"] else None}
            if r["prev_hash"] != prev or sha256_text(prev + canonical_json(body)) != r["hash"]:
                return {"ok": False, "events": n, "first_bad_seq": r["seq"]}
            prev, n = r["hash"], n + 1
        return {"ok": True, "events": n, "first_bad_seq": None}

    # ------------------------------------------------------------------ findings, staging, decisions
    def add_findings(self, job_id, items) -> None:
        with self._tx() as c:
            c.execute("DELETE FROM findings WHERE job_id=?", (job_id,))
            c.executemany("INSERT INTO findings(job_id, stage, severity, code, row, field, message, detail) VALUES (?,?,?,?,?,?,?,?)",
                          [(job_id, f.get("stage"), f["severity"], f["code"], f.get("row"), f.get("field"), f["message"],
                            canonical_json({k: v for k, v in f.items() if k not in ("stage", "severity", "code", "row", "field", "message")}) or None) for f in items])

    def findings(self, job_id, limit=1000) -> list:
        rows = self._all("SELECT stage, severity, code, row, field, message, detail FROM findings WHERE job_id=? ORDER BY id LIMIT ?", (job_id, limit))
        for r in rows:
            extra = json.loads(r.pop("detail") or "{}")
            r.update(extra)
            for k in [k for k, v in r.items() if v is None]:
                del r[k]
        return rows

    def save_staging(self, job_id, obj) -> str:
        data = canonical_json(obj).encode("utf-8")
        _atomic_write(self.root / "staging" / f"{job_id}.json", data)
        return hashlib.sha256(data).hexdigest()

    def load_staging(self, job_id) -> dict | None:
        path = self.root / "staging" / f"{job_id}.json"
        return json.loads(path.read_text("utf-8")) if path.exists() else None

    def add_decision(self, job_id, decision, reviewer, reason, detail=None) -> int:
        with self._tx() as c:
            cur = c.execute("INSERT INTO decisions(job_id, decision, reviewer, reason, at, detail) VALUES (?,?,?,?,?,?)",
                            (job_id, decision, reviewer, reason, self.clock(), canonical_json(detail) if detail is not None else None))
            return cur.lastrowid

    def decisions(self, job_id) -> list:
        rows = self._all("SELECT * FROM decisions WHERE job_id=? ORDER BY decision_id", (job_id,))
        for r in rows:
            r["detail"] = json.loads(r["detail"]) if r["detail"] else None
        return rows

    # ------------------------------------------------------------------ releases
    def release_path(self, dataset, scope, version) -> Path:
        return self.root / "releases" / dataset / (scope or "_") / f"v{version:04d}.json"

    def current(self, dataset, scope="") -> dict | None:
        return self._one("SELECT r.* FROM current_release c JOIN releases r ON r.release_id=c.release_id WHERE c.dataset=? AND c.scope=?", (dataset, scope))

    def list_current(self) -> list:
        return self._all("SELECT r.dataset, r.scope, r.version, r.release_id, r.rows, r.content_hash, r.created_at, r.approved_by, r.job_id FROM current_release c "
                         "JOIN releases r ON r.release_id=c.release_id ORDER BY r.dataset, r.scope")

    def releases(self, dataset, scope="") -> list:
        return self._all("SELECT release_id, dataset, scope, version, job_id, content_hash, rows, status, parent_release_id, created_at, approved_by FROM releases WHERE dataset=? AND scope=? ORDER BY version",
                         (dataset, scope))

    def get_release(self, release_id) -> dict | None:
        return self._one("SELECT * FROM releases WHERE release_id=?", (release_id,))

    def read_release(self, release_id) -> dict:
        rel = self.get_release(release_id)
        if not rel:
            raise StoreError(f"no release {release_id}")
        text = Path(rel["path"]).read_text("utf-8")
        doc = json.loads(text)
        if sha256_text(canonical_json(doc["rows"])) != rel["content_hash"]:
            raise IntegrityError(f"release {release_id} no longer matches its recorded hash")
        return doc

    def write_release_file(self, dataset, scope, version, doc) -> Path:
        path = self.release_path(dataset, scope, version)
        _atomic_write(path, canonical_json(doc).encode("utf-8"))
        return path

    # ------------------------------------------------------------------ atomic state changes (one transaction each)
    def next_version(self, dataset, scope="") -> int:
        row = self._one("SELECT COALESCE(MAX(version),0)+1 AS v FROM releases WHERE dataset=? AND scope=?", (dataset, scope))
        return row["v"]

    def commit_release(self, *, dataset, scope, job_id, version, content_hash, path, rows, reviewer, reason, detail) -> int:
        """Publish an approved release: insert it, supersede the previous one, move the current pointer, close the job - all or nothing."""
        now = self.clock()
        with self._tx() as c:
            cur = c.execute("SELECT release_id FROM current_release WHERE dataset=? AND scope=?", (dataset, scope)).fetchone()
            parent = cur["release_id"] if cur and cur["release_id"] else None
            rid = c.execute("INSERT INTO releases(dataset, scope, version, job_id, content_hash, path, rows, status, parent_release_id, created_at, approved_by) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            (dataset, scope, version, job_id, content_hash, str(path), rows, "ACTIVE", parent, now, reviewer)).lastrowid
            if parent:
                c.execute("UPDATE releases SET status='SUPERSEDED' WHERE release_id=?", (parent,))
            c.execute("INSERT INTO current_release(dataset, scope, release_id) VALUES (?,?,?) ON CONFLICT(dataset, scope) DO UPDATE SET release_id=excluded.release_id", (dataset, scope, rid))
            c.execute("UPDATE jobs SET status='APPROVED', updated_at=? WHERE job_id=?", (now, job_id))
            c.execute("INSERT INTO decisions(job_id, decision, reviewer, reason, at, detail) VALUES (?,?,?,?,?,?)", (job_id, "APPROVE", reviewer, reason, now, canonical_json(detail)))
            self._event(c, job_id, "REVIEW", "APPROVED", message=f"{dataset}{('/' + scope) if scope else ''} v{version}", counts={"rows": rows, "release_id": rid})
        return rid

    def reject_job(self, job_id, reviewer, reason, detail=None) -> None:
        now = self.clock()
        with self._tx() as c:
            c.execute("UPDATE jobs SET status='REJECTED', updated_at=? WHERE job_id=?", (now, job_id))
            c.execute("INSERT INTO decisions(job_id, decision, reviewer, reason, at, detail) VALUES (?,?,?,?,?,?)", (job_id, "REJECT", reviewer, reason, now, canonical_json(detail) if detail is not None else None))
            self._event(c, job_id, "REVIEW", "REJECTED", message=reason[:200])

    def switch_current(self, *, dataset, scope, target_release_id, reviewer, reason, kind) -> None:
        """Make `target_release_id` current (or clear the pointer when None). Newer releases become ROLLED_BACK; nothing is deleted."""
        now = self.clock()
        with self._tx() as c:
            cur = c.execute("SELECT r.release_id, r.version, r.job_id FROM current_release c JOIN releases r ON r.release_id=c.release_id WHERE c.dataset=? AND c.scope=?", (dataset, scope)).fetchone()
            target_version = 0
            if target_release_id is not None:
                t = c.execute("SELECT version FROM releases WHERE release_id=? AND dataset=? AND scope=?", (target_release_id, dataset, scope)).fetchone()
                target_version = t["version"]
                c.execute("UPDATE releases SET status='ACTIVE' WHERE release_id=?", (target_release_id,))
            c.execute("UPDATE releases SET status='ROLLED_BACK' WHERE dataset=? AND scope=? AND version>? AND status IN ('ACTIVE','SUPERSEDED')", (dataset, scope, target_version))
            c.execute("INSERT INTO current_release(dataset, scope, release_id) VALUES (?,?,?) ON CONFLICT(dataset, scope) DO UPDATE SET release_id=excluded.release_id", (dataset, scope, target_release_id))
            self._event(c, cur["job_id"] if cur else None, "REVIEW", kind, message=f"{dataset}{('/' + scope) if scope else ''}: {reason[:160]}",
                        counts={"from_release": cur["release_id"] if cur else None, "to_release": target_release_id, "reviewer": reviewer})

    # ------------------------------------------------------------------ discovery runs (artifacts + index)
    def save_run(self, run: dict) -> Path:
        path = self.root / "discovery" / f"{run['run_id']}.json"
        _atomic_write(path, canonical_json(run).encode("utf-8"))
        with self._tx() as c:
            c.execute("INSERT INTO discovery_runs(run_id, entity_id, as_of, created_at, status, job_id, selected, path) VALUES (?,?,?,?,?,?,?,?) "
                      "ON CONFLICT(run_id) DO UPDATE SET created_at=excluded.created_at, status=excluded.status, job_id=excluded.job_id, selected=excluded.selected",
                      (run["run_id"], run["entity"]["entity_id"], run["as_of"], self.clock(), run["status"], run.get("staging_job_id"), len(run.get("selected_event_ids", [])), str(path)))
        return path

    def load_run(self, run_id) -> dict | None:
        row = self._one("SELECT path FROM discovery_runs WHERE run_id=?", (run_id,))
        return json.loads(Path(row["path"]).read_text("utf-8")) if row else None

    def latest_run(self, entity_id) -> dict | None:
        row = self._one("SELECT run_id FROM discovery_runs WHERE entity_id=? ORDER BY created_at DESC, rowid DESC LIMIT 1", (entity_id,))
        return self.load_run(row["run_id"]) if row else None

    def list_runs(self, limit=50) -> list:
        return self._all("SELECT run_id, entity_id, as_of, created_at, status, job_id, selected FROM discovery_runs ORDER BY created_at DESC LIMIT ?", (limit,))

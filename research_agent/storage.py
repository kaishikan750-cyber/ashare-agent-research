from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from uuid import uuid4
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    """Transactional local storage, shared by API/MCP processes. No model keys persisted."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "experiments.sqlite3"
        with self.connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, status TEXT, created_at TEXT, updated_at TEXT, request TEXT, result TEXT, error TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, created_at TEXT, payload TEXT)")

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=20)
        conn.row_factory = sqlite3.Row
        return conn

    def create(self, request: dict) -> str:
        ident = uuid4().hex
        with self.connect() as conn:
            conn.execute("INSERT INTO jobs VALUES (?, 'queued', ?, ?, ?, NULL, NULL)",
                         (ident, now(), now(), json.dumps(request, ensure_ascii=False, allow_nan=False)))
        return ident

    def update(self, ident, status, result=None, error=None):
        with self.connect() as conn:
            conn.execute("UPDATE jobs SET status=?, updated_at=?, result=?, error=? WHERE id=?",
                         (status, now(), json.dumps(result, ensure_ascii=False, allow_nan=False) if result is not None else None, error, ident))

    def event(self, ident, payload):
        with self.connect() as conn:
            conn.execute("INSERT INTO events (job_id, created_at, payload) VALUES (?, ?, ?)",
                         (ident, now(), json.dumps(payload, ensure_ascii=False, allow_nan=False)))

    def get(self, ident):
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (ident,)).fetchone()
            if row is None:
                raise KeyError(ident)
            job = dict(row)
            job["request"] = json.loads(job["request"])
            job["result"] = json.loads(job["result"]) if job["result"] else None
            job["events"] = [{"seq": r["seq"], "created_at": r["created_at"], **json.loads(r["payload"])}
                             for r in conn.execute("SELECT * FROM events WHERE job_id=? ORDER BY seq", (ident,))]
            return job

    def list(self):
        with self.connect() as conn:
            return [dict(r) for r in conn.execute("SELECT id,status,created_at,updated_at,error FROM jobs ORDER BY created_at DESC LIMIT 50")]

    def mark_interrupted(self):
        """Call on startup of the single local API process, never on an MCP reader."""
        with self.connect() as conn:
            conn.execute("UPDATE jobs SET status='failed', updated_at=?, error=? WHERE status IN ('queued','running')",
                         (now(), "进程在实验结束前退出，请重新提交；已保存的事件仍可查看。"))

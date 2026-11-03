"""Small SQLite store for new jobs and reviews, separate from immutable results/."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from api.schemas import Feedback, FeedbackInput


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, config TEXT NOT NULL,
                    status TEXT NOT NULL, created_at TEXT NOT NULL, completed_at TEXT,
                    result TEXT, progress TEXT, error TEXT);
                CREATE TABLE IF NOT EXISTS feedback (
                    id TEXT PRIMARY KEY, target_type TEXT NOT NULL, target_id TEXT NOT NULL,
                    label TEXT NOT NULL, comment TEXT NOT NULL, reviewer TEXT NOT NULL,
                    created_at TEXT NOT NULL);
            """)

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def create_job(self, kind: str, config: dict) -> dict:
        job_id = str(uuid4())
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO jobs(id,kind,config,status,created_at) VALUES(?,?,?,?,?)",
                (job_id, kind, json.dumps(config), "PENDING", now()),
            )
        return self.job(job_id)

    def job(self, job_id: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        for key in ("config", "result", "progress"):
            result[key] = json.loads(result[key]) if result[key] else None
        return result

    def jobs(self, kind: str | None = None) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT id FROM jobs ORDER BY created_at DESC LIMIT 500"
            ).fetchall()
        jobs = [self.job(row["id"]) for row in rows]
        return [job for job in jobs if kind is None or job["kind"] == kind]

    def update(
        self, job_id: str, status: str, *, result=None, progress=None, error=None
    ) -> None:
        if status == "FAILED":
            progress = (
                progress
                if progress is not None
                else (self.job(job_id) or {}).get("progress")
            )
            if progress:
                stopped = []
                for item in progress:
                    item = dict(item)
                    if item["status"] == "running" or item["id"] == "result":
                        item.update(
                            status="error",
                            note=error
                            or "Uitvoering afgebroken; geen resultaat goedgekeurd.",
                        )
                    elif item["status"] == "pending":
                        item.update(
                            status="skipped",
                            note="Niet uitgevoerd doordat de taak is afgebroken.",
                        )
                    stopped.append(item)
                progress = stopped
        completed = now() if status in {"COMPLETED", "FAILED"} else None
        with self.connection() as conn:
            conn.execute(
                "UPDATE jobs SET status=?,result=COALESCE(?,result),progress=COALESCE(?,progress),error=?,completed_at=? WHERE id=?",
                (
                    status,
                    json.dumps(result, allow_nan=False) if result is not None else None,
                    json.dumps(progress) if progress is not None else None,
                    error,
                    completed,
                    job_id,
                ),
            )

    def recover_interrupted(self) -> None:
        with self.connection() as conn:
            ids = [
                row["id"]
                for row in conn.execute(
                    "SELECT id FROM jobs WHERE status IN ('PENDING','RUNNING')"
                ).fetchall()
            ]
        for job_id in ids:
            self.update(
                job_id,
                "FAILED",
                error="Proces onderbroken door een API-herstart; niet automatisch hervat.",
            )

    def add_feedback(self, value: FeedbackInput) -> Feedback:
        feedback = Feedback(**value.model_dump(), id=str(uuid4()), created_at=now())
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO feedback VALUES(?,?,?,?,?,?,?)",
                tuple(
                    feedback.model_dump()[key]
                    for key in (
                        "id",
                        "target_type",
                        "target_id",
                        "label",
                        "comment",
                        "reviewer",
                        "created_at",
                    )
                ),
            )
        return feedback

    def feedback(self, target_id: str | None = None) -> list[Feedback]:
        with self.connection() as conn:
            rows = (
                conn.execute(
                    "SELECT * FROM feedback WHERE target_id=? ORDER BY created_at DESC LIMIT 500",
                    (target_id,),
                ).fetchall()
                if target_id
                else conn.execute(
                    "SELECT * FROM feedback ORDER BY created_at DESC LIMIT 500"
                ).fetchall()
            )
        return [Feedback(**dict(row)) for row in rows]

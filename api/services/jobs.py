"""One bounded local worker process; no shell, distributed queue or fake progress."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

from api.config import Settings
from api.services.privacy import redact
from api.services.storage import Store


class BusyError(Exception):
    pass


class JobManager:
    def __init__(self, settings: Settings, store: Store):
        self.settings, self.store = settings, store
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sue-worker")
        self.slots = threading.BoundedSemaphore(2)
        self.processes: set[subprocess.Popen] = set()
        self.lock = threading.Lock()
        self.closing = False

    def start(self, kind: str, config: dict) -> dict:
        if self.closing or not self.slots.acquire(blocking=False):
            raise BusyError(
                "Er loopt al een taak en er staat er één in de wachtrij. Probeer later opnieuw."
            )
        try:
            job = self.store.create_job(kind, config)
            self.pool.submit(self._execute, job["id"])
            return job
        except Exception:
            self.slots.release()
            raise

    def _execute(self, job_id: str):
        process = None
        try:
            self.store.update(job_id, "RUNNING")
            env = {
                **os.environ,
                "SUE_DATA_DIR": str(self.settings.data_dir.resolve()),
                "SUE_PROJECT_ROOT": str(self.settings.root.resolve()),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            # argv contains a fixed module and generated UUID, never SQL or credentials.
            process = subprocess.Popen(
                [sys.executable, "-B", "-m", "api.worker", job_id],
                cwd=self.settings.root,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            with self.lock:
                self.processes.add(process)
            _, stderr = process.communicate(timeout=self.settings.timeout_seconds)
            if self.store.job(job_id)["status"] not in {"COMPLETED", "FAILED"}:
                self.store.update(
                    job_id,
                    "FAILED",
                    error=redact(stderr or "Worker gestopt zonder resultaat.")[:1000],
                )
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            self.store.update(
                job_id,
                "FAILED",
                error="Maximale taakduur overschreden; worker beëindigd. Geen resultaat goedgekeurd.",
            )
        except Exception as exc:
            self.store.update(
                job_id, "FAILED", error=redact(f"{type(exc).__name__}: {exc}")[:1000]
            )
        finally:
            with self.lock:
                self.processes.discard(process)
            self.slots.release()

    def close(self):
        self.closing = True
        with self.lock:
            for process in self.processes:
                if process.poll() is None:
                    process.terminate()
        self.pool.shutdown(wait=True, cancel_futures=True)

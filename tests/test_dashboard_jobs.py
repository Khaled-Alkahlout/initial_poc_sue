import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from api.config import ROOT, Settings
from api.services.jobs import BusyError, JobManager
from api.services.storage import Store


class JobManagementTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.settings = Settings(
            root=ROOT, data_dir=Path(self.directory.name), timeout_seconds=1
        )
        self.store = Store(self.settings.database_path)
        self.manager = JobManager(self.settings, self.store)

    def tearDown(self):
        self.manager.close()
        self.directory.cleanup()

    def test_concurrency_and_queue_are_bounded(self):
        with patch.object(self.manager.pool, "submit"):
            self.manager.start("test", {"suite": "selection"})
            self.manager.start("test", {"suite": "selection"})
            with self.assertRaises(BusyError):
                self.manager.start("test", {"suite": "selection"})

    def test_timeout_kills_worker_and_records_failure(self):
        job = self.store.create_job("test", {"suite": "selection"})
        process = Mock()
        process.communicate.side_effect = [
            subprocess.TimeoutExpired("fixed-worker", 1),
            ("", ""),
        ]
        self.manager.slots.acquire()
        with patch(
            "api.services.jobs.subprocess.Popen", return_value=process
        ) as factory:
            self.manager._execute(job["id"])
        process.kill.assert_called_once()
        self.assertNotIn("shell", factory.call_args.kwargs)
        self.assertEqual(factory.call_args.args[0][-1], job["id"])
        self.assertEqual(self.store.job(job["id"])["status"], "FAILED")

    def test_interrupted_jobs_do_not_resume_silently(self):
        job = self.store.create_job("test", {"suite": "selection"})
        self.store.update(job["id"], "RUNNING")
        self.store.recover_interrupted()
        self.assertEqual(self.store.job(job["id"])["status"], "FAILED")
        self.assertIn("onderbroken", self.store.job(job["id"])["error"])

    def test_worker_without_a_result_is_a_failure_even_with_exit_code_zero(self):
        job = self.store.create_job("test", {"suite": "selection"})
        process = Mock(returncode=0)
        process.communicate.return_value = ("", "")
        self.manager.slots.acquire()
        with patch("api.services.jobs.subprocess.Popen", return_value=process):
            self.manager._execute(job["id"])
        self.assertEqual(self.store.job(job["id"])["status"], "FAILED")

    def test_failed_task_does_not_leave_a_running_phase_visible(self):
        job = self.store.create_job("test", {"suite": "selection"})
        self.store.update(
            job["id"],
            "RUNNING",
            progress=[
                {"id": "selection", "status": "passed", "note": "done"},
                {"id": "generation", "status": "running", "note": "busy"},
                {"id": "benchmark", "status": "pending", "note": "waiting"},
                {"id": "result", "status": "pending", "note": "waiting"},
            ],
        )
        self.store.update(job["id"], "FAILED", error="timeout")
        progress = self.store.job(job["id"])["progress"]
        self.assertEqual(
            [s["status"] for s in progress], ["passed", "error", "skipped", "error"]
        )


if __name__ == "__main__":
    unittest.main()

"""Internal entrypoint for the API's fixed, time-bounded operations."""

from pathlib import Path
import os
import sys
from uuid import UUID

from api.config import Settings
from api.services.catalog import Catalog
from api.services.privacy import redact
from api.services.storage import Store
from api.services.workflows import execute_run, execute_tests
from api.services.runtime import ensure_current


def main():
    job_id = str(UUID(sys.argv[1]))
    settings = Settings(
        root=Path(
            os.getenv("SUE_PROJECT_ROOT", str(Path(__file__).resolve().parents[1]))
        )
    )
    store = Store(settings.database_path)
    job = store.job(job_id)
    if job is None:
        raise SystemExit(2)
    try:
        # Recheck configuration inside the process; no bypass through queued inputs.
        config = job["config"]
        ensure_current(config.get("runtime_revision"))
        capabilities = Catalog(settings, store).system()
        options = (
            capabilities.run_modes if job["kind"] == "run" else capabilities.test_suites
        )
        operation = config["mode"] if job["kind"] == "run" else config["suite"]
        if not next(
            (item.available for item in options if item.id == operation), False
        ):
            raise ValueError(
                "Deze operatie is niet beschikbaar met de huidige serverconfiguratie."
            )
        store.update(job_id, "RUNNING")
        result = (
            execute_run(job, settings, store)
            if job["kind"] == "run"
            else execute_tests(job, settings)
        )
        if store.job(job_id)["status"] != "FAILED":
            store.update(job_id, "COMPLETED", result=result)
    except (Exception, SystemExit) as exc:
        store.update(
            job_id, "FAILED", error=redact(f"{type(exc).__name__}: {exc}")[:1000]
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()

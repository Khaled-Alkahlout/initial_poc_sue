"""One explicitly invoked fixture rewrite smoke test; never executes SQL.

Uses the configured model once, snapshots generation settings, and saves a normal
analysis job. No automatic retry. Use --source-id to reuse a stored diagnosis.
"""

import argparse
import json

from api.config import Settings
from api.services.analysis import execute_analysis, rewrite_source
from api.services.storage import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-id")
    parser.add_argument("--confirm-external-model", action="store_true", required=True)
    args = parser.parse_args()
    settings = Settings()
    store = Store(settings.database_path)
    if args.source_id:
        rewrite_source(store, args.source_id, "top_products")
    job = store.create_job(
        "run",
        {
            "mode": "analysis",
            "query_id": "top_products",
            "condition": "C4_stats",
            "confirm_external_model": True,
            "confirm_sql": False,
            "source_id": args.source_id,
            "rewrite_only": bool(args.source_id),
            "generation_settings": store.generation_settings().model_dump(),
        },
    )
    try:
        result = execute_analysis(job, settings, store)
        if store.job(job["id"])["status"] != "FAILED":
            store.update(job["id"], "COMPLETED", result=result)
        saved = store.job(job["id"])
        attempt = saved["result"]["attempts"][0]
        # No SQL, schema, provider body or private model prose in stdout.
        print(
            json.dumps(
                {
                    "run_id": job["id"],
                    "status": saved["status"],
                    "rewrite_status": (attempt.get("analysis") or {}).get(
                        "rewrite_status"
                    ),
                    "validation_state": attempt["validation_state"],
                    "diagnostics": attempt["diagnostics"],
                },
                indent=2,
            )
        )
    except Exception:
        store.update(
            job["id"], "FAILED", error="Smoke test failed; inspect backend diagnostics."
        )
        raise SystemExit("Smoke test failed; no automatic retry.") from None


if __name__ == "__main__":
    main()

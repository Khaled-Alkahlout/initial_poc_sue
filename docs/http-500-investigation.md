# HTTP 500: mixed API/worker versions

## Exact cause and reproduction

On 3 November 2026, the running API on `127.0.0.1:8000` returned 500 for:

- `GET /api/overview` (the dashboard's failing frontend data request)
- `GET /api/queries?top_k=2`
- `GET /api/queries/top_products`
- `GET /api/runs`
- `GET /api/development/tests`

The same overview request through the Next.js proxy on port 3000 also returned 500. `GET /api/system/status` and `GET /api/settings/ai` returned 200. The model connection check does not read the run catalog, so a working OpenRouter test did not establish that these data endpoints worked.

The live `/openapi.json` exposed the original nine-field `Analysis` model. The repository's model already supported the three additional rewrite fields. The API was a long-running Uvicorn process without reload; worker processes launch fresh Python modules from disk.

The newest completed analysis, `d24f9ee2-6f8f-41c8-9a47-a1704b3f9775`, stored a valid version-2 analysis containing `schema_version`, `rewrite_status`, and `rewrite_explanation`. Its fresh worker could write that result, but the stale API still used a strict version-1 reader with `extra="forbid"`. Every catalog-backed endpoint iterated all stored runs, so one incompatible record broke the entire catalog view.

The exact exception was reproduced by applying the running server's old model contract to the existing persisted record:

```text
ValidationError
attempts.0.analysis.schema_version        extra_forbidden
attempts.0.analysis.rewrite_status        extra_forbidden
attempts.0.analysis.rewrite_explanation   extra_forbidden

overview -> Catalog.overview -> Catalog.queries -> Catalog.runs
         -> Catalog.job_run -> RunDetail.model_validate
```

A fresh process read the same history successfully before any database change. This excluded malformed stored SQL, missing required fields, JSON serialization failure, invalid input, and an OpenRouter outage as the cause of this incident. The original server wrote exceptions to its launch console rather than a persistent application log; the traceback above was reproduced directly, rather than recovered from an old log file.

## Fix

The verified idle backend was restarted on the existing port with the current compatible reader. The existing database was retained; all nine stored runs remained. No SQL, analysis payload, settings or history records were deleted or migrated. All previously failing endpoints then returned 200, and the live OpenAPI contract included the new fields.

To prevent recurrence, the API records a source revision for its Python API/LLM modules. If those files change under the running process, requests return 503 with `runtime_version_mismatch` and an explicit restart instruction. No new job is dispatched. The queued job snapshots the parent's revision; the fresh worker checks it before model calls or database work. Old queued jobs without the optional revision field remain readable. This is deliberately a restart guard, not an automatic process restart or a relaxation of response validation. Frontend-only changes do not trigger it.

Persisted results are still strictly validated. Incompatible results produce a diagnosed `stored_result_incompatible` error without silently dropping runs or erasing invalid records.

## Error behavior and diagnostics

| Situation | Status | Error code |
| --- | --- | --- |
| Invalid request fields or parameters | 400/422 as appropriate | `invalid_input` |
| Changed backend code under running process | 503 | `runtime_version_mismatch` |
| Temporarily locked/unavailable SQLite storage | 503 | `storage_unavailable` |
| Model network outage or upstream temporary failure | 503 | `llm_request_failed` |
| Upstream model rejection/invalid response | 502 | `llm_request_failed` |
| Incompatible stored run | 500 | `stored_result_incompatible` |
| Unexpected application exception | 500 | `internal_error` |

Existing 403 origin controls, 404 missing resources and 409 safety/configuration/concurrency gates retain their behavior. Successful asynchronous job submission is still 202; later generation/validation failures remain visible in the job result. A model visibility test that successfully receives output but fails its content/limit check still returns its structured test result; an upstream transport/provider failure receives an appropriate error status.

Errors carry a generated request reference in JSON and `X-Request-ID`. Server `sue.api` logs contain the request reference, method, route template, exception type, traceback frame file/function/line, and, for persisted validation failures, run ID and failing field locations/types. Provider failures log only safe classifications/status. They do not log exception input, SQL, schema text, credentials, provider bodies, request bodies or traceback locals. The restarted local server captures stderr, including these logs, at `.local/api-errors.log`; stdout/access logs are in `.local/api-stdout.log`. These local files remain ignored by Git.

The frontend distinguishes invalid input, a failed AI request, temporary unavailability and internal errors. It includes the endpoint and request reference. An HTTP 500 no longer tells the user to correct their input.

## Changed files

| File | Change |
| --- | --- |
| `api/app.py` | Error boundary, safe validation responses, request references, runtime guard |
| `api/routes.py` | Distinguish model dependency failures from invalid settings/input |
| `api/services/catalog.py` | Classify stored-result validation errors with run context |
| `api/services/errors.py` | New safe error responses, classifications and exception diagnostics |
| `api/services/runtime.py` | New API/worker source-version checks |
| `api/services/jobs.py` | Check runtime before dispatch and snapshot worker revision |
| `api/worker.py` | Check parent/worker revision before work |
| `frontend/src/lib/api/client.ts` | Actionable status categories, endpoint and request reference |
| `tests/test_api_errors.py` | Mixed-history, exact old-reader failure, logging, dependency and runtime regressions |
| `frontend/src/tests/api-client.test.ts` | Frontend error category/reference regressions |
| `frontend/e2e/api-health.spec.ts` | Actual recovered data endpoints, dashboard and stored workspace |
| `docs/http-500-investigation.md` | Findings, reproduction and verification |

## Verification

- 106 backend tests passed, including old/new history readback without mutation, the exact three-field failure, safe exception logs, 422/500/503 classification and rejection before worker dispatch.
- 39 frontend tests passed; TypeScript, ESLint, Ruff and diff whitespace checks passed.
- Four browser tests passed against the recovered application: AI settings, stored analysis usage, dashboard/catalog/history recovery, and the intercepted SQL rewrite workflow.
- The six checked data/status endpoints all returned 200 on port 8000 with request references after restart. The actual frontend dashboard and top_products workspace rendered without the error panel.
- No paid model generation or PostgreSQL execution was needed for this fix. SQL safety logic, execution confirmation flags, OpenRouter request generation and analysis history remain intact.

Reproduce offline tests from the repository root with `python -m unittest discover -s tests -v`. Frontend commands are `npm test`, `npm run typecheck`, `npm run lint`, and `npx playwright test e2e/api-health.spec.ts e2e/sql-rewrites.spec.ts e2e/ai-settings.spec.ts` from `frontend` with the local API/UI running. After changing backend Python code, restart Uvicorn before checking the UI.

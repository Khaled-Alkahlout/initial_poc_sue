# SQL rewrite investigation and workflow

## Finding from the actual stored run

The local analysis `18e58eac-2abe-4efd-8a2f-cd60357e4647` matches the reported run exactly: HTTP 200, 5,801 input tokens, 2,098 output tokens, `stop` / `end_turn`, 4,979 visible characters and zero reasoning tokens. Its validated nine-field analysis contains `optimized_sql: null`; `proposed_sql` is also null. The static-stage note records that no rewrite was proposed. No candidate reached the safety checker. The workspace reads this same stored `proposed_sql` field.

Another saved top_products analysis (`301eafa1-7680-4b8b-9c90-3b888cd72269`) explicitly attributes null SQL to being unable to identify a useful rewrite "with certainty" without measurements. The old system prompt described a conservative adviser and permitted null SQL without requiring a transformation attempt or a dedicated reason. Its schema required a nullable SQL field but no rewrite status or explanation. This made a completed, schema-valid analysis with only index advice an ordinary success.

The evidence supports an explicit null decision, rather than truncation, static rejection, persistence loss or a frontend field mismatch. Prompt caution is a plausible contributor, not a proven account of the model's internal decision. The exact run did not save a dedicated no-rewrite reason or its original raw provider content, so alternate content elsewhere in that provider response cannot be independently reconstructed. The strict old parser would have rejected unexpected top-level fields rather than quietly extracting them.

The separate legacy experiment path uses a different prompt (including returning the original SQL when no improvement is found), fenced text and an artifact `sql` field. Historical artifacts contain SQL and render through that adapter. They are distinct from the structured Analysis Workspace path.

## Contract and compatibility

New requests use OpenRouter `response_format: json_schema`, `strict: true`, and `provider.require_parameters: true`, after catalog capability checking. See [OpenRouter's structured-output documentation](https://github.com/OpenRouterTeam/docs/blob/main/guides/features/structured-outputs.mdx). Unsupported models fail visibly; no substitute model or repair call is made. The direct Anthropic legacy transport still uses backend schema validation.

`RewriteResponse` requires schema version 2, `optimized_sql` (first property), `rewrite_status`, and a specific `rewrite_explanation`. Status is `candidate`, `no_safe_rewrite`, or `insufficient_context`. Backend validation enforces nonempty SQL exactly when status is candidate. Diagnosis, a defensible rewrite hypothesis, and independent correctness/performance testing are separate responsibilities. No untested performance claim is accepted as a measurement. Index advice remains independent.

Existing field names `problem`, `expected_benefit`, and `validation_recommendations` remain for API compatibility (the equivalents of problem summary, expected impact and validation steps). Existing nine-field analyses load as version 1, without inventing a historical rewrite decision. Compatibility paths are explicit:

| Format | Extraction |
| --- | --- |
| Structured analysis v1/v2 | `optimized_sql`, then Pydantic validation |
| Analysis envelope | Exactly one top-level `analysis` object containing the same v1/v2 contract |
| Legacy artifact v0 | Existing `sql` field, or exactly one SQL/PostgreSQL fence in `text` |
| Explicit `legacy_text_v0` parser | Exactly one SQL/PostgreSQL fence; never guessed from arbitrary prose |

Malformed structured responses never fall back to legacy text parsing. Multiple fences and invalid legacy SQL fields become visible parsing failures. There is no recursive key guessing. Formatting/comments-only copies of the original are retained as rejected candidates rather than labelled improvements. Safety checks still use the existing `proposal_check` and validator. These checks establish admission only, not equivalence. The read-only execution, confirmation flags and existing evaluation algorithm are unchanged.

## Manual action and diagnostics

The Analysis Workspace's **Generate SQL Rewrite** action sends one explicit analysis request with `rewrite_only: true` and the selected stored source ID. The backend verifies the source belongs to the query, reuses its redacted context and bottleneck diagnosis, and includes its prior candidate/outcome. Source analyses are immutable; each new request gets its own history record. Duplicate in-flight analysis requests remain blocked. The existing external-model consent control applies; the action never executes SQL or retries automatically.

The SQL panels show original and proposed SQL with Prism highlighting and copy actions, before the longer diagnosis. No-rewrite, parsing error, static rejection, request failure and awaiting-validation states are distinct. Old analyses explicitly say when a specific rewrite decision was not recorded.

Development response diagnostics record rewrite requested, candidate returned, structured parsing, static admission, rejection classification, SQL storage readback, and a frontend acknowledgement of the rendered stored SQL. Null means unknown or not applicable, never success. The acknowledgement is metadata only and does not transmit SQL. It is an instrumented render acknowledgement, not independent proof that a human saw the SQL. The boolean update is atomic and preserves run completion time.

On parsing failures, the original model text is kept only in `SUE_DATA_DIR/private-model-diagnostics/<run-id>.bin`. Windows uses current-user DPAPI encryption (operator inspection requires `CryptUnprotectData` under that account); POSIX uses a 0700 directory and 0600 files. It is never returned by REST or written to ordinary logs. The UI receives only safe classification and whether preservation succeeded. Operators should retain/delete these files according to their local diagnostic retention policy. Raw provider reasoning is neither requested nor saved. Legacy redacted partial-response fields remain readable for existing history.

## Regression evidence and limits

The new backend tests exercise candidate and justified no-rewrite responses, inconsistent contracts, legacy fields/fences/envelopes, unchanged SQL, static rejection, protected parsing diagnostics, focused context reuse, source ownership, persistence/readback and display acknowledgement. The existing top_products filtered-orders CTE fixture is used as an untested candidate; retaining its SQL is not a speedup claim. Existing validation-state tests cover correctness failures, validation errors and measured improvement without new model requests.

The browser regression intercepts provider generation, then demonstrates top_products with no rewrite, preserved index advice, the manual focused request, SQL comparison, copy availability and render acknowledgement. Frontend tests separately cover parsing/static/request errors and legacy contracts.

Historical `results/validation-20261027-195356.csv` already records the filtered-orders CTE as `EQUIVALENT_NOT_FASTER`. It rejects removal of either DISTINCT, the inclusive date upper bound, omitted status, changed ordering, per-variant aggregate double counting, left-join filter leakage and grouping at variant granularity. These are historical results, not newly measured performance. The prompt explicitly calls out these hazards and preserves UUID casts, parameters, aliases, tenant/date/status filtering, grouping, ordering, LIMIT and NULL semantics. No new PostgreSQL correctness or benchmark execution was performed: the current SQL-enable and test-database confirmation flags are both false.

Validation completed: 100 backend tests, 35 frontend tests, TypeScript, ESLint, Ruff and the intercepted browser workflow. A real provider smoke test was attempted but automatic approval review rejected sending stored context externally with potential provider charges. It was not retried. Consequently, live compliance of the configured model with the new contract remains unverified.

After explicit approval for that external request, reproduce one bounded live fixture check from the repository root:

```powershell
.\.venv\Scripts\python.exe -m scripts.check_rewrite_workflow --source-id 18e58eac-2abe-4efd-8a2f-cd60357e4647 --confirm-external-model
```

The command snapshots current generation settings, uses the configured model once, stores an ordinary analysis run, and prints metadata only. It never runs SQL. A legitimate no-rewrite outcome is a successful contract test, not evidence that optimization is impossible.

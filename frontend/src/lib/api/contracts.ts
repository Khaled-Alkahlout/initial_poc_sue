import { z } from "zod";

export const stageStatus = z.enum([
  "pending",
  "running",
  "passed",
  "failed",
  "warning",
  "inconclusive",
  "skipped",
  "error",
]);
export const outcome = z.enum([
  "accepted",
  "not_faster",
  "mismatch",
  "safety_rejected",
  "inconclusive",
  "error",
  "unavailable",
]);
export const mode = z.enum([
  "historical",
  "replay",
  "mock",
  "live_mock",
  "live",
]);
const lifecycle = z.enum(["PENDING", "RUNNING", "COMPLETED", "FAILED"]);
export const condition = z.enum([
  "C1_query",
  "C2_schema",
  "C3_plan",
  "C4_stats",
]);
export const stageSchema = z.object({
  id: z.string(),
  label: z.string(),
  status: stageStatus,
  note: z.string(),
  duration_ms: z.number().nullable(),
  origin: z.string(),
});
const benchmarkSchema = z.object({
  original_ms: z.number().nullable(),
  proposed_ms: z.number().nullable(),
  original_iqr_ms: z.number().nullable(),
  proposed_iqr_ms: z.number().nullable(),
  speedup: z.number().nullable(),
  reduction_percent: z.number().nullable(),
  repetitions: z.number().nullable(),
  status: stageStatus,
  origin: z.string(),
});
const contextSchema = z.object({
  id: z.string(),
  label: z.string(),
  state: z.enum([
    "available",
    "unavailable",
    "omitted",
    "redacted",
    "truncated",
  ]),
  text: z.string().nullable(),
  note: z.string(),
});
export const attemptSchema = z.object({
  id: z.string(),
  run_id: z.string(),
  query_id: z.string(),
  candidate: z.string(),
  condition: z.string().nullable(),
  repetition: z.number().nullable(),
  model: z.string().nullable(),
  raw_verdict: z.string().nullable(),
  outcome,
  correctness: stageStatus,
  original_sql: z.string().nullable(),
  proposed_sql: z.string().nullable(),
  explanation: z.string().nullable(),
  detail: z.string(),
  parameter_sets: z.number().nullable(),
  failing_parameter_sets: z.number().nullable(),
  input_tokens: z.number().nullable(),
  output_tokens: z.number().nullable(),
  llm_seconds: z.number().nullable(),
  unchanged: z.boolean().nullable(),
  stages: z.array(stageSchema),
  benchmark: benchmarkSchema,
  context: z.array(contextSchema),
  raw_record: z.record(z.string(), z.unknown()),
  origin: z.string(),
});
export const runSummarySchema = z.object({
  id: z.string(),
  title: z.string(),
  mode,
  lifecycle,
  created_at: z.string(),
  completed_at: z.string().nullable(),
  query_ids: z.array(z.string()),
  attempt_count: z.number(),
  accepted_count: z.number(),
  issue_count: z.number(),
  input_tokens: z.number().nullable(),
  output_tokens: z.number().nullable(),
  model_requests: z.number().nullable(),
  source_id: z.string().nullable(),
  error: z.string().nullable(),
});
export const runSchema = runSummarySchema.extend({
  attempts: z.array(attemptSchema),
  stages: z.array(stageSchema),
  selection: z.record(z.string(), z.unknown()).nullable(),
  limitations: z.array(z.string()),
});
export const querySchema = z.object({
  query_id: z.string(),
  sql: z.string().nullable(),
  calls: z.number().nullable(),
  mean_execution_time_ms: z.number().nullable(),
  total_execution_time_ms: z.number().nullable(),
  impact_ms: z.number().nullable(),
  impact_source: z.string().nullable(),
  rank: z.number().nullable(),
  status: z.enum(["eligible", "excluded", "deferred"]),
  selected: z.boolean(),
  reason_codes: z.array(z.string()),
  source: z.string(),
  is_synthetic: z.boolean(),
  window_id: z.string().nullable(),
  dialect: z.string(),
  analyzed: z.boolean(),
  related_run_ids: z.array(z.string()),
  analysis_count: z.number(),
  latest_outcome: outcome.nullable(),
});
export const queriesSchema = z.object({
  queries: z.array(querySchema),
  policy: z.record(z.string(), z.unknown()),
});
export const queryDetailSchema = querySchema.extend({
  runs: z.array(runSummarySchema),
  attempts: z.array(attemptSchema),
});
const conditionStatsSchema = z.object({
  condition: z.string(),
  requests: z.number(),
  independent_queries: z.number(),
  accepted: z.number(),
  rejected: z.number(),
  inconclusive: z.number(),
  unchanged: z.number(),
  input_tokens: z.number().nullable(),
  output_tokens: z.number().nullable(),
});
export const overviewSchema = z.object({
  metrics: z.array(
    z.object({
      id: z.string(),
      label: z.string(),
      value: z.number().nullable(),
      note: z.string(),
      origin: z.string(),
    }),
  ),
  queries: z.array(querySchema),
  recent_runs: z.array(runSummarySchema),
  conditions: z.array(conditionStatsSchema),
  warnings: z.array(z.string()),
});
export const testSchema = z.object({
  id: z.string(),
  name: z.string(),
  component: z.string(),
  purpose: z.string(),
  expected: z.string().nullable(),
  actual: z.string().nullable(),
  status: stageStatus,
  duration_ms: z.number().nullable(),
  error_classification: z.string().nullable(),
  executed_at: z.string().nullable(),
  run_id: z.string().nullable(),
  query_id: z.string().nullable(),
  origin: z.string(),
  detail: z.string(),
  attempt: attemptSchema.nullable(),
  metadata: z.record(z.string(), z.unknown()),
});
export const testsSchema = z.object({
  tests: z.array(testSchema),
  counts: z.record(z.string(), z.number()),
  warnings: z.array(z.string()),
});
export const executionSchema = z.object({
  id: z.string(),
  suite: z.string(),
  lifecycle,
  created_at: z.string(),
  completed_at: z.string().nullable(),
  tests: z.array(testSchema),
  error: z.string().nullable(),
});
const capabilitySchema = z.object({
  id: z.string(),
  label: z.string(),
  available: z.boolean(),
  reason: z.string(),
  executes_sql: z.boolean(),
  external_model: z.boolean(),
});
export const systemSchema = z.object({
  api_status: z.string(),
  database_status: z.string(),
  database_configured: z.boolean(),
  model_configured: z.boolean(),
  dependencies: z.record(z.string(), z.boolean()),
  fixtures: z.number(),
  historical_runs: z.number(),
  historical_evaluations: z.number(),
  filter_available: z.boolean(),
  run_modes: z.array(capabilitySchema),
  test_suites: z.array(capabilitySchema),
  warnings: z.array(z.string()),
  limitations: z.array(z.string()),
});
export const feedbackSchema = z.object({
  id: z.string(),
  target_type: z.enum(["run", "test", "attempt"]),
  target_id: z.string(),
  label: z.enum(["correct", "incorrect", "needs_review"]),
  comment: z.string(),
  reviewer: z.string(),
  created_at: z.string(),
});

export type Stage = z.infer<typeof stageSchema>;
export type Attempt = z.infer<typeof attemptSchema>;
export type Benchmark = z.infer<typeof benchmarkSchema>;
export type RunSummary = z.infer<typeof runSummarySchema>;
export type Run = z.infer<typeof runSchema>;
export type Query = z.infer<typeof querySchema>;
export type QueryDetail = z.infer<typeof queryDetailSchema>;
export type Overview = z.infer<typeof overviewSchema>;
export type TestRecord = z.infer<typeof testSchema>;
export type SystemStatus = z.infer<typeof systemSchema>;
export type Feedback = z.infer<typeof feedbackSchema>;
export type RunInput = {
  mode: "replay" | "mock" | "live_mock" | "live";
  query_id: string;
  condition: z.infer<typeof condition>;
  source_id?: string;
  confirm_sql: boolean;
  confirm_external_model: boolean;
};
export type FeedbackInput = Pick<
  Feedback,
  "target_type" | "target_id" | "label" | "comment" | "reviewer"
>;
export type TestInput = {
  suite: "selection" | "routing" | "mutations";
  query_id: string;
  confirm_sql: boolean;
};

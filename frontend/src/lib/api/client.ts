import { z } from "zod";
import {
  executionSchema,
  feedbackSchema,
  overviewSchema,
  queriesSchema,
  queryDetailSchema,
  runSchema,
  runSummarySchema,
  systemSchema,
  testSchema,
  testsSchema,
  type FeedbackInput,
  type RunInput,
  type TestInput,
  aiSettingsSchema,
  aiTestSchema,
  generationSettingsSchema,
  type GenerationSettings,
} from "./contracts";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
    public requestId?: string,
    public path?: string,
  ) {
    super(message);
  }
}

export async function request<T>(
  path: string,
  schema: z.ZodType<T>,
  options?: RequestInit,
): Promise<T> {
  const origin =
    typeof window === "undefined"
      ? (process.env.API_ORIGIN ?? "http://127.0.0.1:8000")
      : "";
  let response: Response;
  try {
    response = await fetch(`${origin}/api${path}`, {
      ...options,
      cache: "no-store",
      signal: options?.signal ?? AbortSignal.timeout(15000),
      headers: { "Content-Type": "application/json", ...options?.headers },
    });
  } catch {
    throw new ApiError(
      "De Python-API is niet bereikbaar. Controleer of de lokale backend draait.",
      0,
    );
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = z
      .object({
        detail: z.string().optional(),
        error_code: z.string().optional(),
        request_id: z.string().optional(),
      })
      .safeParse(body);
    const info = detail.success ? detail.data : {};
    const reference =
      info.request_id ?? response.headers.get("X-Request-ID") ?? undefined;
    const category =
      info.error_code === "llm_request_failed"
        ? "AI-modelverzoek mislukt."
        : response.status === 400 || response.status === 422
          ? "Ongeldige invoer."
          : response.status === 503
            ? "Backend of afhankelijkheid tijdelijk niet beschikbaar."
            : response.status >= 500
              ? "Interne backendfout."
              : "API-verzoek geweigerd.";
    const message = `${category} ${info.detail ?? `HTTP ${response.status}.`}`;
    throw new ApiError(
      `${message} Endpoint: /api${path.split("?")[0]}.${reference ? ` Referentie: ${reference}.` : ""}`,
      response.status,
      info.error_code,
      reference,
      path,
    );
  }
  const parsed = schema.safeParse(body);
  if (!parsed.success)
    throw new ApiError(
      "De API-response voldoet niet aan het afgesproken contract. Er worden geen vervangende resultaten getoond.",
      502,
    );
  return parsed.data;
}

const id = encodeURIComponent;
export const api = {
  recordRewriteDisplay: (runId: string, sqlDisplayed: boolean) =>
    fetch(`/api/runs/${id(runId)}/rewrite-display`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sql_displayed: sqlDisplayed }),
    }),
  getAISettings: () =>
    request("/settings/ai", aiSettingsSchema, {
      signal: AbortSignal.timeout(30000),
    }),
  saveAISettings: (value: GenerationSettings) =>
    request("/settings/ai", generationSettingsSchema, {
      method: "PUT",
      body: JSON.stringify(value),
      signal: AbortSignal.timeout(30000),
    }),
  resetAISettings: () =>
    request("/settings/ai/reset", generationSettingsSchema, {
      method: "POST",
      signal: AbortSignal.timeout(30000),
    }),
  testAIGeneration: () =>
    request("/settings/ai/test", aiTestSchema, {
      method: "POST",
      body: JSON.stringify({ confirm_external_model: true }),
      signal: AbortSignal.timeout(90000),
    }),
  getOverview: () => request("/overview", overviewSchema),
  getQueries: (topK = 2, excludedIds: string[] = []) =>
    request(
      `/queries?top_k=${topK}${excludedIds.map((value) => `&exclude_query=${id(value)}`).join("")}`,
      queriesSchema,
    ),
  getQuery: (queryId: string) =>
    request(`/queries/${id(queryId)}`, queryDetailSchema),
  getRuns: () => request("/runs", z.array(runSummarySchema)),
  getRun: (runId: string) => request(`/runs/${id(runId)}`, runSchema),
  startRun: (input: RunInput) =>
    request("/runs", runSchema, {
      method: "POST",
      body: JSON.stringify(input),
    }),
  getTests: () => request("/development/tests", testsSchema),
  getTest: (testId: string) =>
    request(`/development/tests/${id(testId)}`, testSchema),
  runTests: (input: TestInput) =>
    request("/development/tests/run", executionSchema, {
      method: "POST",
      body: JSON.stringify(input),
    }),
  getExecution: (jobId: string) =>
    request(`/development/executions/${id(jobId)}`, executionSchema),
  getFeedback: (targetId: string) =>
    request(
      `/development/feedback?target_id=${id(targetId)}`,
      z.array(feedbackSchema),
    ),
  submitFeedback: (input: FeedbackInput) =>
    request("/development/feedback", feedbackSchema, {
      method: "POST",
      body: JSON.stringify(input),
    }),
  getSystem: () => request("/system/status", systemSchema),
};
export const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : "Onbekende fout.";

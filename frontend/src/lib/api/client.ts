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
} from "./contracts";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
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
    const detail = z.object({ detail: z.string() }).safeParse(body);
    throw new ApiError(
      detail.success
        ? detail.data.detail
        : `API-verzoek mislukt (${response.status}). Controleer de invoer.`,
      response.status,
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

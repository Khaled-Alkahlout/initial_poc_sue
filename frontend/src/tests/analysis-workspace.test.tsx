import { test, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AnalysisWorkspace } from "@/features/queries/analysis-workspace";
import { api } from "@/lib/api/client";
import { query, run, system, attempt } from "./fixtures";
import type { ReactNode } from "react";
vi.mock("@/features/runs/run-detail", () => ({
  RunDetail: ({ rewriteAction }: { rewriteAction?: ReactNode }) => (
    <>
      <p>Analyse in workspace</p>
      {rewriteAction}
    </>
  ),
}));

test("AI-analyse vraagt bevestiging, voert geen SQL uit en blijft in de workspace", async () => {
  const user = userEvent.setup();
  const config = system();
  config.run_modes.push({
    id: "analysis",
    label: "AI",
    available: true,
    reason: "Eén request",
    executes_sql: false,
    external_model: true,
  });
  const request = vi
    .spyOn(api, "startRun")
    .mockResolvedValue({ ...run(), mode: "analysis" });
  render(
    <AnalysisWorkspace
      query={{ ...query(), runs: [], attempts: [] }}
      system={config}
    />,
  );
  const button = screen.getByRole("button", { name: "Analyze with AI" });
  expect(button).toBeDisabled();
  await user.click(screen.getByRole("checkbox"));
  await user.click(button);
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      expect.objectContaining({
        mode: "analysis",
        confirm_sql: false,
        confirm_external_model: true,
      }),
    ),
  );
  expect(await screen.findByText("Analyse in workspace")).toBeInTheDocument();
});

test("opgeslagen analyse verschijnt opnieuw bij openen van de workspace", async () => {
  vi.spyOn(api, "getRun").mockResolvedValue({ ...run(), mode: "analysis" });
  render(
    <AnalysisWorkspace
      query={{
        ...query(),
        runs: [],
        attempts: [attempt({ diagnostics: { error_code: "token_limit" } })],
      }}
      system={system()}
    />,
  );
  expect(await screen.findByText("Analyse in workspace")).toBeInTheDocument();
});

test("ontbrekende providerconfiguratie geeft uitleg en geen modelrequest", () => {
  render(
    <AnalysisWorkspace
      query={{ ...query(), runs: [], attempts: [] }}
      system={system()}
    />,
  );
  expect(
    screen.getByRole("button", { name: "Analyze with AI" }),
  ).toBeDisabled();
  expect(
    screen.getByText("OpenRouter nog niet geconfigureerd."),
  ).toBeInTheDocument();
});

test("gerichte rewrite vraagt één nieuw verzoek met de opgeslagen analyse als bron", async () => {
  const user = userEvent.setup();
  const config = system();
  config.run_modes.push({
    id: "analysis",
    label: "AI",
    available: true,
    reason: "",
    executes_sql: false,
    external_model: true,
  });
  const saved = {
    ...run(),
    mode: "analysis" as const,
    lifecycle: "COMPLETED" as const,
  };
  vi.spyOn(api, "getRun").mockResolvedValue(saved);
  const start = vi
    .spyOn(api, "startRun")
    .mockResolvedValue({ ...saved, id: "focused", lifecycle: "PENDING" });
  render(
    <AnalysisWorkspace
      query={{
        ...query(),
        runs: [],
        attempts: [
          attempt({ diagnostics: { error_code: "schema_validation_failed" } }),
        ],
      }}
      system={config}
    />,
  );
  const button = await screen.findByRole("button", {
    name: "Generate SQL Rewrite",
  });
  expect(button).toBeDisabled();
  await user.click(screen.getByRole("checkbox"));
  await user.click(button);
  await waitFor(() => expect(start).toHaveBeenCalledTimes(1));
  expect(start).toHaveBeenCalledWith(
    expect.objectContaining({
      mode: "analysis",
      rewrite_only: true,
      source_id: saved.id,
      query_id: "top_products",
      confirm_sql: false,
    }),
  );
});

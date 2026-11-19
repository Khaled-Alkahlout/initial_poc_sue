import { test, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AnalysisWorkspace } from "@/features/queries/analysis-workspace";
import { api } from "@/lib/api/client";
import { query, run, system, attempt } from "./fixtures";
vi.mock("@/features/runs/run-detail", () => ({
  RunDetail: () => <p>Analyse in workspace</p>,
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
  const button = screen.getByRole("button", { name: "Analyse starten" });
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

test("volledige run vereist bevestiging voor zowel de database als het model", async () => {
  const user = userEvent.setup();
  const config = system();
  config.run_modes.push(
    {
      id: "analysis",
      label: "AI",
      available: true,
      reason: "",
      executes_sql: false,
      external_model: true,
    },
    {
      id: "live",
      label: "AI en validatie",
      available: true,
      reason: "",
      executes_sql: true,
      external_model: true,
    },
  );
  config.run_modes = config.run_modes.map((mode) =>
    mode.id === "validate" ? { ...mode, available: true } : mode,
  );
  const start = vi
    .spyOn(api, "startRun")
    .mockResolvedValue({ ...run(), mode: "live" });
  render(
    <AnalysisWorkspace
      query={{ ...query(), runs: [], attempts: [] }}
      system={config}
    />,
  );
  await user.selectOptions(
    screen.getByRole("combobox", { name: "Na de analyse" }),
    "test",
  );
  await user.click(
    screen.getByRole("checkbox", { name: /correctheidscontrole en benchmark/ }),
  );
  const submit = screen.getByRole("button", { name: "Analyse starten" });
  expect(submit).toBeDisabled();
  await user.click(screen.getByRole("checkbox", { name: /extern AI-request/ }));
  await user.click(submit);
  expect(start).toHaveBeenCalledExactlyOnceWith(
    expect.objectContaining({
      mode: "live",
      condition: "C4_stats",
      confirm_sql: true,
      confirm_external_model: true,
    }),
  );
});

test("schema kan worden meegestuurd terwijl het voorstel alleen wordt opgeslagen", async () => {
  const user = userEvent.setup();
  const config = system();
  config.run_modes.push({
    id: "analysis",
    label: "SQL-analyse",
    available: true,
    reason: "",
    executes_sql: false,
    external_model: true,
  });
  config.run_modes = config.run_modes.map((mode) =>
    mode.id === "validate" ? { ...mode, available: true } : mode,
  );
  const request = vi
    .spyOn(api, "startRun")
    .mockResolvedValue({ ...run(), mode: "analysis" });
  render(
    <AnalysisWorkspace
      query={{ ...query(), runs: [], attempts: [] }}
      system={config}
    />,
  );
  await user.selectOptions(
    screen.getByRole("combobox", { name: "Context voor het model" }),
    "C2_schema",
  );
  expect(screen.getByRole("combobox", { name: "Na de analyse" })).toHaveValue(
    "save",
  );
  await user.click(screen.getByRole("checkbox", { name: /extern AI-request/ }));
  expect(
    screen.getByRole("button", { name: "Analyse starten" }),
  ).toBeDisabled();
  await user.click(
    screen.getByRole("checkbox", { name: /gekozen metadata op/ }),
  );
  await user.click(screen.getByRole("button", { name: "Analyse starten" }));
  expect(request).toHaveBeenCalledExactlyOnceWith(
    expect.objectContaining({
      mode: "analysis",
      condition: "C2_schema",
      confirm_sql: true,
      confirm_external_model: true,
    }),
  );
});

test("ontbrekende providerconfiguratie geeft uitleg en geen modelrequest", () => {
  render(
    <AnalysisWorkspace
      query={{ ...query(), runs: [], attempts: [] }}
      system={system()}
    />,
  );
  expect(
    screen.getByRole("button", { name: "Analyse starten" }),
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
    name: "Opnieuw analyseren met eerdere uitkomst",
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

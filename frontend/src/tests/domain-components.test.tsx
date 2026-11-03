import { describe, expect, test, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryTable } from "@/components/queries/query-table";
import { QueryDecision } from "@/components/queries/query-decision";
import { SqlComparison } from "@/components/queries/sql-viewer";
import { PipelineVisualizer } from "@/components/pipeline/pipeline-visualizer";
import {
  ContextViewer,
  PerformanceComparison,
} from "@/components/evaluation/attempt-panels";
import { TestMatrix } from "@/components/evaluation/test-matrix";
import { EmptyState, ErrorState } from "@/components/shared/states";
import { ArchitectureView } from "@/features/development/architecture";
import { attempt, query, stage, system, testRecord } from "./fixtures";

describe("Queryweergave", () => {
  test("ontbrekende SQL blijft zichtbaar als ontbrekend", () => {
    render(
      <QueryTable
        queries={[
          query({
            sql: null,
            selected: false,
            status: "excluded",
            reason_codes: ["MISSING_SQL"],
          }),
        ]}
      />,
    );
    expect(screen.getByText("SQL ontbreekt")).toBeInTheDocument();
    expect(
      screen.getByText("Uitgesloten", { selector: "span" }),
    ).toBeInTheDocument();
  });
  test("toont backendrang en filtert geselecteerde queries", async () => {
    const user = userEvent.setup();
    render(
      <QueryTable
        queries={[
          query(),
          query({
            query_id: "slow",
            calls: 1,
            mean_execution_time_ms: 2000,
            impact_ms: 2000,
            rank: 2,
            selected: false,
            reason_codes: ["PROVIDED_TOTAL", "OUTSIDE_TOP_K"],
          }),
        ]}
      />,
    );
    const rows = screen.getAllByRole("row");
    expect(
      within(rows[1]).getByRole("link", { name: "top_products" }),
    ).toBeInTheDocument();
    expect(screen.getByText("500.000")).toBeInTheDocument();
    await user.selectOptions(
      screen.getByLabelText("Filter op selectiestatus"),
      "selected",
    );
    expect(
      screen.queryByRole("link", { name: "slow" }),
    ).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Zoek query of SQL"), "unknown");
    expect(screen.getByText("Geen query's gevonden")).toBeInTheDocument();
  });
  test("verklaart backendredenen zonder nieuwe regels te verzinnen", () => {
    render(
      <QueryDecision
        query={query({ selected: false, reason_codes: ["OUTSIDE_TOP_K"] })}
      />,
    );
    expect(
      screen.getByText("Geschikt, maar buiten het ingestelde querybudget."),
    ).toBeInTheDocument();
    expect(screen.getByText("OUTSIDE_TOP_K")).toBeInTheDocument();
  });
});
describe("SQL en fases", () => {
  test("SQL-vergelijking bewaart opmaak, escaped markup en kopieert de originele tekst", async () => {
    const user = userEvent.setup();
    const copy = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    const sql = "SELECT '<script>alert(1)</script>'\nFROM orders;";
    const { container } = render(
      <SqlComparison original={sql} proposed="SELECT 2" />,
    );
    expect(
      screen.getByRole("region", { name: "Original SQL" }),
    ).toBeInTheDocument();
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("pre")?.textContent).toBe(sql);
    await user.click(
      screen.getByRole("button", { name: "Kopieer SQL: Original SQL" }),
    );
    expect(copy).toHaveBeenCalledWith(sql);
  });
  test("mislukt, onbeslist en niet uitgevoerd blijven aparte statussen", async () => {
    const user = userEvent.setup();
    render(
      <PipelineVisualizer
        stages={[
          stage({ id: "static", label: "Statisch", status: "failed" }),
          stage({ status: "inconclusive", note: "Tie niet bewezen." }),
          stage({ id: "benchmark", label: "Benchmark", status: "skipped" }),
        ]}
      />,
    );
    expect(screen.getByText("Mislukt")).toBeVisible();
    expect(screen.getByText("Onbeslist")).toBeVisible();
    expect(screen.getByText("Niet uitgevoerd")).toBeVisible();
    await user.click(screen.getByText("Correctheid"));
    expect(screen.getByText(/Tie niet bewezen/)).toBeVisible();
  });
  test("schematische pipeline claimt geen actuele successen", () => {
    render(<PipelineVisualizer />);
    expect(screen.queryByText("Geslaagd")).not.toBeInTheDocument();
    expect(screen.getByText("LLM-generatie")).toBeInTheDocument();
  });
  test("claimt geen speedup na onvoldoende correctheidsbewijs", () => {
    render(
      <PerformanceComparison
        attempt={attempt({ correctness: "inconclusive" })}
      />,
    );
    expect(
      screen.getByText("Geen onderbouwde performanceconclusie"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Gemeten speedup")).not.toBeInTheDocument();
  });
  test("toont gemeten benchmarkdata met herkomst", () => {
    render(<PerformanceComparison attempt={attempt()} />);
    expect(screen.getByText("5×")).toBeInTheDocument();
    expect(screen.getByText("Historisch")).toBeInTheDocument();
  });
  test("ontbrekende context wordt niet opgevuld", () => {
    render(<ContextViewer attempt={attempt()} />);
    expect(screen.getByText("Niet beschikbaar")).toBeInTheDocument();
  });
});
describe("Development en fouttoestanden", () => {
  test("matrix toont ontbrekende verwachtingen en filterbare technische fouten", async () => {
    const user = userEvent.setup();
    render(
      <TestMatrix
        tests={[
          testRecord(),
          testRecord({
            id: "error",
            name: "Uitvoeringsfout",
            status: "error",
            actual: "EXEC_ERROR",
          }),
        ]}
      />,
    );
    expect(screen.getAllByText("Niet gedefinieerd")).toHaveLength(2);
    await user.selectOptions(
      screen.getByLabelText("Filter op teststatus"),
      "error",
    );
    expect(
      screen.queryByRole("link", { name: "Voorbeeldtest" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("EXEC_ERROR")).toBeInTheDocument();
  });
  test("configuratie wordt niet als operationele gereedheid weergegeven", () => {
    render(
      <ArchitectureView
        system={{
          ...system(),
          database_configured: true,
          model_configured: true,
        }}
      />,
    );
    expect(screen.getAllByText("Niet getest")).toHaveLength(2);
    expect(
      screen.getByText("Configuratie aanwezig; geen verbinding geopend"),
    ).toBeInTheDocument();
  });
  test("lege en mislukte verzoeken hebben expliciete toestanden", async () => {
    const user = userEvent.setup();
    const retry = vi.fn();
    render(
      <>
        <EmptyState />
        <ErrorState message="Backend offline" retry={retry} />
      </>,
    );
    expect(screen.getByText("Geen gegevens beschikbaar")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Backend offline");
    await user.click(screen.getByRole("button", { name: "Opnieuw proberen" }));
    expect(retry).toHaveBeenCalledOnce();
  });
});

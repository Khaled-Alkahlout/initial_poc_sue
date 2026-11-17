import type { AnchorHTMLAttributes } from "react";
import { describe, expect, test, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api } from "@/lib/api/client";
import { FeedbackForm } from "@/components/evaluation/feedback-form";
import { OutcomeBadge } from "@/components/shared/status";
import { AppShell } from "@/components/layout/app-shell";
import { StartRun } from "@/features/runs/start-run";
import { RunDetail } from "@/features/runs/run-detail";
import { attempt, query, run, system } from "./fixtures";

const { push, refresh } = vi.hoisted(() => ({
  push: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock("next/navigation", () => ({
  usePathname: () => "/queries",
  useRouter: () => ({ push, refresh }),
}));
vi.mock("next/link", () => ({
  default: (props: AnchorHTMLAttributes<HTMLAnchorElement>) => <a {...props} />,
}));

const availableAnalysis = {
  id: "analysis",
  label: "AI-analyse zonder database",
  available: true,
  reason: "OpenRouter is geconfigureerd.",
  executes_sql: false,
  external_model: true,
};

describe("review en navigatie", () => {
  test("handmatige feedback verandert de technische conclusie niet", async () => {
    const user = userEvent.setup();
    const feedback = {
      id: "feedback",
      target_type: "run" as const,
      target_id: "test-run",
      label: "incorrect" as const,
      comment: "Semantiek nader onderzoeken.",
      reviewer: "IN",
      created_at: "2026-11-02T12:00:00Z",
    };
    vi.spyOn(api, "getFeedback")
      .mockResolvedValueOnce([])
      .mockResolvedValue([feedback]);
    const submit = vi.spyOn(api, "submitFeedback").mockResolvedValue(feedback);
    render(
      <>
        <OutcomeBadge outcome="accepted" />
        <FeedbackForm targetId="test-run" targetType="run" />
      </>,
    );
    await user.selectOptions(screen.getByLabelText("Reviewlabel"), "incorrect");
    await user.type(
      screen.getByLabelText("Toelichting · optioneel"),
      feedback.comment,
    );
    await user.click(screen.getByRole("button", { name: "Review opslaan" }));
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(
        "technische uitslag blijft ongewijzigd",
      ),
    );
    expect(submit).toHaveBeenCalledWith(
      expect.objectContaining({ target_id: "test-run", label: "incorrect" }),
    );
    expect(screen.getByText("Geaccepteerd binnen test")).toBeInTheDocument();
    expect(
      await screen.findByText("Incorrect", { selector: "span" }),
    ).toBeInTheDocument();
  });
  test("een request zonder benchmark kan een handmatige review krijgen", async () => {
    const user = userEvent.setup();
    const latest = {
      ...run(),
      mode: "analysis" as const,
      attempts: [
        attempt({
          correctness: "skipped",
          proposed_sql: null,
          outcome: "inconclusive",
          benchmark: {
            ...attempt().benchmark,
            status: "skipped",
            original_ms: null,
            proposed_ms: null,
          },
        }),
      ],
    };
    const feedback = {
      id: "feedback",
      target_type: "run" as const,
      target_id: latest.id,
      label: "needs_review" as const,
      comment: "Het antwoord vraagt om extra context.",
      reviewer: "",
      created_at: "2026-11-02T12:00:00Z",
    };
    vi.spyOn(api, "getRun").mockResolvedValue(latest);
    vi.spyOn(api, "getFeedback")
      .mockResolvedValueOnce([])
      .mockResolvedValue([feedback]);
    const submit = vi.spyOn(api, "submitFeedback").mockResolvedValue(feedback);
    render(<RunDetail initial={latest} system={system()} inline />);

    expect(
      screen.getByRole("heading", { name: "Request beoordelen" }),
    ).toBeVisible();
    expect(
      screen.getByText(/Geen vergelijkbare prestatiemeting beschikbaar/),
    ).toBeVisible();
    await user.type(
      screen.getByLabelText("Toelichting · optioneel"),
      feedback.comment,
    );
    await user.click(screen.getByRole("button", { name: "Review opslaan" }));
    expect(
      await screen.findByText(feedback.comment, { exact: true }),
    ).toBeVisible();
    expect(submit).toHaveBeenCalledWith(
      expect.objectContaining({ target_id: latest.id, target_type: "run" }),
    );
    expect(screen.getByText("Not benchmarked")).toBeVisible();
  });
  test("centrale navigatie scheidt POC van Development en ondersteunt themawisseling", async () => {
    const user = userEvent.setup();
    render(
      <AppShell>
        <h1>Querypagina</h1>
      </AppShell>,
    );
    expect(
      screen.getByRole("link", { name: "Query Explorer" }),
    ).toHaveAttribute("aria-current", "page");
    expect(
      screen.getByRole("link", { name: "Tests & evaluatie" }),
    ).toHaveAttribute("href", "/development");
    await user.click(screen.getByLabelText("Wissel licht en donker thema"));
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
  test("Live POC start beide stappen na bevestiging voor model en database", async () => {
    const user = userEvent.setup();
    const config = system();
    config.run_modes.push(availableAnalysis);
    config.run_modes = config.run_modes.map((mode) =>
      mode.id === "live"
        ? { ...mode, available: true, reason: "Testdatabase geconfigureerd." }
        : mode,
    );
    const start = vi
      .spyOn(api, "startRun")
      .mockResolvedValue({ ...run(), mode: "live" });
    render(<StartRun queries={[query()]} system={config} />);
    await user.click(screen.getByRole("button", { name: "POC starten" }));
    expect(screen.getByText("Live POC", { exact: true })).toBeVisible();
    expect(screen.getAllByRole("combobox")).toEqual([
      screen.getByRole("combobox", { name: "Querycase" }),
    ]);
    expect(
      screen.getByRole("button", { name: "Live POC starten" }),
    ).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: /AI-kosten/ }));
    expect(
      screen.getByRole("button", { name: "Live POC starten" }),
    ).toBeDisabled();
    await user.click(
      screen.getByRole("checkbox", { name: /read-only correctheidscontrole/ }),
    );
    await user.click(screen.getByRole("button", { name: "Live POC starten" }));
    await waitFor(() =>
      expect(start).toHaveBeenCalledWith(
        expect.objectContaining({
          mode: "live",
          query_id: "top_products",
          condition: "C1_query",
          confirm_sql: true,
          confirm_external_model: true,
        }),
      ),
    );
    expect(push).toHaveBeenCalledWith("/runs/test-run");
  });
  test("POC uitvoeren start AI-analyse na kostenbevestiging als de database niet is geconfigureerd", async () => {
    const user = userEvent.setup();
    const config = system();
    const reason = "SUE_DATABASE_URL ontbreekt op de server.";
    config.run_modes = config.run_modes.map((mode) =>
      mode.id === "live" ? { ...mode, reason } : mode,
    );
    config.run_modes.push(availableAnalysis);
    const start = vi
      .spyOn(api, "startRun")
      .mockResolvedValue({ ...run(), mode: "analysis" });
    render(<StartRun queries={[query()]} system={config} />);
    await user.click(screen.getByRole("button", { name: "POC starten" }));
    expect(screen.getByText(reason, { exact: false })).toBeVisible();
    expect(screen.getByText(/Correctheid en Benchmark vereisen/)).toBeVisible();
    expect(screen.getAllByRole("checkbox")).toHaveLength(1);
    const submit = screen.getByRole("button", { name: "AI-analyse starten" });
    expect(submit).toBeDisabled();
    await user.click(submit);
    expect(start).not.toHaveBeenCalled();
    await user.click(screen.getByRole("checkbox", { name: /AI-kosten/ }));
    await user.click(submit);
    expect(start).toHaveBeenCalledWith({
      mode: "analysis",
      query_id: "top_products",
      condition: "C1_query",
      confirm_sql: false,
      confirm_external_model: true,
    });
    expect(push).toHaveBeenCalledWith("/runs/test-run");
  });
  test("POC uitvoeren toont de reden en blokkeert starten als AI-analyse niet beschikbaar is", async () => {
    const user = userEvent.setup();
    const config = system();
    const reason = "OpenRouter is nog niet geconfigureerd.";
    config.run_modes.push({ ...availableAnalysis, available: false, reason });
    const start = vi.spyOn(api, "startRun");
    render(<StartRun queries={[query()]} system={config} />);
    await user.click(screen.getByRole("button", { name: "POC starten" }));
    expect(screen.getByText(reason)).toBeVisible();
    expect(screen.getByRole("checkbox", { name: /AI-kosten/ })).toBeDisabled();
    const submit = screen.getByRole("button", { name: "AI-analyse starten" });
    expect(submit).toBeDisabled();
    await user.click(submit);
    expect(start).not.toHaveBeenCalled();
  });
});

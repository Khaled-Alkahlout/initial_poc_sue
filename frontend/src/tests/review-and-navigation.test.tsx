import type { AnchorHTMLAttributes } from "react";
import { describe, expect, test, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { api } from "@/lib/api/client";
import { FeedbackForm } from "@/components/evaluation/feedback-form";
import { OutcomeBadge } from "@/components/shared/status";
import { AppShell } from "@/components/layout/app-shell";
import { StartRun } from "@/features/runs/start-run";
import { query, run, system } from "./fixtures";

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
  test("demo start expliciet als replay en navigeert naar de nieuwe run", async () => {
    const user = userEvent.setup();
    const start = vi
      .spyOn(api, "startRun")
      .mockResolvedValue({ ...run(), mode: "replay" });
    render(<StartRun queries={[query()]} system={system()} />);
    await user.click(screen.getByRole("button", { name: "Demo starten" }));
    expect(screen.getByRole("option", { name: /Live POC/ })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Replay starten" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/runs/test-run"));
    expect(start).toHaveBeenCalledWith(
      expect.objectContaining({
        mode: "replay",
        confirm_sql: false,
        confirm_external_model: false,
      }),
    );
  });
});

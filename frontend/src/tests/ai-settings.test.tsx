import { expect, test, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AISettingsPage } from "@/features/settings/ai-settings";
import { AIUsage } from "@/components/evaluation/ai-usage";
import { api } from "@/lib/api/client";
import type { AISettings } from "@/lib/api/contracts";
import { attempt } from "./fixtures";

const initial: AISettings = {
  provider: "openrouter",
  model: "test-model",
  key_configured: true,
  llm_enabled: true,
  settings: {
    max_output_tokens: 4096,
    reasoning_effort: "low",
    temperature: null,
  },
  defaults: {
    max_output_tokens: 4096,
    reasoning_effort: "low",
    temperature: null,
  },
  capabilities: {
    reasoning_efforts: ["disabled", "low", "medium", "high"],
    temperature_supported: false,
    max_output_tokens: 16384,
    provider_default_supported: true,
    max_tokens_supported: true,
  },
  capabilities_error: null,
  precedence: "Opgeslagen > omgeving",
  sql_enabled: false,
  test_database_confirmed: false,
};

test("instellingen wijzigen en opslaan zonder databasebevoegdheden", async () => {
  const user = userEvent.setup();
  const save = vi.spyOn(api, "saveAISettings").mockResolvedValue({
    ...initial.settings,
    max_output_tokens: 8192,
    reasoning_effort: "high",
  });
  render(<AISettingsPage initial={initial} />);
  await user.selectOptions(
    screen.getByLabelText("Maximum output tokens"),
    "8192",
  );
  await user.selectOptions(screen.getByLabelText("Reasoning effort"), "high");
  await user.click(
    screen.getByRole("button", { name: "Instellingen opslaan" }),
  );
  await waitFor(() =>
    expect(save).toHaveBeenCalledWith({
      max_output_tokens: 8192,
      reasoning_effort: "high",
      temperature: null,
    }),
  );
  expect(screen.getByRole("status")).toHaveTextContent(
    "Instellingen opgeslagen",
  );
  expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
});

test("provider-default en reset zijn functionele opties", async () => {
  const user = userEvent.setup();
  vi.spyOn(api, "resetAISettings").mockResolvedValue(initial.defaults);
  render(<AISettingsPage initial={initial} />);
  await user.selectOptions(
    screen.getByLabelText("Maximum output tokens"),
    "provider",
  );
  await user.click(
    screen.getByRole("button", { name: "Standaarden herstellen" }),
  );
  await waitFor(() =>
    expect(screen.getByLabelText("Maximum output tokens")).toHaveValue("4096"),
  );
  expect(api.resetAISettings).toHaveBeenCalledOnce();
});

test("kleine verbindingstest vereist kostenbevestiging", async () => {
  const user = userEvent.setup();
  vi.spyOn(api, "testAIGeneration").mockResolvedValue({
    success: true,
    message: "OK ontvangen",
    diagnostics: {
      input_tokens: 10,
      output_tokens: 2,
      reasoning_tokens: 0,
      finish_reason: "stop",
      seconds: 0.5,
    },
    test_settings: {
      max_output_tokens: 512,
      reasoning_effort: "disabled",
      temperature: null,
    },
  });
  render(<AISettingsPage initial={initial} />);
  const button = screen.getByRole("button", { name: "Test AI connection" });
  expect(button).toBeDisabled();
  await user.click(screen.getByRole("checkbox"));
  await user.click(button);
  expect(await screen.findByText("OK ontvangen")).toBeInTheDocument();
  expect(screen.getByText("10 / 2 / 0")).toBeInTheDocument();
});

test("afgekapt antwoord toont waarschuwing en echte reasoningmetadata", () => {
  render(
    <AIUsage
      attempt={attempt({
        outcome: "error",
        correctness: "skipped",
        diagnostics: {
          error_code: "token_limit",
          finish_reason: "length",
          reasoning_tokens: 496,
          configured_max_output_tokens: 512,
        },
        partial_response: '{"problem":',
      })}
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Response reached the configured output token limit",
  );
  expect(screen.getByText("496")).toBeInTheDocument();
  expect(screen.getByText("length")).toBeInTheDocument();
});

import { expect, test } from "vitest";
import { dateTime } from "@/lib/formatters";
test("historische kloktijd krijgt geen verzonnen tijdzone", () => {
  expect(dateTime("2026-10-27T19:00:00")).toContain("19:00");
  expect(dateTime("2026-10-27T19:00:00")).toContain("tijdzone onbekend");
});
test("UTC-timestamps worden voor Amsterdam getoond", () => {
  expect(dateTime("2026-11-02T12:00:00Z")).toContain("13:00");
  expect(dateTime(null)).toBe("Niet vastgelegd");
});

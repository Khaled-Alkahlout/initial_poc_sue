export const count = (value: number | null | undefined) =>
  value == null
    ? "—"
    : new Intl.NumberFormat("nl-NL", { maximumFractionDigits: 1 }).format(
        value,
      );
export const milliseconds = (value: number | null | undefined) =>
  value == null ? "Niet beschikbaar" : `${count(value)} ms`;
export function dateTime(value: string | null | undefined) {
  if (!value || Number.isNaN(new Date(value).getTime()))
    return "Niet vastgelegd";
  if (!/(?:Z|[+-]\d{2}:\d{2})$/i.test(value)) {
    return `${new Intl.DateTimeFormat("nl-NL", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }).format(new Date(`${value}Z`))} · tijdzone onbekend`;
  }
  return new Intl.DateTimeFormat("nl-NL", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Europe/Amsterdam",
  }).format(new Date(value));
}
export const conditionLabels: Record<string, string> = {
  C1_query: "C1 · Alleen query",
  C2_schema: "C2 · Query + schema",
  C3_plan: "C3 · Met execution plan",
  C4_stats: "C4 · Met statistieken",
};
export const sourceLabels: Record<string, string> = {
  historical: "Historisch",
  replay: "Replay",
  mock: "Offline mock",
  live_mock: "Testdatabase · mock",
  live: "Live POC",
  synthetic: "Gesimuleerd",
  current: "Nieuwe uitvoering",
  measured: "Testmeting",
  fixtures: "SQL-fixtures",
};
export const reasonLabels: Record<string, string> = {
  PROVIDED_TOTAL: "Aangeleverde totale uitvoeringstijd bepaalt de impact.",
  DERIVED_TOTAL:
    "Impact afgeleid uit calls × gemiddelde duur in hetzelfde meetvenster.",
  OUTSIDE_TOP_K: "Geschikt, maar buiten het ingestelde querybudget.",
  MISSING_SQL: "SQL ontbreekt.",
  INVALID_SQL: "SQL kon niet worden geparsed.",
  UNSUPPORTED_STATEMENT: "Statement valt buiten de SELECT-scope.",
  MULTIPLE_STATEMENTS: "Meerdere statements zijn uitgesloten.",
  EXCLUDED_QUERY_ID: "Query-ID uitgesloten door het filterbeleid.",
  EXCLUDED_SCHEMA: "Schema uitgesloten door het filterbeleid.",
  EXCLUDED_TABLE: "Tabel uitgesloten door het filterbeleid.",
  MISSING_CALLS: "Uitvoeringsfrequentie ontbreekt.",
  MISSING_MEAN_EXECUTION_TIME_MS: "Gemiddelde uitvoeringstijd ontbreekt.",
  MISSING_TOTAL_EXECUTION_TIME_MS: "Geen bruikbare totale uitvoeringstijd.",
  MISSING_MEASUREMENT_WINDOW:
    "Gezamenlijk meetvenster ontbreekt; impact niet afgeleid.",
  INVALID_CALLS: "Ongeldige uitvoeringsfrequentie.",
  INVALID_MEAN_EXECUTION_TIME_MS: "Ongeldige gemiddelde duur.",
  INVALID_TOTAL_EXECUTION_TIME_MS: "Ongeldige totale duur.",
  DUPLICATE_QUERY_ID: "Dubbel record: niet opnieuw geselecteerd of opgeteld.",
  CONFLICTING_QUERY_ID: "Verschillende SQL onder dezelfde ID; uitgesloten.",
  NO_EXECUTIONS: "Geen uitvoeringen geregistreerd.",
  INVALID_DERIVED_TOTAL: "Afgeleide impact is ongeldig.",
  MISSING_QUERY_ID: "Query-ID ontbreekt.",
  UNSUPPORTED_DIALECT: "Dit SQL-dialect wordt nog niet ondersteund.",
};

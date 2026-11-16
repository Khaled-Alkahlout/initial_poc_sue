import { expect, test, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SqlComparison, SqlViewer } from "@/components/queries/sql-viewer";
import { formatSql, highlightSqlLines, sqlPreview } from "@/lib/sql";

test("formats joins and nested queries and preserves PostgreSQL parameters, comments and identifiers", () => {
  const sql =
    "SELECT u.id, (SELECT count(*) FROM logs WHERE logs.user_id = u.id) AS seen FROM users u JOIN orders o ON o.user_id = u.id JOIN tickets t ON t.id = o.ticket_id WHERE u.tenant = %(tenant_id)s AND o.id = $1 AND t.name = :name AND u.status = 'x  y' /* original\n    indentation */ ORDER BY \"MixedCase\";";
  const formatted = formatSql(sql);
  expect(formatted.split("\n").length).toBeGreaterThan(10);
  expect(formatted).toMatch(/\n +SELECT[\s\S]+\nFROM/);
  expect(formatted).toMatch(/\n +JOIN orders/);
  expect(formatted).toMatch(/\n +JOIN tickets/);
  for (const literal of [
    "%(tenant_id)s",
    "$1",
    ":name",
    "'x  y'",
    '"MixedCase"',
    "/* original\n    indentation */",
  ]) {
    expect(formatted).toContain(literal);
  }
});

test("preserves whitespace-sensitive PostgreSQL strings and highlights multiline comments", () => {
  const adjacent = "SELECT 'first'\n'second';";
  expect(formatSql(adjacent)).toBe(adjacent);
  const nestedComment = "/* note /* inner */\n    keep spacing */ SELECT 1;";
  expect(formatSql(nestedComment)).toBe(nestedComment);
  const dollar = "$tag$quoted -- not a comment\n  second line$tag$";
  const sql = formatSql(
    "SELECT " +
      dollar +
      ', "column" FROM users; /* comment\n  still comment */',
  );
  expect(sql).toContain(dollar);
  const tokens = highlightSqlLines(sql).flat();
  expect(tokens).toContainEqual({
    kind: "string",
    text: "$tag$quoted -- not a comment",
  });
  expect(tokens).toContainEqual({ kind: "identifier", text: '"column"' });
  expect(tokens).toContainEqual({
    kind: "comment",
    text: "  still comment */",
  });
});

test("retains long and unparseable identifiers and renders a short multiline preview", () => {
  const identifier = "very_long_".repeat(25) + "column";
  const sql = "SELECT " + identifier + ", other, final FROM records";
  render(<SqlViewer sql={sql} />);
  expect(
    screen.getByRole("region", { name: "SQL" }).querySelector("code"),
  ).toHaveTextContent(identifier);
  expect(sqlPreview("-- owner: team\n" + sql)).toMatch(/^SELECT\n +very_long_/);
  expect(sqlPreview(sql).split("\n")).toHaveLength(4);
  const unparseable = "SELECT 'unfinished";
  expect(formatSql(unparseable)).toBe(unparseable);
});

test("places original above optimized SQL, diffs actual code and copies the exact backend SQL", async () => {
  const user = userEvent.setup();
  const copy = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
  const original = "SELECT id FROM users WHERE id = $1;";
  const proposed = "SELECT id FROM users WHERE id = $1 AND active = true;";
  render(<SqlComparison original={original} proposed={proposed} />);
  const regions = within(
    screen.getByRole("region", { name: "Query Optimization Comparison" }),
  ).getAllByRole("region");
  expect(regions.map((region) => region.getAttribute("aria-label"))).toEqual([
    "Original SQL Query",
    "Optimized SQL Query",
  ]);
  await user.click(
    within(regions[1]).getByRole("button", {
      name: "Kopieer SQL: Optimized SQL Query",
    }),
  );
  expect(copy).toHaveBeenCalledWith(proposed);
  expect(within(regions[1]).getByRole("status")).toHaveTextContent(
    "Gekopieerd",
  );
  await user.click(screen.getByRole("button", { name: "SQL-diff" }));
  expect(
    [...document.querySelectorAll(".diff-line.diff-added")].some((row) =>
      row.textContent?.includes("AND active = true"),
    ),
  ).toBe(true);
  expect(screen.getByRole("button", { name: "SQL-diff" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await user.click(screen.getByRole("button", { name: /^SQL$/ }));
  expect(
    screen.getByRole("region", { name: "Original SQL Query" }),
  ).toBeVisible();
});

test("removals and additions identify actual replacements", async () => {
  render(
    <SqlComparison
      original="SELECT name FROM customers"
      proposed="SELECT name FROM clients"
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "SQL-diff" }));
  expect(document.querySelector(".diff-line.diff-removed")).toHaveTextContent(
    "customers",
  );
  expect(document.querySelector(".diff-line.diff-added")).toHaveTextContent(
    "clients",
  );
});

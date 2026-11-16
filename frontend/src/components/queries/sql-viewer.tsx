"use client";

import { Fragment, useMemo, useState, type ReactNode } from "react";
import { Check, Code2, Copy, GitCompareArrows } from "lucide-react";
import {
  compareSqlLines,
  formatSql,
  highlightSqlLines,
  sqlPreview,
} from "@/lib/sql";

type SqlTokens = ReturnType<typeof highlightSqlLines>[number];

function Tokens({ tokens }: { tokens: SqlTokens }) {
  return tokens.map(({ text, kind }, index) =>
    kind ? (
      <span key={index} className={"token " + kind}>
        {text}
      </span>
    ) : (
      <Fragment key={index}>{text}</Fragment>
    ),
  );
}

export function SqlPreview({ sql }: { sql: string | null }) {
  const lines = useMemo(() => sql && highlightSqlLines(sqlPreview(sql)), [sql]);
  if (!lines) return <span className="cell-secondary">SQL ontbreekt</span>;
  return (
    <code className="sql-preview">
      {lines.map((tokens, index) => (
        <Fragment key={index}>
          {index > 0 && "\n"}
          <Tokens tokens={tokens} />
        </Fragment>
      ))}
    </code>
  );
}

function CopySql({ sql, title }: { sql: string; title: string }) {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "error">(
    "idle",
  );
  async function copy() {
    try {
      await navigator.clipboard.writeText(sql);
      setCopyState("copied");
    } catch {
      setCopyState("error");
    }
  }
  return (
    <div className="sql-copy">
      <button type="button" onClick={copy} aria-label={"Kopieer SQL: " + title}>
        {copyState === "copied" ? <Check size={14} /> : <Copy size={14} />}
        Kopieer SQL
      </button>
      <span className="sql-copy-status" role="status">
        {copyState === "copied"
          ? "Gekopieerd"
          : copyState === "error"
            ? "Kopiëren mislukt"
            : ""}
      </span>
    </div>
  );
}

export function SqlViewer({
  sql,
  title = "SQL",
  empty = "Geen SQL opgeslagen voor deze poging.",
  label,
  timing,
  formatted,
}: {
  sql: string | null;
  title?: string;
  empty?: string;
  label?: string;
  timing?: string;
  formatted?: string | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const lines = useMemo(
    () => (sql?.trim() ? highlightSqlLines(formatted ?? formatSql(sql)) : null),
    [sql, formatted],
  );
  const visibleLines = expanded ? lines : lines?.slice(0, 18);
  return (
    <section className="sql-viewer" aria-label={title}>
      <div className="sql-heading">
        <div className="sql-label">
          <Code2 size={17} aria-hidden="true" />
          <h3>{title}</h3>
          {label && <span className="sql-tag">{label}</span>}
        </div>
        <div className="sql-actions">
          {timing && (
            <span className="sql-timing" title="Mediane uitvoeringstijd">
              {timing}
            </span>
          )}
          {lines && sql && <CopySql key={sql} sql={sql} title={title} />}
        </div>
      </div>
      {visibleLines ? (
        <>
          <pre className="sql-body" tabIndex={0} aria-label={title + " code"}>
            <code>
              {visibleLines.map((tokens, index) => (
                <Fragment key={index}>
                  {index > 0 && "\n"}
                  <span className="sql-line" data-line={index + 1}>
                    <span>
                      <Tokens tokens={tokens} />
                    </span>
                  </span>
                </Fragment>
              ))}
            </code>
          </pre>
          {lines && lines.length > 18 && (
            <button
              type="button"
              className="sql-expand"
              aria-expanded={expanded}
              onClick={() => setExpanded(!expanded)}
            >
              {expanded
                ? "Toon minder regels"
                : "Toon alle " + lines.length + " regels"}
            </button>
          )}
        </>
      ) : (
        <p className="sql-empty">{empty}</p>
      )}
    </section>
  );
}

function SqlDiff({
  original,
  proposed,
}: {
  original: string;
  proposed: string;
}) {
  const changes = useMemo(
    () => compareSqlLines(original, proposed),
    [original, proposed],
  );
  const oldLines = useMemo(() => highlightSqlLines(original), [original]);
  const newLines = useMemo(() => highlightSqlLines(proposed), [proposed]);
  if (!changes)
    return (
      <p className="sql-empty">
        Dit verschil is te groot om hier te berekenen. Bekijk beide SQL-versies
        in de SQL-weergave.
      </p>
    );
  if (!changes.some((change) => change.added || change.removed)) {
    return <p className="sql-empty">Geen verschillen in de weergegeven SQL.</p>;
  }
  let oldIndex = 0;
  let newIndex = 0;
  const rows = changes.flatMap((change) => {
    const kind = change.added
      ? "added"
      : change.removed
        ? "removed"
        : "unchanged";
    return Array.from({ length: change.count ?? 0 }, () => {
      const tokens = change.removed ? oldLines[oldIndex] : newLines[newIndex];
      const before = change.added ? null : ++oldIndex;
      const after = change.removed ? null : ++newIndex;
      return { before, after, kind, tokens };
    });
  });
  return (
    <div className="sql-viewer">
      <div className="sql-heading">
        <h3>SQL-diff</h3>
        <div className="diff-legend">
          <span className="diff-removed">− Verwijderd</span>
          <span className="diff-added">+ Toegevoegd</span>
        </div>
      </div>
      <div
        className="sql-body diff-body"
        tabIndex={0}
        aria-label="Verschillen in SQL"
      >
        {rows.map((row, index) => (
          <code key={index} className={"diff-line diff-" + row.kind}>
            <span aria-hidden="true">{row.before}</span>
            <span aria-hidden="true">{row.after}</span>
            <span
              aria-label={
                row.kind === "removed"
                  ? "Verwijderd"
                  : row.kind === "added"
                    ? "Toegevoegd"
                    : undefined
              }
            >
              {row.kind === "removed" ? "−" : row.kind === "added" ? "+" : ""}
            </span>
            <span className="diff-text">
              <Tokens tokens={row.tokens ?? []} />
            </span>
          </code>
        ))}
      </div>
    </div>
  );
}

export function SqlComparison({
  original,
  proposed,
  empty,
  proposedLabel,
  timing,
  status,
}: {
  original: string | null;
  proposed: string | null;
  empty?: string;
  proposedLabel?: string;
  timing?: { original: string; proposed: string };
  status?: ReactNode;
}) {
  const [showDiff, setShowDiff] = useState(false);
  const before = useMemo(() => original && formatSql(original), [original]);
  const after = useMemo(() => proposed && formatSql(proposed), [proposed]);
  return (
    <section
      className="panel sql-compare"
      aria-label="Query Optimization Comparison"
    >
      <header className="panel-heading">
        <div>
          <h2>Query Optimization Comparison</h2>
          <p>Bekijk het origineel, het voorstel en de gewijzigde SQL-regels.</p>
        </div>
        {before && after && (
          <div
            className="segmented-control"
            role="group"
            aria-label="SQL-weergave"
          >
            <button
              type="button"
              aria-pressed={!showDiff}
              onClick={() => setShowDiff(false)}
            >
              <Code2 size={15} /> SQL
            </button>
            <button
              type="button"
              aria-pressed={showDiff}
              onClick={() => setShowDiff(true)}
            >
              <GitCompareArrows size={15} /> SQL-diff
            </button>
          </div>
        )}
      </header>
      <div className="panel-body sql-pair">
        {status}
        {showDiff && before && after ? (
          <SqlDiff original={before} proposed={after} />
        ) : (
          <>
            <SqlViewer
              title="Original SQL Query"
              sql={original}
              formatted={before}
              timing={timing?.original}
            />
            <SqlViewer
              title="Optimized SQL Query"
              sql={proposed}
              formatted={after}
              empty={empty}
              label={proposedLabel}
              timing={timing?.proposed}
            />
          </>
        )}
      </div>
    </section>
  );
}

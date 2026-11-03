"use client";
import { useState } from "react";
import Prism from "prismjs";
import "prismjs/components/prism-sql";
import { Check, Copy } from "lucide-react";

export function SqlViewer({
  sql,
  title = "SQL",
  empty = "Geen SQL beschikbaar in het bronartefact.",
}: {
  sql: string | null;
  title?: string;
  empty?: string;
}) {
  const [copyState, setCopyState] = useState("Kopieer SQL");
  async function copy() {
    try {
      await navigator.clipboard.writeText(sql ?? "");
      setCopyState("Gekopieerd");
    } catch {
      setCopyState("Kopiëren mislukt");
    }
  }
  return (
    <section className="sql-viewer" aria-label={title}>
      <div className="sql-heading">
        <span>{title}</span>
        {sql && (
          <button onClick={copy} aria-label={`${copyState}: ${title}`}>
            {copyState === "Gekopieerd" ? (
              <Check size={12} />
            ) : (
              <Copy size={12} />
            )}
            {copyState}
          </button>
        )}
      </div>
      {sql ? (
        <pre>
          <code
            dangerouslySetInnerHTML={{
              __html: Prism.highlight(sql, Prism.languages.sql, "sql"),
            }}
          />
        </pre>
      ) : (
        <p className="sql-empty">{empty}</p>
      )}
    </section>
  );
}
export function SqlComparison({
  original,
  proposed,
}: {
  original: string | null;
  proposed: string | null;
}) {
  return (
    <div className="sql-compare">
      <SqlViewer title="Originele query" sql={original} />
      <SqlViewer title="Voorgestelde herschrijving" sql={proposed} />
    </div>
  );
}

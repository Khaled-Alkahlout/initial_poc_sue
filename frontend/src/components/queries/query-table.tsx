"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { ArrowDownUp, Search } from "lucide-react";
import type { Query } from "@/lib/api/contracts";
import { count } from "@/lib/formatters";
import { Badge, SourceBadge } from "@/components/shared/status";
import { Input, Select } from "@/components/ui/fields";
import { EmptyState } from "@/components/shared/states";

type SortKey =
  | "query_id"
  | "calls"
  | "mean_execution_time_ms"
  | "impact_ms"
  | "rank";
type Column = {
  id: string;
  label: string;
  sort?: SortKey;
  numeric?: boolean;
  render: (query: Query) => React.ReactNode;
};
// Presentation columns can change independently of the telemetry contract.
const columns: Column[] = [
  {
    id: "query",
    label: "Query",
    sort: "query_id",
    render: (q) => (
      <>
        <Link className="mono" href={`/queries/${q.query_id}`}>
          {q.query_id}
        </Link>
        <span className="cell-secondary cell-preview mono">
          {q.sql
            ?.split("\n")
            .filter((line) => !line.trim().startsWith("--"))
            .join(" ") ?? "SQL ontbreekt"}
        </span>
      </>
    ),
  },
  {
    id: "source",
    label: "Bron",
    render: (q) => (
      <SourceBadge source={q.is_synthetic ? "synthetic" : "measured"} />
    ),
  },
  {
    id: "calls",
    label: "Calls",
    sort: "calls",
    numeric: true,
    render: (q) => count(q.calls),
  },
  {
    id: "mean",
    label: "Gemiddeld · ms",
    sort: "mean_execution_time_ms",
    numeric: true,
    render: (q) => count(q.mean_execution_time_ms),
  },
  {
    id: "total",
    label: "Totale impact · ms",
    sort: "impact_ms",
    numeric: true,
    render: (q) => <strong>{count(q.impact_ms)}</strong>,
  },
  {
    id: "rank",
    label: "Rang",
    sort: "rank",
    render: (q) => (
      <span className={`rank ${q.rank === 1 ? "rank-first" : ""}`}>
        {q.rank ?? "—"}
      </span>
    ),
  },
  {
    id: "decision",
    label: "Selectie",
    render: (q) => (
      <Badge
        tone={
          q.selected ? "green" : q.status === "deferred" ? "amber" : "neutral"
        }
      >
        {q.selected
          ? "Geselecteerd"
          : q.status === "eligible"
            ? "Buiten budget"
            : q.status === "excluded"
              ? "Uitgesloten"
              : "Uitgesteld"}
      </Badge>
    ),
  },
  {
    id: "analysis",
    label: "Analyse",
    render: (q) => (
      <span className="muted">
        {q.analyzed
          ? `${q.analysis_count} vastgelegd`
          : "Nog niet geanalyseerd"}
      </span>
    ),
  },
];
export function QueryTable({ queries }: { queries: Query[] }) {
  const [search, setSearch] = useState("");
  const [decision, setDecision] = useState("all");
  const [analysis, setAnalysis] = useState("all");
  const [source, setSource] = useState("all");
  const [sort, setSort] = useState<{ key: SortKey; direction: number }>({
    key: "rank",
    direction: 1,
  });
  const visible = useMemo(
    () =>
      queries
        .filter(
          (q) =>
            `${q.query_id} ${q.sql ?? ""}`
              .toLowerCase()
              .includes(search.toLowerCase()) &&
            (decision === "all" ||
              (decision === "selected" ? q.selected : q.status === decision)) &&
            (analysis === "all" || q.analyzed === (analysis === "analyzed")) &&
            (source === "all" || q.is_synthetic === (source === "mock")),
        )
        .sort((a, b) => {
          const left = a[sort.key],
            right = b[sort.key];
          if (left == null)
            return right == null ? a.query_id.localeCompare(b.query_id) : 1;
          if (right == null) return -1;
          return (
            (typeof left === "string" && typeof right === "string"
              ? left.localeCompare(right)
              : Number(left) - Number(right)) * sort.direction
          );
        }),
    [queries, search, decision, analysis, source, sort],
  );
  return (
    <>
      <div className="toolbar">
        <div className="search-wrap">
          <Search size={15} />
          <Input
            aria-label="Zoek query of SQL"
            placeholder="Zoek op query-ID of SQL…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Select
          aria-label="Filter op selectiestatus"
          value={decision}
          onChange={(e) => setDecision(e.target.value)}
        >
          <option value="all">Alle beslissingen</option>
          <option value="selected">Geselecteerd</option>
          <option value="eligible">Geschikt</option>
          <option value="excluded">Uitgesloten</option>
          <option value="deferred">Uitgesteld</option>
        </Select>
        <Select
          aria-label="Filter op analyse"
          value={analysis}
          onChange={(e) => setAnalysis(e.target.value)}
        >
          <option value="all">Alle analyses</option>
          <option value="analyzed">Geanalyseerd</option>
          <option value="not-analyzed">Niet geanalyseerd</option>
        </Select>
        <Select
          aria-label="Filter op bron"
          value={source}
          onChange={(e) => setSource(e.target.value)}
        >
          <option value="all">Alle bronnen</option>
          <option value="mock">Mocktelemetrie</option>
          <option value="real">Gemeten telemetrie</option>
        </Select>
      </div>
      {visible.length ? (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                {columns.map((column) => (
                  <th
                    key={column.id}
                    className={column.numeric ? "numeric" : ""}
                    aria-sort={
                      column.sort === sort.key
                        ? sort.direction === 1
                          ? "ascending"
                          : "descending"
                        : undefined
                    }
                  >
                    {column.sort ? (
                      <button
                        className="sort-button"
                        onClick={() =>
                          setSort({
                            key: column.sort!,
                            direction:
                              sort.key === column.sort ? -sort.direction : 1,
                          })
                        }
                      >
                        {column.label}
                        <ArrowDownUp size={11} />
                      </button>
                    ) : (
                      column.label
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visible.map((query) => (
                <tr key={query.query_id}>
                  {columns.map((column) => (
                    <td
                      className={column.numeric ? "numeric" : ""}
                      key={column.id}
                    >
                      {column.render(query)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          title="Geen query's gevonden"
          description="Pas de zoekterm of filters aan. Er worden geen fictieve vervangende resultaten getoond."
        />
      )}
      <div className="table-footer">
        <span>
          {visible.length} van {queries.length} querypatronen
        </span>
        <span>Ranking afkomstig van de Python-selectielaag</span>
      </div>
    </>
  );
}

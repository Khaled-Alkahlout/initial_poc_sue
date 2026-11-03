"use client";
import Link from "next/link";
import { useState } from "react";
import { ArrowDownUp, Search } from "lucide-react";
import type { TestRecord } from "@/lib/api/contracts";
import { count, dateTime } from "@/lib/formatters";
import { SourceBadge, StatusBadge } from "@/components/shared/status";
import { Input, Select } from "@/components/ui/fields";
import { EmptyState } from "@/components/shared/states";

export function TestMatrix({ tests }: { tests: TestRecord[] }) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [component, setComponent] = useState("all");
  const [origin, setOrigin] = useState("all");
  const [sort, setSort] = useState("date");
  const components = [...new Set(tests.map((test) => test.component))];
  const visible = tests
    .filter(
      (test) =>
        `${test.name} ${test.query_id ?? ""} ${test.actual ?? ""}`
          .toLowerCase()
          .includes(search.toLowerCase()) &&
        (status === "all" || test.status === status) &&
        (component === "all" || test.component === component) &&
        (origin === "all" ||
          (origin === "historical"
            ? test.origin === "historical"
            : test.origin !== "historical")),
    )
    .sort((a, b) =>
      sort === "name"
        ? a.name.localeCompare(b.name)
        : (b.executed_at ?? "").localeCompare(a.executed_at ?? ""),
    );
  return (
    <>
      <div className="toolbar">
        <div className="search-wrap">
          <Search size={15} />
          <Input
            placeholder="Zoek test, query of uitkomst…"
            aria-label="Zoek tests"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Select
          aria-label="Filter op teststatus"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="all">Alle statussen</option>
          <option value="passed">Geslaagd</option>
          <option value="failed">Mislukt</option>
          <option value="inconclusive">Onbeslist</option>
          <option value="warning">Aandachtspunt</option>
          <option value="error">Technische fout</option>
          <option value="skipped">Niet uitgevoerd</option>
        </Select>
        <Select
          aria-label="Filter op component"
          value={component}
          onChange={(e) => setComponent(e.target.value)}
        >
          <option value="all">Alle componenten</option>
          {components.map((value) => (
            <option key={value}>{value}</option>
          ))}
        </Select>
        <Select
          aria-label="Filter op evaluatiebron"
          value={origin}
          onChange={(e) => setOrigin(e.target.value)}
        >
          <option value="all">Alle bronnen</option>
          <option value="historical">Historisch</option>
          <option value="new">Nieuwe uitvoeringen / replays</option>
        </Select>
      </div>
      {visible.length ? (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>
                  <button
                    className="sort-button"
                    onClick={() => setSort(sort === "name" ? "date" : "name")}
                  >
                    Test / component <ArrowDownUp size={11} />
                  </button>
                </th>
                <th>Verwachting</th>
                <th>Werkelijke uitkomst</th>
                <th>Status</th>
                <th className="numeric">Duur · ms</th>
                <th>
                  <button
                    className="sort-button"
                    onClick={() => setSort("date")}
                  >
                    Uitvoering <ArrowDownUp size={11} />
                  </button>
                </th>
              </tr>
            </thead>
            <tbody>
              {visible.map((test) => (
                <tr key={test.id}>
                  <td>
                    <Link
                      href={`/development/tests/${encodeURIComponent(test.id)}`}
                      className="mono cell-preview"
                    >
                      {test.name}
                    </Link>
                    <span className="cell-secondary">{test.component}</span>
                  </td>
                  <td>
                    {test.expected ?? (
                      <span className="muted">Niet gedefinieerd</span>
                    )}
                  </td>
                  <td className="mono">{test.actual ?? "Niet vastgelegd"}</td>
                  <td>
                    <StatusBadge status={test.status} />
                  </td>
                  <td className="numeric">{count(test.duration_ms)}</td>
                  <td>
                    <SourceBadge source={test.origin} />
                    <span className="cell-secondary">
                      {dateTime(test.executed_at)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          title="Geen evaluaties voor deze filters"
          description="Ontbrekende of niet-uitgevoerde controles worden niet als geslaagd ingevuld."
        />
      )}
      <div className="table-footer">
        <span>
          {visible.length} van {tests.length} evaluatierecords
        </span>
        <span>Reviews staan los van technische uitslagen</span>
      </div>
    </>
  );
}

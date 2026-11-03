"use client";
import Link from "next/link";
import { useState } from "react";
import { ArrowDownUp, ArrowUpRight, Search } from "lucide-react";
import type { RunSummary } from "@/lib/api/contracts";
import { count, dateTime } from "@/lib/formatters";
import { LifecycleBadge, SourceBadge } from "@/components/shared/status";
import { EmptyState } from "@/components/shared/states";
import { Input, Select } from "@/components/ui/fields";

export function RunTable({
  runs,
  controls = false,
}: {
  runs: RunSummary[];
  controls?: boolean;
}) {
  const [search, setSearch] = useState("");
  const [mode, setMode] = useState("all");
  const [status, setStatus] = useState("all");
  const [ascending, setAscending] = useState(false);
  const visible = runs
    .filter(
      (run) =>
        `${run.id} ${run.query_ids.join(" ")} ${run.title}`
          .toLowerCase()
          .includes(search.toLowerCase()) &&
        (mode === "all" || run.mode === mode) &&
        (status === "all" || run.lifecycle === status),
    )
    .sort((a, b) =>
      ascending
        ? a.created_at.localeCompare(b.created_at)
        : b.created_at.localeCompare(a.created_at),
    );
  return (
    <>
      {controls && (
        <div className="toolbar">
          <div className="search-wrap">
            <Search size={15} />
            <Input
              aria-label="Zoek runs"
              placeholder="Zoek run of query…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <Select
            aria-label="Filter op runtype"
            value={mode}
            onChange={(e) => setMode(e.target.value)}
          >
            <option value="all">Alle runtypen</option>
            <option value="historical">Historisch</option>
            <option value="replay">Replay</option>
            <option value="mock">Offline mock</option>
            <option value="live_mock">Testdatabase · mock</option>
            <option value="live">Live POC</option>
          </Select>
          <Select
            aria-label="Filter op runstatus"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="all">Alle statussen</option>
            <option value="PENDING">In wachtrij</option>
            <option value="RUNNING">Bezig</option>
            <option value="COMPLETED">Afgerond</option>
            <option value="FAILED">Afgebroken</option>
          </Select>
        </div>
      )}
      {visible.length ? (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Run / query</th>
                <th>Type</th>
                <th>
                  <button
                    className="sort-button"
                    onClick={() => setAscending(!ascending)}
                  >
                    Tijdstip <ArrowDownUp size={11} />
                  </button>
                </th>
                <th>Status</th>
                <th className="numeric">Pogingen</th>
                <th className="numeric">Geaccepteerd</th>
                <th aria-label="Openen" />
              </tr>
            </thead>
            <tbody>
              {visible.map((run) => (
                <tr key={run.id}>
                  <td>
                    <Link href={`/runs/${run.id}`}>
                      {run.query_ids.join(", ") || run.title}
                    </Link>
                    <span className="cell-secondary mono">
                      {run.id.slice(0, 25)}
                    </span>
                  </td>
                  <td>
                    <SourceBadge source={run.mode} />
                  </td>
                  <td>{dateTime(run.created_at)}</td>
                  <td>
                    <LifecycleBadge status={run.lifecycle} />
                  </td>
                  <td className="numeric">{count(run.attempt_count)}</td>
                  <td className="numeric">{count(run.accepted_count)}</td>
                  <td>
                    <Link
                      href={`/runs/${run.id}`}
                      aria-label={`Open run ${run.id}`}
                    >
                      <ArrowUpRight size={14} />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          title="Geen runs gevonden"
          description="Start een replay of pas de filters aan."
        />
      )}
    </>
  );
}

"use client";
import type { RunSummary } from "@/lib/api/contracts";
import { api } from "@/lib/api/client";
import { useApi } from "@/hooks/use-api";
import { RunTable } from "@/components/pipeline/run-table";
import { ErrorState } from "@/components/shared/states";
const active = (runs: RunSummary[]) =>
  runs.some((run) => ["PENDING", "RUNNING"].includes(run.lifecycle));
export function RunList({ initial }: { initial: RunSummary[] }) {
  const { data, error, refresh } = useApi(api.getRuns, initial, active);
  return (
    <>
      {error && <ErrorState message={error} retry={refresh} />}
      <RunTable runs={data ?? initial} controls />
    </>
  );
}

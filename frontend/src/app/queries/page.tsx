import { api } from "@/lib/api/client";
import { loadPage } from "@/lib/api/load-page";
import { QueryExplorer } from "@/features/queries/query-explorer";
import { PageHeader } from "@/components/shared/page-header";
import { ErrorState } from "@/components/shared/states";
export const dynamic = "force-dynamic";
export default async function Page() {
  const result = await loadPage(api.getQueries);
  if (!result.ok) return <ErrorState message={result.message} />;
  return (
    <div className="stack">
      <PageHeader
        eyebrow="POC / TELEMETRIE & SELECTIE"
        title="Query Explorer"
        description="Van workload naar prioriteit. Ontdek welke query's geschikt zijn voor analyse, waarom ze worden geselecteerd en welke impact ze vertegenwoordigen."
      />
      <QueryExplorer initial={result.data} />
    </div>
  );
}

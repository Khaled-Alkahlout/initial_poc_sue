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
        title="Query Explorer"
        description="Zoek een SQL-query en bekijk hoe de selector de workload prioriteert."
      />
      <QueryExplorer initial={result.data} />
    </div>
  );
}

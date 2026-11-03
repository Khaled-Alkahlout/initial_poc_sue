import { api } from "@/lib/api/client";
import { loadPage } from "@/lib/api/load-page";
import { OverviewDashboard } from "@/features/dashboard/overview";
import { ErrorState } from "@/components/shared/states";
export const dynamic = "force-dynamic";
export default async function Page() {
  const result = await loadPage(() =>
    Promise.all([api.getOverview(), api.getSystem()]),
  );
  if (!result.ok) return <ErrorState message={result.message} />;
  const [data, system] = result.data;
  return <OverviewDashboard data={data} system={system} />;
}

import { api } from "@/lib/api/client";
import { loadPage } from "@/lib/api/load-page";
import { ErrorState } from "@/components/shared/states";
import { DevelopmentCenter } from "@/features/development/development-center";
export const dynamic = "force-dynamic";
export default async function Page() {
  const result = await loadPage(() =>
    Promise.all([api.getTests(), api.getSystem(), api.getOverview()]),
  );
  if (!result.ok) return <ErrorState message={result.message} />;
  const [tests, system, overview] = result.data;
  return (
    <DevelopmentCenter
      tests={tests.tests}
      counts={tests.counts}
      overview={overview}
      system={system}
    />
  );
}

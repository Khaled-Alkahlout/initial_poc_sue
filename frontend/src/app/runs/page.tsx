import { api } from "@/lib/api/client";
import { loadPage } from "@/lib/api/load-page";
import { RunList } from "@/features/runs/run-list";
import { StartRun } from "@/features/runs/start-run";
import { Card, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/shared/page-header";
import { ErrorState } from "@/components/shared/states";
export const dynamic = "force-dynamic";
export default async function Page() {
  const result = await loadPage(() =>
    Promise.all([api.getRuns(), api.getQueries(), api.getSystem()]),
  );
  if (!result.ok) return <ErrorState message={result.message} />;
  const [runs, queries, system] = result.data;
  return (
    <div className="stack">
      <PageHeader
        eyebrow="POC / SINGLE-AGENT PIPELINE"
        title="Pipeline-runs"
        description="Bekijk opgeslagen experimenten of start een gecontroleerde uitvoering. Replays worden nooit als nieuwe model- of performancemetingen gepresenteerd."
        action={<StartRun queries={queries.queries} system={system} />}
      />
      <Card>
        <CardHeader
          title="Runhistorie"
          description="Afgerond betekent dat de verwerking klaar is; het betekent niet dat alle voorstellen zijn geaccepteerd."
        />
        <RunList initial={runs} />
      </Card>
    </div>
  );
}

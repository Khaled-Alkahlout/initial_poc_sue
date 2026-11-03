import { api } from "@/lib/api/client";
import { loadPage } from "@/lib/api/load-page";
import { ErrorState } from "@/components/shared/states";
import { ArchitectureView } from "@/features/development/architecture";
export const dynamic = "force-dynamic";
export default async function Page() {
  const result = await loadPage(api.getSystem);
  if (!result.ok) return <ErrorState message={result.message} />;
  return <ArchitectureView system={result.data} />;
}

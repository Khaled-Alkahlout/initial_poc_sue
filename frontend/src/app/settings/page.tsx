import { api } from "@/lib/api/client";
import { loadPage } from "@/lib/api/load-page";
import { ErrorState } from "@/components/shared/states";
import { AISettingsPage } from "@/features/settings/ai-settings";
export const dynamic = "force-dynamic";
export default async function Page() {
  const result = await loadPage(api.getAISettings);
  if (!result.ok) return <ErrorState message={result.message} />;
  return <AISettingsPage initial={result.data} />;
}

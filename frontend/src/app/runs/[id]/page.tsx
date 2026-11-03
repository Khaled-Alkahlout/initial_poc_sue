import { notFound } from "next/navigation";
import { api } from "@/lib/api/client";
import { loadPage } from "@/lib/api/load-page";
import { RunDetail } from "@/features/runs/run-detail";
import { ErrorState } from "@/components/shared/states";
export const dynamic = "force-dynamic";
export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ attempt?: string }>;
}) {
  const { id } = await params;
  const search = await searchParams;
  const result = await loadPage(() => api.getRun(id));
  if (!result.ok) {
    if (result.status === 404) notFound();
    return <ErrorState message={result.message} />;
  }
  return <RunDetail initial={result.data} initialAttemptId={search.attempt} />;
}

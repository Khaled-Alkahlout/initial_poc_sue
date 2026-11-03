import { notFound } from "next/navigation";
import { api } from "@/lib/api/client";
import { loadPage } from "@/lib/api/load-page";
import { QueryDetailView } from "@/features/queries/query-detail";
import { ErrorState } from "@/components/shared/states";
export const dynamic = "force-dynamic";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const result = await loadPage(() =>
    Promise.all([api.getQuery(id), api.getSystem()]),
  );
  if (!result.ok) {
    if (result.status === 404) notFound();
    return <ErrorState message={result.message} />;
  }
  return <QueryDetailView query={result.data[0]} system={result.data[1]} />;
}

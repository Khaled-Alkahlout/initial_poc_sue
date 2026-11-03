import { notFound } from "next/navigation";
import { api } from "@/lib/api/client";
import { loadPage } from "@/lib/api/load-page";
import { ErrorState } from "@/components/shared/states";
import { TestDetail } from "@/features/development/test-detail";
export const dynamic = "force-dynamic";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const result = await loadPage(() => api.getTest(id));
  if (!result.ok) {
    if (result.status === 404) notFound();
    return <ErrorState message={result.message} />;
  }
  return <TestDetail test={result.data} />;
}

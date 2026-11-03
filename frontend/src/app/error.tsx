"use client";
import { ErrorState } from "@/components/shared/states";
export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <ErrorState
      message="Deze pagina kon niet worden geladen. Er worden geen vervangende resultaten getoond."
      retry={reset}
    />
  );
}

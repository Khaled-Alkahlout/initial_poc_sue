"use client";
import { useCallback, useEffect, useState } from "react";
import { errorMessage } from "@/lib/api/client";

/** Components supply centralized API methods; no domain status is inferred here. */
export function useApi<T>(
  loader: () => Promise<T>,
  initial?: T,
  pollWhen?: (value: T) => boolean,
) {
  const [data, setData] = useState<T | undefined>(initial);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const refresh = useCallback(() => setVersion((v) => v + 1), []);
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      try {
        const result = await loader();
        if (disposed) return;
        setData(result);
        setError(null);
        if (pollWhen?.(result)) timer = setTimeout(load, 1200);
      } catch (reason) {
        if (!disposed) setError(errorMessage(reason));
      }
    }
    void load();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [loader, pollWhen, version]);
  return { data, error, loading: data === undefined && !error, refresh };
}

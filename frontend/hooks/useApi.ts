"use client";
// =============================================================================
// HiveMind — useApi Hook
// Generic data-fetching hook with loading/error state.
// Usage: const { data, loading, error } = useApi(fetchRuns);
// With args: const { data } = useApi(() => fetchTasksByRun(runId), [runId]);
// =============================================================================

import { useState, useEffect, useCallback } from "react";

interface UseApiReturn<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

/**
 * Generic hook for fetching data from the API.
 *
 * @param fetcher — A function that returns a Promise<T>.
 * @param deps — Dependency array. The fetcher re-runs when any dep changes.
 *               Pass an empty array for "fetch once on mount".
 */
export function useApi<T>(
  fetcher: () => Promise<T>,
  deps: React.DependencyList = []
): UseApiReturn<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetcher();
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, loading, error, refetch: fetchData };
}

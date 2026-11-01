// TanStack Query over the existing client: caching, retries, stale-while-revalidate and request de-duplication.
// Pages migrate from useEffect+fetch to these hooks one workspace at a time; `api` itself is unchanged.
import { QueryClient, useQuery } from "@tanstack/react-query";
import { api } from "./client";
import { readStatus } from "../studio/api";

export const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 60_000, gcTime: 10 * 60_000, retry: 1, refetchOnWindowFocus: false } },
});

export const useHealth = () =>
  useQuery({ queryKey: ["health"], queryFn: () => api.health(), refetchInterval: (q) => (q.state.status === "error" ? 5000 : false), retry: false });

/** The ranked CCR queue (also used to choose the default watchlist). */
export const usePriorityQueue = () => useQuery({ queryKey: ["priority-queue"], queryFn: () => api.priorityQueue() });

/** Is the operator switch on (server started with the Studio enabled)? Admin tools are hidden from the analyst nav when it is not. */
export const useOperatorMode = () => useQuery({ queryKey: ["operator-mode"], queryFn: async () => (await readStatus()).kind === "enabled", staleTime: 5 * 60_000 });

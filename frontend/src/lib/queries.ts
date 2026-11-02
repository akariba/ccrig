import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export const useToday = (asOf: string, watchlist: string[]) => useQuery({ queryKey: ["today", asOf, watchlist.join(",")], queryFn: () => api.today(asOf, watchlist), enabled: watchlist.length > 0 });
export const useNetworkGraph = (params: Record<string, string | number | boolean>, enabled = true) => useQuery({ queryKey: ["network", params], queryFn: () => api.networkGraph(params), enabled });
export const useCounterpartyPage = (id: string | undefined) => useQuery({ queryKey: ["cp", id], queryFn: () => api.counterpartyPage(id!), enabled: !!id, retry: false });
export const useStressRun = () => useMutation({ mutationFn: (b: { shock: string[]; max_hops?: number; label?: string }) => api.stressRun(b) });
export const useSources = (asOf: string) => useQuery({ queryKey: ["health-sources", asOf], queryFn: () => api.healthSources(asOf) });
export const useModels = () => useQuery({ queryKey: ["health-models"], queryFn: () => api.healthModels() });
export const usePipeline = () => useQuery({ queryKey: ["health-pipeline"], queryFn: () => api.healthPipeline() });
export const useScenarios = () => useQuery({ queryKey: ["stress-scenarios"], queryFn: () => api.stressScenarios() });

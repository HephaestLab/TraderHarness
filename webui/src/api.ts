import type {
  AgentCard,
  LLMConfig,
  LLMTestResult,
  ResultAnalysis,
  ResultDocument,
  ResultSummary,
  RunState,
  RuntimeStatus,
  ToolCatalogEntry,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
    ...init,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail || `请求失败（${response.status}）`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  status: () => request<RuntimeStatus>("/api/status"),
  tools: () => request<ToolCatalogEntry[]>("/api/tools"),
  agents: () => request<AgentCard[]>("/api/agents"),
  createAgent: (card: AgentCard) =>
    request<AgentCard>("/api/agents", {
      method: "POST",
      body: JSON.stringify(card),
    }),
  updateAgent: (card: AgentCard) =>
    request<AgentCard>(`/api/agents/${encodeURIComponent(card.id)}`, {
      method: "PUT",
      body: JSON.stringify(card),
    }),
  deleteAgent: (id: string) =>
    request<void>(`/api/agents/${encodeURIComponent(id)}`, { method: "DELETE" }),
  results: () => request<ResultSummary[]>("/api/results"),
  result: (file: string) =>
    request<ResultDocument>(`/api/results/${encodeURIComponent(file)}`),
  resultAnalysis: (file: string) =>
    request<ResultAnalysis>(`/api/results/${encodeURIComponent(file)}/analysis`),
  deleteResult: (file: string) =>
    request<void>(`/api/results/${encodeURIComponent(file)}`, { method: "DELETE" }),
  startRun: (payload: {
    agents: string[];
    start_date: string;
    end_date: string;
    initial_cash: number;
    mask_entities: boolean;
    entity_mask_seed: number;
  }) =>
    request<RunState>("/api/runs", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  startDemo: () => request<RunState>("/api/demo", { method: "POST" }),
  runs: () => request<RunState[]>("/api/runs"),
  run: (id: string) => request<RunState>(`/api/runs/${encodeURIComponent(id)}`),
  cancelRun: (id: string) =>
    request<RunState>(`/api/runs/${encodeURIComponent(id)}`, { method: "DELETE" }),
  getLLMConfig: () => request<LLMConfig>("/api/config/llm"),
  saveLLMConfig: (payload: { api_key?: string; base_url?: string; clear?: boolean }) =>
    request<LLMConfig>("/api/config/llm", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  testLLMConfig: (payload: { api_key?: string; base_url?: string; model?: string }) =>
    request<LLMTestResult>("/api/config/llm/test", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};

export function eventSocketUrl(runId: string): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/api/runs/${encodeURIComponent(runId)}/events`;
}

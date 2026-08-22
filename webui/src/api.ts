import type {
  AgentCard,
  LLMConfig,
  LLMTestResult,
  MaskingShowcase,
  PaperSession,
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
  maskingShowcase: () => request<MaskingShowcase>("/api/showcase/masking-ab"),
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
  resultAnalysis: (
    file: string,
    revealEntities = false,
    detail: "summary" | "full" = "summary",
  ) => {
    const params = new URLSearchParams({ detail });
    if (revealEntities) params.set("reveal_entities", "true");
    return request<ResultAnalysis>(
      `/api/results/${encodeURIComponent(file)}/analysis?${params.toString()}`,
    );
  },
  deleteResult: (file: string) =>
    request<void>(`/api/results/${encodeURIComponent(file)}`, { method: "DELETE" }),
  startRun: (payload: {
    agents: string[];
    start_date: string;
    end_date: string;
    initial_cash: number;
    mask_dates: boolean;
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
  startPaper: (payload: {
    agent_id: string;
    session_date: string;
    initial_cash: number;
    mode: "live" | "accelerated";
    poll_seconds?: number;
    max_attention_codes?: number;
  }) =>
    request<PaperSession>("/api/paper/sessions", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  paperSessions: () => request<PaperSession[]>("/api/paper/sessions"),
  paperSession: (id: string) =>
    request<PaperSession>(`/api/paper/sessions/${encodeURIComponent(id)}`),
  cancelPaper: (id: string) =>
    request<{ id: string; status: string }>(`/api/paper/sessions/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),
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

export function paperEventSocketUrl(sessionId: string): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/api/paper/sessions/${encodeURIComponent(sessionId)}/events`;
}

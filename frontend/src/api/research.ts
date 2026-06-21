import client from "./client";

export interface ResearchReport {
  id: number;
  source: string;
  title: string;
  url: string;
  report_type: "stock" | "industry";
  org: string;
  analyst: string;
  rating: string;
  target_price: number | null;
  current_price: number | null;
  industry: string;
  stock_codes: string[];
  publish_date: string;
  fetch_time: string;
  summary: string;
  extra: Record<string, unknown>;
}

export interface ResearchReportListResponse {
  items: ResearchReport[];
  total: number;
  limit: number;
  offset: number;
}

export interface ResearchPick {
  id: number;
  trade_date: string;
  code: string;
  name: string;
  report_count: number;
  buy_rating_count: number;
  avg_target_price: number | null;
  upside_pct: number | null;
  current_price: number | null;
  org_count: number;
  consensus_score: number;
  ai_advice: "" | "buy" | "watch" | "avoid";
  ai_buy_low: number | null;
  ai_buy_high: number | null;
  ai_stop_loss: number | null;
  ai_catalyst: string;
  ai_risk: string;
  ai_analysis: string;
  confidence: number;
  score: number;
  model_used: string;
  status: string;
}

export interface ResearchPickListResponse {
  items: ResearchPick[];
  total: number;
  trade_date: string | null;
}

export interface ResearchPickTaskStatus {
  active: boolean;
  status: "idle" | "running" | "completed" | "failed";
  trade_date: string;
  phase: string;
  started_at: string | null;
  finished_at: string | null;
  stage: string | null;
  finished: number;
  total: number;
  error: string | null;
}

export interface ResearchSyncResult {
  total: number;
  inserted: number;
  status: string;
  duration: number;
}

export interface FetchReportsParams {
  days?: number;
  report_type?: "stock" | "industry";
  rating?: string;
  org?: string;
  limit?: number;
  offset?: number;
}

export async function fetchReports(params: FetchReportsParams = {}): Promise<ResearchReportListResponse> {
  const { data } = await client.get("/research/reports", { params });
  return data;
}

export async function fetchOrgs(limit = 50): Promise<{ items: string[] }> {
  const { data } = await client.get("/research/orgs", { params: { limit } });
  return data;
}

export async function fetchPicks(tradeDate?: string): Promise<ResearchPickListResponse> {
  const { data } = await client.get("/research/picks", {
    params: tradeDate ? { trade_date: tradeDate } : {},
  });
  return data;
}

export async function fetchPickHistory(limit = 50, offset = 0): Promise<{ items: unknown[]; total: number }> {
  const { data } = await client.get("/research/picks/history", { params: { limit, offset } });
  return data;
}

export async function fetchPickTaskStatus(
  tradeDate: string,
  phase = "close",
): Promise<ResearchPickTaskStatus> {
  const { data } = await client.get("/research/picks/task-status", {
    params: { trade_date: tradeDate, phase },
  });
  return data;
}

export async function triggerPickGeneration(
  tradeDate?: string,
  phase = "close",
): Promise<{ started: boolean; already_running: boolean; trade_date: string; phase: string; started_at?: string; stage?: string }> {
  const { data } = await client.post("/research/picks/generate", { trade_date: tradeDate, phase });
  return data;
}

export async function triggerResearchSync(days = 3): Promise<ResearchSyncResult> {
  const { data } = await client.post("/research/sync", null, { params: { days } });
  return data;
}

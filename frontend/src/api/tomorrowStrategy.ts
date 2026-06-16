import client from "./client";

export interface TomorrowStrategyEvent {
  title?: string;
  source?: string;
  impact?: string;
}

export interface TomorrowStrategySector {
  rank?: number;
  code?: string;
  name?: string;
  sector_type?: string;
  change_pct_today?: number | null;
  streak_up_days?: number | null;
  main_net_inflow_yi?: number | null;
  news_count?: number | null;
  news_avg_score?: number | null;
  top_events?: TomorrowStrategyEvent[];
  sustainability?: string | null;
  sustainability_reason?: string | null;
  tomorrow_outlook?: string | null;
}

export interface TomorrowStrategyStock {
  sector_code?: string;
  sector_name?: string;
  code?: string;
  name?: string;
  role?: string;
  entry_logic?: string;
  watch_price_low?: number | null;
  watch_price_high?: number | null;
  stop_loss_price?: number | null;
  target_price?: number | null;
  risk_tags?: string[];
}

export interface TomorrowStrategyAdvice {
  position_level?: string;
  style?: string;
  market_bias?: string;
  risk_warnings?: string[];
  actionable_summary?: string;
}

export interface TomorrowStrategyItem {
  id: number;
  trade_date: string;
  content_json: Record<string, unknown>;
  raw_text: string;
  sectors_json: TomorrowStrategySector[];
  stocks_json: TomorrowStrategyStock[];
  strategy_json: TomorrowStrategyAdvice;
  model_used: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface TomorrowStrategyHistoryItem {
  id: number;
  trade_date: string;
  status: string;
  model_used?: string | null;
  sector_count?: number | null;
  stock_count?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface TomorrowStrategyResponse {
  items: TomorrowStrategyHistoryItem[];
  total: number;
}

export interface GenerateTomorrowStrategyResponse {
  success: boolean;
  message: string;
  data: TomorrowStrategyItem | null;
}

export async function fetchLatestTomorrowStrategy(): Promise<TomorrowStrategyItem | null> {
  const { data } = await client.get("/tomorrow-strategy/latest");
  return data;
}

export async function fetchTomorrowStrategyHistory(
  limit = 20,
  offset = 0,
): Promise<TomorrowStrategyResponse> {
  const { data } = await client.get("/tomorrow-strategy/history", { params: { limit, offset } });
  return data;
}

export async function fetchTomorrowStrategyByDate(date: string): Promise<TomorrowStrategyItem> {
  const { data } = await client.get(`/tomorrow-strategy/${date}`);
  return data;
}

export async function triggerTomorrowStrategy(
  date?: string,
): Promise<GenerateTomorrowStrategyResponse> {
  const params = date ? { date } : {};
  const { data } = await client.post("/tomorrow-strategy/generate", null, {
    params,
    timeout: 30000,
  });
  return data;
}

export interface TomorrowStrategyTaskStatus {
  active: boolean;
  status: string;
  trade_date: string;
  started_at?: string | null;
  finished_at?: string | null;
  stage?: string | null;
  error?: string | null;
}

export async function fetchTomorrowStrategyTaskStatus(
  date?: string,
): Promise<TomorrowStrategyTaskStatus> {
  const params = date ? { date } : {};
  const { data } = await client.get("/tomorrow-strategy/task-status", {
    params,
    timeout: 10000,
  });
  return data;
}

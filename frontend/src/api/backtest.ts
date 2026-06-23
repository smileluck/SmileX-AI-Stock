import client from "./client";

// ----- Types -----

export interface StrategyInfo {
  type: string;
  label: string;
  description: string;
  experimental?: boolean;
  default_params: {
    topN?: number;
    stop_loss?: number;
    take_profit?: number;
    factors?: Record<string, number>;
  };
}

export interface BacktestRequest {
  strategy_type: string;
  universe: string;
  start_date: string;
  end_date: string;
  initial_capital?: number;
  top_n?: number;
  rebalance?: string;
  stop_loss?: number;
  take_profit?: number;
  commission_bps?: number;
  stamp_duty_bps?: number;
  benchmark?: string;
  custom_factors?: Record<string, number>;
  name?: string;
}

export interface BacktestMetrics {
  total_return?: number;
  annual_return?: number;
  max_drawdown?: number;
  sharpe?: number;
  calmar?: number;
  win_rate?: number;
  profit_loss_ratio?: number;
  n_trades?: number;
  n_sells?: number;
  benchmark_total_return?: number | null;
  excess_return?: number | null;
  n_days?: number;
}

export interface EquityPoint {
  trade_date: string;
  equity: number;
  cash: number;
  position_value: number;
  benchmark: number | null;
  drawdown: number | null;
}

export interface TradeItem {
  trade_date: string;
  code: string;
  name: string | null;
  side: "buy" | "sell";
  price: number;
  shares: number;
  amount: number;
  cost: number;
  reason: string;
}

export interface BacktestRunMeta {
  id: number;
  name: string;
  strategy_type: string;
  universe: string;
  start_date: string;
  end_date: string;
  status: string;
  metrics: BacktestMetrics;
  created_at: string;
  finished_at: string | null;
}

export interface BacktestDetail {
  id: number;
  name: string;
  strategy_type: string;
  universe: string;
  start_date: string;
  end_date: string;
  status: string;
  params: Record<string, unknown>;
  metrics: BacktestMetrics;
  equity_curve: EquityPoint[];
  trades_summary: {
    n_trades: number;
    n_buys: number;
    n_sells: number;
    total_cost: number;
  };
  created_at: string;
  finished_at: string | null;
}

// ----- API -----

export async function fetchStrategies(): Promise<StrategyInfo[]> {
  const { data } = await client.get("/backtest/strategies");
  return data.items;
}

export async function fetchDataCoverage(universe = "main"): Promise<{
  n_days: number;
  n_codes: number;
  min_date: string | null;
  max_date: string | null;
  universe: string;
  sufficient: boolean;
}> {
  const { data } = await client.get("/backtest/data-coverage", { params: { universe } });
  return data;
}

export async function createBacktest(req: BacktestRequest): Promise<BacktestDetail> {
  const { data } = await client.post("/backtest/runs", req, { timeout: 120000 });
  return data;
}

export async function listBacktestRuns(limit = 50, offset = 0): Promise<{
  items: BacktestRunMeta[];
  total: number;
}> {
  const { data } = await client.get("/backtest/runs", { params: { limit, offset } });
  return data;
}

export async function getBacktestRun(id: number): Promise<BacktestDetail> {
  const { data } = await client.get(`/backtest/runs/${id}`);
  return data;
}

export async function listBacktestTrades(
  id: number,
  limit = 100,
  offset = 0,
): Promise<{ items: TradeItem[]; total: number }> {
  const { data } = await client.get(`/backtest/runs/${id}/trades`, {
    params: { limit, offset },
  });
  return data;
}

export async function deleteBacktestRun(id: number): Promise<void> {
  await client.delete(`/backtest/runs/${id}`);
}

export async function triggerBackfill(days = 365): Promise<{
  success: boolean;
  message: string;
  task_id: string | null;
}> {
  const { data } = await client.post("/backtest/backfill", null, {
    params: { days },
    timeout: 10000,
  });
  return data;
}

export async function fetchBackfillStatus(taskId: string): Promise<{
  status: string;
  message: string;
  progress?: number;
}> {
  const { data } = await client.get(`/backtest/backfill/${taskId}/status`);
  return data;
}

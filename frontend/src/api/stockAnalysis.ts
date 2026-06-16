import client from "./client";
import type {
  GenerateStockAnalysisResponse,
  StockAnalysisItem,
  StockAnalysisResponse,
} from "../types";

export async function fetchLatestStockAnalysis(code?: string): Promise<StockAnalysisItem | null> {
  const { data } = await client.get("/stock/analysis/latest", {
    params: code ? { code } : {},
  });
  return data;
}

export async function fetchStockAnalysisHistory(
  code?: string,
  limit = 20,
  offset = 0
): Promise<StockAnalysisResponse> {
  const { data } = await client.get("/stock/analysis/history", {
    params: { limit, offset, ...(code ? { code } : {}) },
  });
  return data;
}

export async function fetchStockAnalysisDetail(id: number): Promise<StockAnalysisItem> {
  const { data } = await client.get(`/stock/analysis/detail/${id}`);
  return data;
}

export async function triggerStockAnalysis(
  code: string,
  tradeDate?: string
): Promise<GenerateStockAnalysisResponse> {
  const { data } = await client.post("/stock/analysis/generate", {
    code,
    trade_date: tradeDate || null,
  }, {
    timeout: 30000,
  });
  return data;
}

export interface StockAnalysisTaskStatus {
  active: boolean;
  status: string;
  code: string;
  trade_date: string;
  started_at?: string | null;
  finished_at?: string | null;
  stage?: string | null;
  analysis_id?: number | null;
  error?: string | null;
}

export async function fetchStockAnalysisTaskStatus(
  code: string,
  tradeDate?: string,
): Promise<StockAnalysisTaskStatus> {
  const params: Record<string, string> = { code };
  if (tradeDate) params.trade_date = tradeDate;
  const { data } = await client.get("/stock/analysis/task-status", {
    params,
    timeout: 10000,
  });
  return data;
}

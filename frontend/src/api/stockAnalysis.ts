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
  });
  return data;
}

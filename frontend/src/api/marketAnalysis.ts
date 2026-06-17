import client from "./client";
import type { MarketAnalysisItem, MarketAnalysisResponse, GenerateAnalysisResponse } from "../types";

export async function fetchLatestAnalysis(): Promise<MarketAnalysisItem | null> {
  const { data } = await client.get("/market/analysis/latest");
  return data;
}

export async function fetchAnalysisHistory(limit = 20, offset = 0): Promise<MarketAnalysisResponse> {
  const { data } = await client.get("/market/analysis/history", { params: { limit, offset } });
  return data;
}

export async function fetchAnalysisByDate(date: string): Promise<MarketAnalysisItem> {
  const { data } = await client.get(`/market/analysis/${date}`);
  return data;
}

export async function triggerAnalysis(tradeDate?: string): Promise<GenerateAnalysisResponse> {
  const { data } = await client.post("/market/analysis/generate", { trade_date: tradeDate || null }, { timeout: 180000 });
  return data;
}

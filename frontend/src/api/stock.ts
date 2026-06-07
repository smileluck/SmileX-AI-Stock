import client from "./client";
import type {
  StockOverviewResponse,
  LimitUpResponse,
  RecommendationListResponse,
  GenerateRecommendationResponse,
} from "../types";

export async function fetchStockOverview(): Promise<StockOverviewResponse> {
  const { data } = await client.get("/stock/overview");
  return data;
}

export async function fetchLimitUp(tradeDate?: string): Promise<LimitUpResponse> {
  const { data } = await client.get("/stock/limit-up", {
    params: tradeDate ? { trade_date: tradeDate } : {},
  });
  return data;
}

export async function triggerLimitUpSnapshot(): Promise<{ success: boolean; message: string }> {
  const { data } = await client.post("/stock/limit-up/snapshot");
  return data;
}

export async function fetchRecommendations(tradeDate?: string): Promise<RecommendationListResponse> {
  const { data } = await client.get("/stock/recommendation", {
    params: tradeDate ? { trade_date: tradeDate } : {},
  });
  return data;
}

export async function fetchRecommendationHistory(
  limit = 50,
  offset = 0
): Promise<RecommendationListResponse> {
  const { data } = await client.get("/stock/recommendation/history", {
    params: { limit, offset },
  });
  return data;
}

export async function triggerRecommendationGeneration(): Promise<GenerateRecommendationResponse> {
  const { data } = await client.post("/stock/recommendation/generate");
  return data;
}

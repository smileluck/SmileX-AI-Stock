import client from "./client";
import type { MarketOverviewResponse, MarketHistoryResponse } from "../types";

export async function fetchMarketOverview(): Promise<MarketOverviewResponse> {
  const { data } = await client.get("/market/overview");
  return data;
}

export async function fetchMarketHistory(days = 30): Promise<MarketHistoryResponse> {
  const { data } = await client.get("/market/history", { params: { days } });
  return data;
}

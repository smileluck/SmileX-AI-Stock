import client from "./client";
import type { MarketOverviewResponse } from "../types";

export async function fetchMarketOverview(): Promise<MarketOverviewResponse> {
  const { data } = await client.get("/market/overview");
  return data;
}

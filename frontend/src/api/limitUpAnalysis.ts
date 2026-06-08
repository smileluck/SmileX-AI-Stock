import client from "./client";
import type { LimitUpAnalysisResponse } from "../types";

export async function fetchLimitUpAnalysis(
  tradeDate?: string,
  board?: string,
  stockType?: string
): Promise<LimitUpAnalysisResponse> {
  const { data } = await client.get("/limit-up/analysis", {
    params: { trade_date: tradeDate, board, stock_type: stockType },
  });
  return data;
}

export async function triggerLimitUpAnalysisSnapshot() {
  const { data } = await client.post("/limit-up/analysis/snapshot");
  return data;
}

export async function triggerLimitUpAnalysisGenerate(tradeDate?: string) {
  const { data } = await client.post("/limit-up/analysis/generate", null, {
    params: { trade_date: tradeDate || undefined },
  });
  return data;
}

export async function fetchLimitUpAnalysisHistory(limit = 20, offset = 0) {
  const { data } = await client.get("/limit-up/analysis/history", {
    params: { limit, offset },
  });
  return data;
}

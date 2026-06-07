import client from "./client";
import type {
  SectorAnalysisItem,
  SectorAnalysisResponse,
  GenerateSectorAnalysisResponse,
} from "../types";

export async function fetchLatestSectorAnalysis(): Promise<SectorAnalysisItem | null> {
  const { data } = await client.get("/sector/analysis/latest");
  return data;
}

export async function fetchSectorAnalysisHistory(
  limit = 20,
  offset = 0
): Promise<SectorAnalysisResponse> {
  const { data } = await client.get("/sector/analysis/history", {
    params: { limit, offset },
  });
  return data;
}

export async function triggerSectorAnalysis(
  tradeDate?: string
): Promise<GenerateSectorAnalysisResponse> {
  const { data } = await client.post("/sector/analysis/generate", {
    trade_date: tradeDate || null,
  });
  return data;
}

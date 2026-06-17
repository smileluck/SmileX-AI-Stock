import client from "./client";
import type {
  SectorAnalysisItem,
  SectorAnalysisResponse,
  GenerateSectorAnalysisResponse,
  SectorAnalysisTaskStatus,
} from "../types";

export async function fetchLatestSectorAnalysis(
  sectorType?: string
): Promise<SectorAnalysisItem | null> {
  const { data } = await client.get("/sector/analysis/latest", {
    params: sectorType ? { sector_type: sectorType } : {},
  });
  return data;
}

export async function fetchSectorAnalysisByDate(
  tradeDate: string,
  sectorType: string
): Promise<SectorAnalysisItem> {
  const { data } = await client.get(`/sector/analysis/${tradeDate}`, {
    params: { sector_type: sectorType },
  });
  return data;
}

export async function fetchSectorAnalysisHistory(
  limit = 20,
  offset = 0,
  sectorType?: string
): Promise<SectorAnalysisResponse> {
  const { data } = await client.get("/sector/analysis/history", {
    params: { limit, offset, ...(sectorType ? { sector_type: sectorType } : {}) },
  });
  return data;
}

export async function triggerSectorAnalysis(
  tradeDate?: string,
  sectorType?: string
): Promise<GenerateSectorAnalysisResponse> {
  const { data } = await client.post("/sector/analysis/generate", {
    trade_date: tradeDate || null,
    sector_type: sectorType || null,
  });
  return data;
}

export async function fetchSectorAnalysisTaskStatus(
  tradeDate?: string,
  sectorType?: string
): Promise<SectorAnalysisTaskStatus> {
  const { data } = await client.get("/sector/analysis/task-status", {
    params: { trade_date: tradeDate || undefined, sector_type: sectorType || undefined },
  });
  return data;
}

export async function triggerSectorReview(
  tradeDate?: string
): Promise<GenerateSectorAnalysisResponse> {
  const { data } = await client.post("/sector/analysis/review", {
    trade_date: tradeDate || null,
  });
  return data;
}

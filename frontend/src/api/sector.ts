import client from "./client";
import type {
  SectorOverviewResponse,
  SectorCapitalFlowResponse,
  SectorHistoryDateResponse,
  SectorHistoryRangeResponse,
  SectorTrendResponse,
  SectorDatesResponse,
  SectorSnapshotResponse,
} from "../types";

export async function fetchSectorOverview(): Promise<SectorOverviewResponse> {
  const { data } = await client.get("/market/sector/overview");
  return data;
}

export async function fetchSectorCapitalFlow(): Promise<SectorCapitalFlowResponse> {
  const { data } = await client.get("/market/sector/capital-flow");
  return data;
}

export async function fetchSectorHistoryByDate(
  tradeDate: string,
  sectorType: string
): Promise<SectorHistoryDateResponse> {
  const { data } = await client.get("/market/sector/history/date", {
    params: { trade_date: tradeDate, sector_type: sectorType },
  });
  return data;
}

export async function fetchSectorHistoryRange(
  startDate: string,
  endDate: string,
  sectorType: string
): Promise<SectorHistoryRangeResponse> {
  const { data } = await client.get("/market/sector/history/range", {
    params: { start_date: startDate, end_date: endDate, sector_type: sectorType },
  });
  return data;
}

export async function fetchSectorTrend(
  code: string,
  sectorType: string,
  startDate: string,
  endDate: string
): Promise<SectorTrendResponse> {
  const { data } = await client.get("/market/sector/history/trend", {
    params: { code, sector_type: sectorType, start_date: startDate, end_date: endDate },
  });
  return data;
}

export async function fetchSectorAvailableDates(
  sectorType: string,
  limit = 90
): Promise<SectorDatesResponse> {
  const { data } = await client.get("/market/sector/history/dates", {
    params: { sector_type: sectorType, limit },
  });
  return data;
}

export async function triggerSectorSnapshot(): Promise<SectorSnapshotResponse> {
  const { data } = await client.post("/market/sector/snapshot");
  return data;
}

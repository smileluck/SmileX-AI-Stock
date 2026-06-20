import client from "./client";
import type {
  WatchlistStockResponse,
  WatchlistSearchItem,
  WatchlistStockDailyItem,
  WatchlistAnalysisResponse,
  WatchlistAnalysisTaskStatus,
  WatchlistSectorItem,
  WatchlistCustomSectorItem,
  WatchlistCustomSectorStockItem,
} from "../types";

// ---- 关注股 ----

export async function fetchWatchlistStocks(tradeDate?: string): Promise<WatchlistStockResponse> {
  const { data } = await client.get("/watchlist/stocks", {
    params: tradeDate ? { trade_date: tradeDate } : {},
  });
  return data;
}

export interface AddWatchlistStockPayload {
  code: string;
  name?: string;
  note?: string;
  add_price?: number | null;
  target_buy_price?: number | null;
  stop_loss_price?: number | null;
  source?: string;
  custom_sector_id?: number | null;
}

export async function addWatchlistStock(payload: AddWatchlistStockPayload) {
  return (await client.post("/watchlist/stocks", payload)).data;
}

export async function patchWatchlistStock(
  code: string,
  fields: Partial<AddWatchlistStockPayload> & { status?: string; sort_order?: number },
) {
  return (await client.patch(`/watchlist/stocks/${code}`, fields)).data;
}

export async function deleteWatchlistStock(code: string): Promise<{ success: boolean }> {
  return (await client.delete(`/watchlist/stocks/${code}`)).data;
}

export async function searchWatchlistStock(q: string, limit = 20): Promise<WatchlistSearchItem[]> {
  const { data } = await client.get("/watchlist/stocks/search", { params: { q, limit } });
  return data.items;
}

export async function addFromRecommendation(payload: { code: string; name?: string; add_price?: number | null }) {
  return (await client.post("/watchlist/stocks/from-recommendation", payload)).data;
}

export async function fetchWatchlistDaily(code: string, days = 30): Promise<WatchlistStockDailyItem[]> {
  const { data } = await client.get(`/watchlist/stocks/${code}/daily`, { params: { days } });
  return data.items;
}

// ---- 快照 ----

export async function triggerWatchlistSnapshot(tradeDate?: string) {
  return (await client.post("/watchlist/snapshot", null, {
    params: tradeDate ? { trade_date: tradeDate } : {},
  })).data;
}

// ---- 买点分析 ----

export async function generateWatchlistAnalysis(phase: "morning" | "close", tradeDate?: string) {
  return (await client.post("/watchlist/analysis/generate", null, {
    params: { phase, ...(tradeDate ? { trade_date: tradeDate } : {}) },
  })).data;
}

export async function fetchWatchlistAnalysisTaskStatus(
  tradeDate: string,
  phase: "morning" | "close",
): Promise<WatchlistAnalysisTaskStatus> {
  const { data } = await client.get("/watchlist/analysis/task-status", {
    params: { trade_date: tradeDate, phase },
  });
  return data;
}

export async function fetchWatchlistAnalysis(params: {
  tradeDate?: string;
  phase?: "morning" | "close";
  code?: string;
  limit?: number;
} = {}): Promise<WatchlistAnalysisResponse> {
  const { data } = await client.get("/watchlist/analysis", {
    params: {
      trade_date: params.tradeDate,
      phase: params.phase,
      code: params.code,
      limit: params.limit,
    },
  });
  return data;
}

// ---- 市场板块关注 ----

export async function fetchMarketSectors(): Promise<WatchlistSectorItem[]> {
  const { data } = await client.get("/watchlist/sectors");
  return data.items;
}

export async function addMarketSector(payload: { sector_name: string; sector_type?: string; note?: string }) {
  return (await client.post("/watchlist/sectors", {
    sector_type: "industry",
    ...payload,
  })).data;
}

export async function deleteMarketSector(id: number) {
  return (await client.delete(`/watchlist/sectors/${id}`)).data;
}

// ---- 自定义板块 ----

export async function fetchCustomSectors(): Promise<WatchlistCustomSectorItem[]> {
  const { data } = await client.get("/watchlist/custom-sectors");
  return data.items;
}

export async function createCustomSector(payload: { name: string; note?: string }) {
  return (await client.post("/watchlist/custom-sectors", payload)).data;
}

export async function updateCustomSector(id: number, payload: { name: string; note?: string }) {
  return (await client.put(`/watchlist/custom-sectors/${id}`, payload)).data;
}

export async function deleteCustomSector(id: number) {
  return (await client.delete(`/watchlist/custom-sectors/${id}`)).data;
}

export async function fetchCustomSectorStocks(sectorId: number): Promise<WatchlistCustomSectorStockItem[]> {
  const { data } = await client.get(`/watchlist/custom-sectors/${sectorId}/stocks`);
  return data.items;
}

export async function addCustomSectorStock(sectorId: number, payload: { code: string; name?: string }) {
  return (await client.post(`/watchlist/custom-sectors/${sectorId}/stocks`, payload)).data;
}

export async function removeCustomSectorStock(sectorId: number, code: string) {
  return (await client.delete(`/watchlist/custom-sectors/${sectorId}/stocks/${code}`)).data;
}

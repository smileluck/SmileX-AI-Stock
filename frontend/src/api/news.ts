import client from "./client";
import type { NewsResponse, SourceInfo, SyncResponse } from "../types";

export async function fetchNews(source?: string, limit = 100): Promise<NewsResponse> {
  const params: Record<string, string | number> = { limit };
  if (source) params.source = source;
  const { data } = await client.get("/news", { params });
  return data;
}

export async function fetchSources(): Promise<SourceInfo[]> {
  const { data } = await client.get("/news/sources");
  return data;
}

export async function triggerSync(): Promise<SyncResponse> {
  const { data } = await client.post("/news/sync");
  return data;
}

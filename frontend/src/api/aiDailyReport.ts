import client from "./client";
import type { AiDailyReportItem, AiDailyReportResponse } from "../types";

export async function fetchLatestReport(): Promise<AiDailyReportItem | null> {
  const { data } = await client.get("/ai/report/latest");
  return data;
}

export async function fetchReportHistory(limit = 20, offset = 0): Promise<AiDailyReportResponse> {
  const { data } = await client.get("/ai/report/history", { params: { limit, offset } });
  return data;
}

export async function fetchReportByDate(date: string): Promise<AiDailyReportItem> {
  const { data } = await client.get(`/ai/report/${date}`);
  return data;
}

export async function triggerReport(date?: string): Promise<{ success: boolean; message: string; data: AiDailyReportItem | null }> {
  const params = date ? { date } : {};
  const { data } = await client.post("/ai/report/generate", null, { params });
  return data;
}

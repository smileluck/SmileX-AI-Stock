import client from "./client";
import type { SectorOverviewResponse, SectorCapitalFlowResponse } from "../types";

export async function fetchSectorOverview(): Promise<SectorOverviewResponse> {
  const { data } = await client.get("/market/sector/overview");
  return data;
}

export async function fetchSectorCapitalFlow(): Promise<SectorCapitalFlowResponse> {
  const { data } = await client.get("/market/sector/capital-flow");
  return data;
}

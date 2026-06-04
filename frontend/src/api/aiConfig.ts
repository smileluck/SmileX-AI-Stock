import client from "./client";
import type {
  AIModelConfig,
  AIModelConfigCreate,
  AIModelConfigUpdate,
  ConnectionTestResult,
  ProviderInfo,
} from "../types";

export async function fetchProviders(): Promise<ProviderInfo[]> {
  const { data } = await client.get("/ai/config/providers");
  return data;
}

export async function fetchAIConfigs(): Promise<AIModelConfig[]> {
  const { data } = await client.get("/ai/config/models");
  return data.items;
}

export async function createAIConfig(payload: AIModelConfigCreate): Promise<AIModelConfig> {
  const { data } = await client.post("/ai/config/models", payload);
  return data;
}

export async function updateAIConfig(id: number, payload: AIModelConfigUpdate): Promise<AIModelConfig> {
  const { data } = await client.put(`/ai/config/models/${id}`, payload);
  return data;
}

export async function deleteAIConfig(id: number): Promise<void> {
  await client.delete(`/ai/config/models/${id}`);
}

export async function testAIConnection(configId: number): Promise<ConnectionTestResult>;
export async function testAIConnection(payload: AIModelConfigCreate): Promise<ConnectionTestResult>;
export async function testAIConnection(arg: number | AIModelConfigCreate): Promise<ConnectionTestResult> {
  if (typeof arg === "number") {
    const { data } = await client.post("/ai/config/test", null, { params: { config_id: arg } });
    return data;
  }
  const { data } = await client.post("/ai/config/test", arg);
  return data;
}

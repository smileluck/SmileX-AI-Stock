import client from "./client";

export interface ProxyStatus {
  success: boolean;
  models?: string[];
  error?: string;
}

export interface ModelConfigItem {
  function_key: string;
  label: string;
  description: string;
  model_name: string;
  source: "database" | "env_default";
}

export async function fetchProxyStatus(): Promise<ProxyStatus> {
  const { data } = await client.get("/ai/proxy/status");
  return data;
}

export async function testProxyConnection(): Promise<ProxyStatus> {
  const { data } = await client.post("/ai/proxy/test");
  return data;
}

export async function fetchModelConfigs(): Promise<ModelConfigItem[]> {
  const { data } = await client.get("/ai/model-config");
  return data;
}

export async function updateModelConfigs(
  configs: { function_key: string; model_name: string }[]
): Promise<{ success: boolean }> {
  const { data } = await client.put("/ai/model-config", { configs });
  return data;
}

export async function fetchAvailableModels(): Promise<string[]> {
  const { data } = await client.get("/ai/model-config/available-models");
  return data.models || [];
}

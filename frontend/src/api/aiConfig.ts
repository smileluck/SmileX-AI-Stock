import client from "./client";

export interface ProxyStatus {
  success: boolean;
  models?: string[];
  error?: string;
}

export async function fetchProxyStatus(): Promise<ProxyStatus> {
  const { data } = await client.get("/ai/proxy/status");
  return data;
}

export async function testProxyConnection(): Promise<ProxyStatus> {
  const { data } = await client.post("/ai/proxy/test");
  return data;
}

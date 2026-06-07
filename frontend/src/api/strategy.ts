import client from "./client";

export interface WeightConfig {
  fundamentals: number;
  technicals: number;
  news: number;
  capital_flow: number;
  sentiment: number;
}

export interface StrategyItem {
  id: number;
  name: string;
  type: string;
  description: string;
  prompt_template: string;
  weight_config: WeightConfig;
  news_enabled: boolean;
  news_count: number;
  output_format: Record<string, unknown>;
  is_enabled: boolean;
  is_default: boolean;
  sort_order: number;
  model_override: string | null;
  created_at: string;
  updated_at: string;
}

export interface StrategyListResponse {
  items: StrategyItem[];
  total: number;
}

export interface StrategyTypeInfo {
  key: string;
  label: string;
  description: string;
}

export async function fetchStrategies(
  type?: string,
  isEnabled?: boolean
): Promise<StrategyListResponse> {
  const params: Record<string, unknown> = {};
  if (type) params.type = type;
  if (isEnabled !== undefined) params.is_enabled = isEnabled;
  const { data } = await client.get("/strategy/list", { params });
  return data;
}

export async function fetchStrategy(id: number): Promise<StrategyItem> {
  const { data } = await client.get(`/strategy/${id}`);
  return data;
}

export async function createStrategy(
  item: Partial<StrategyItem>
): Promise<StrategyItem> {
  const { data } = await client.post("/strategy", item);
  return data;
}

export async function updateStrategy(
  id: number,
  item: Partial<StrategyItem>
): Promise<StrategyItem> {
  const { data } = await client.put(`/strategy/${id}`, item);
  return data;
}

export async function deleteStrategy(
  id: number
): Promise<{ success: boolean }> {
  const { data } = await client.delete(`/strategy/${id}`);
  return data;
}

export async function toggleStrategy(
  id: number
): Promise<StrategyItem> {
  const { data } = await client.put(`/strategy/${id}/toggle`);
  return data;
}

export async function duplicateStrategy(
  id: number
): Promise<StrategyItem> {
  const { data } = await client.post(`/strategy/${id}/duplicate`);
  return data;
}

export async function testStrategy(
  id: number,
  testInput: string
): Promise<{ result: string }> {
  const { data } = await client.post(`/strategy/${id}/test`, {
    test_input: testInput,
  });
  return data;
}

export async function fetchStrategyTypes(): Promise<StrategyTypeInfo[]> {
  const { data } = await client.get("/strategy/types");
  return data;
}

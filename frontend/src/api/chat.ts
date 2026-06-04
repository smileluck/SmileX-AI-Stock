import client from "./client";

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface ChatResponse {
  content: string;
  model: string;
}

export async function sendChatMessage(
  messages: ChatMessage[],
  model?: string,
): Promise<ChatResponse> {
  const { data } = await client.post("/ai/chat", { messages, model });
  return data;
}

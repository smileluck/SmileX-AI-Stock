import { useState, useRef, useEffect } from "react";
import {
  Card,
  Input,
  Button,
  Typography,
  Space,
  Avatar,
  Spin,
  Empty,
  message,
} from "antd";
import {
  SendOutlined,
  RobotOutlined,
  UserOutlined,
  DeleteOutlined,
} from "@ant-design/icons";
import { sendChatMessage } from "../api/chat";
import type { ChatMessage } from "../api/chat";

const { TextArea } = Input;

interface DisplayMessage extends ChatMessage {
  id: string;
}

export default function AIChat() {
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg: DisplayMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
    };

    const updatedMessages = [...messages, userMsg];
    setMessages(updatedMessages);
    setInput("");
    setLoading(true);

    try {
      const apiMessages = updatedMessages.map(({ role, content }) => ({
        role,
        content,
      }));
      const res = await sendChatMessage(apiMessages);
      const assistantMsg: DisplayMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: res.content,
      };
      setMessages([...updatedMessages, assistantMsg]);
    } catch {
      message.error("请求失败，请检查 LLM 配置");
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleClear = () => {
    setMessages([]);
  };

  return (
    <div>
      <Space
        style={{ marginBottom: 16, width: "100%", justifyContent: "space-between" }}
      >
        <Typography.Title level={4} style={{ margin: 0 }}>
          AI 对话
        </Typography.Title>
        <Button
          icon={<DeleteOutlined />}
          onClick={handleClear}
          disabled={messages.length === 0}
        >
          清空对话
        </Button>
      </Space>

      <Card
        bodyStyle={{
          display: "flex",
          flexDirection: "column",
          height: "calc(100vh - 240px)",
          padding: 0,
        }}
      >
        <div
          style={{
            flex: 1,
            overflowY: "auto",
            padding: 16,
          }}
        >
          {messages.length === 0 ? (
            <Empty
              description="开始与 AI 对话"
              style={{ marginTop: 80 }}
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            />
          ) : (
            messages.map((msg) => (
              <div
                key={msg.id}
                style={{
                  display: "flex",
                  justifyContent:
                    msg.role === "user" ? "flex-end" : "flex-start",
                  marginBottom: 16,
                }}
              >
                {msg.role === "assistant" && (
                  <Avatar
                    icon={<RobotOutlined />}
                    style={{
                      backgroundColor: "#1677ff",
                      flexShrink: 0,
                      marginRight: 8,
                    }}
                  />
                )}
                <div
                  style={{
                    maxWidth: "70%",
                    padding: "8px 12px",
                    borderRadius: 8,
                    backgroundColor:
                      msg.role === "user" ? "#1677ff" : "#f0f0f0",
                    color: msg.role === "user" ? "#fff" : "#000",
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-word",
                  }}
                >
                  {msg.content}
                </div>
                {msg.role === "user" && (
                  <Avatar
                    icon={<UserOutlined />}
                    style={{
                      backgroundColor: "#87d068",
                      flexShrink: 0,
                      marginLeft: 8,
                    }}
                  />
                )}
              </div>
            ))
          )}
          {loading && (
            <div style={{ display: "flex", alignItems: "center", marginBottom: 16 }}>
              <Avatar
                icon={<RobotOutlined />}
                style={{ backgroundColor: "#1677ff", flexShrink: 0, marginRight: 8 }}
              />
              <Spin size="small" />
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div
          style={{
            borderTop: "1px solid #f0f0f0",
            padding: 12,
            display: "flex",
            gap: 8,
          }}
        >
          <TextArea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入消息，Enter 发送，Shift+Enter 换行"
            autoSize={{ minRows: 1, maxRows: 4 }}
            disabled={loading}
            style={{ flex: 1 }}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            loading={loading}
            disabled={!input.trim()}
          >
            发送
          </Button>
        </div>
      </Card>
    </div>
  );
}

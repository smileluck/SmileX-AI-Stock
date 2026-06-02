import { Card, Typography, Space } from "antd";
import type { NewsItem, SourceInfo } from "../../types";
import SourceTag from "./SourceTag";
import dayjs from "dayjs";

const { Text, Paragraph } = Typography;

export default function NewsCard({ item, sources }: { item: NewsItem; sources: SourceInfo[] }) {
  const title = item.url?.startsWith("http") ? (
    <a href={item.url} target="_blank" rel="noreferrer">
      {item.title}
    </a>
  ) : (
    item.title
  );

  return (
    <Card size="small" style={{ marginBottom: 8 }}>
      <Space direction="vertical" size={4} style={{ width: "100%" }}>
        <Space>
          <SourceTag source={item.source} sources={sources} />
          <Text type="secondary" style={{ fontSize: 12 }}>
            {item.publish_time ? dayjs(item.publish_time).format("YYYY-MM-DD HH:mm") : ""}
          </Text>
        </Space>
        <Text strong>{title}</Text>
        {item.content && (
          <Paragraph ellipsis={{ rows: 2 }} style={{ margin: 0, color: "#666" }}>
            {item.content}
          </Paragraph>
        )}
      </Space>
    </Card>
  );
}

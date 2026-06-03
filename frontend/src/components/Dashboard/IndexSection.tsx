import { Typography } from "antd";
import IndexCard from "./IndexCard";
import type { IndexItem } from "../../types";

export default function IndexSection({ title, indices }: { title: string; indices: IndexItem[] }) {
  if (indices.length === 0) return null;

  return (
    <div style={{ marginBottom: 24 }}>
      <Typography.Title level={5} style={{ marginBottom: 12 }}>{title}</Typography.Title>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
        {indices.map((item) => (
          <IndexCard key={item.code} item={item} />
        ))}
      </div>
    </div>
  );
}

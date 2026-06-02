import { Tag } from "antd";
import type { SourceInfo } from "../../types";
import { SOURCE_COLOR_MAP } from "../../types";

export default function SourceTag({ source, sources }: { source: string; sources: SourceInfo[] }) {
  const info = sources.find((s) => s.name === source);
  return <Tag color={SOURCE_COLOR_MAP[source] || "default"}>{info?.label || source}</Tag>;
}

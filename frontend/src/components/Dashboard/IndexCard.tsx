import { Card, Statistic } from "antd";
import type { IndexItem } from "../../types";

function formatAmount(val: number | null | undefined): string | null {
  if (val == null) return null;
  if (val >= 1_000_000_000_000) return (val / 1_000_000_000_000).toFixed(2) + "万亿";
  if (val >= 1_000_000_00) return (val / 1_000_000_00).toFixed(2) + "亿";
  if (val >= 1_0000) return (val / 1_0000).toFixed(2) + "万";
  return val.toLocaleString();
}

function formatVolume(val: number | null | undefined): string | null {
  if (val == null) return null;
  if (val >= 1_000_000_00) return (val / 1_000_000_00).toFixed(2) + "亿手";
  if (val >= 1_0000) return (val / 1_0000).toFixed(2) + "万手";
  return val.toLocaleString() + "手";
}

const UP_COLOR = "#cf1322";
const DOWN_COLOR = "#3f8600";

export default function IndexCard({ item }: { item: IndexItem }) {
  const isUp = (item.change ?? 0) > 0;
  const isDown = (item.change ?? 0) < 0;
  const color = isUp ? UP_COLOR : isDown ? DOWN_COLOR : undefined;

  const changeStr = item.change != null ? (item.change > 0 ? "+" : "") + item.change.toFixed(2) : null;
  const pctStr = item.change_pct != null ? (item.change_pct > 0 ? "+" : "") + item.change_pct.toFixed(2) + "%" : null;

  return (
    <Card size="small" style={{ width: 230 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
        <span style={{ fontWeight: 600, fontSize: 14 }}>{item.name}</span>
        {item.update_time && (
          <span style={{ fontSize: 11, color: "#999" }}>{item.update_time.slice(11)}</span>
        )}
      </div>
      <Statistic
        value={item.price ?? "-"}
        precision={2}
        valueStyle={{ color, fontSize: 22, fontWeight: 700 }}
      />
      <div style={{ display: "flex", gap: 12, marginTop: 4, fontSize: 13, color }}>
        {changeStr && <span>{changeStr}</span>}
        {pctStr && <span>{pctStr}</span>}
      </div>
      {(item.volume != null || item.amount != null) && (
        <div style={{ marginTop: 6, fontSize: 12, color: "#888", display: "flex", gap: 12 }}>
          {item.amount != null && <span>额 {formatAmount(item.amount)}</span>}
          {item.volume != null && <span>量 {formatVolume(item.volume)}</span>}
        </div>
      )}
    </Card>
  );
}

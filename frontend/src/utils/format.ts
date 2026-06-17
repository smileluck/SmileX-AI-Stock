// 通用格式化与常量
export const POSITIVE_COLOR = "#cf1322";
export const NEGATIVE_COLOR = "#3f8600";

/** 红涨绿跌：v>0 红，v<0 绿，0/null 无颜色（沿用 antd 默认） */
export function pctColor(v: number | null | undefined): string | undefined {
  if (v == null) return undefined;
  return v > 0 ? POSITIVE_COLOR : v < 0 ? NEGATIVE_COLOR : undefined;
}

/** 涨跌幅：保留两位小数，正数加 + 号，null/undefined 显示 -- */
export function fmtPct(v: number | null | undefined): string {
  if (v == null) return "--";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

/** 金额：自动按亿/万切换，null/undefined 显示 -- */
export function fmtAmount(v: number | null | undefined): string {
  if (v == null) return "--";
  if (Math.abs(v) >= 1_0000_0000) return (v / 1_0000_0000).toFixed(2) + "亿";
  if (Math.abs(v) >= 1_0000) return (v / 1_0000).toFixed(2) + "万";
  return v.toLocaleString();
}

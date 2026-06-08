import { Dropdown } from "antd";
import type { MenuProps } from "antd";
import { LinkOutlined } from "@ant-design/icons";

function getMarket(code: string): string {
  if (code.startsWith("6")) return "SH";
  if (code.startsWith("8") || code.startsWith("4")) return "BJ";
  return "SZ";
}

function getPlatformUrl(code: string, platform: string): string {
  const m = getMarket(code);
  const ml = m.toLowerCase();
  switch (platform) {
    case "eastmoney":
      return `https://quote.eastmoney.com/${ml}${code}.html`;
    case "ths":
      return `https://stockpage.10jqka.com.cn/${code}/`;
    case "xueqiu":
      return `https://xueqiu.com/S/${m}${code}`;
    case "sina":
      return `https://finance.sina.com.cn/realstock/company/${ml}${code}/nc.shtml`;
    default:
      return "";
  }
}

const platforms = [
  { key: "eastmoney", label: "东方财富" },
  { key: "ths", label: "同花顺" },
  { key: "xueqiu", label: "雪球" },
  { key: "sina", label: "新浪财经" },
];

interface StockLinkProps {
  code: string;
  name?: string;
  children?: React.ReactNode;
}

export default function StockLink({ code, name, children }: StockLinkProps) {
  const items: MenuProps["items"] = platforms.map((p) => ({
    key: p.key,
    label: (
      <a href={getPlatformUrl(code, p.key)} target="_blank" rel="noopener noreferrer">
        {p.label}
      </a>
    ),
  }));

  return (
    <Dropdown menu={{ items }} trigger={["click"]}>
      <span
        style={{ color: "#1890ff", cursor: "pointer", whiteSpace: "nowrap" }}
        title={`${name || code} - 点击查看`}
      >
        {children || code} <LinkOutlined style={{ fontSize: 10, marginLeft: 2 }} />
      </span>
    </Dropdown>
  );
}

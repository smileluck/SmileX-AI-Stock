import { Menu } from "antd";
import {
  DashboardOutlined,
  ReadOutlined,
  StockOutlined,
  SettingOutlined,
  ExperimentOutlined,
  HistoryOutlined,
  BarChartOutlined,
  ThunderboltOutlined,
  FieldTimeOutlined,
} from "@ant-design/icons";
import { useNavigate, useLocation } from "react-router-dom";

const menuItems = [
  { key: "/", icon: <DashboardOutlined />, label: "大盘概览" },
  { key: "/news", icon: <ReadOutlined />, label: "资讯聚合" },
  { key: "/scheduler", icon: <FieldTimeOutlined />, label: "定时任务" },
  { key: "/stock", icon: <StockOutlined />, label: "个股分析" },
  { key: "/recommendation", icon: <ThunderboltOutlined />, label: "今日推荐" },
  { key: "/history", icon: <HistoryOutlined />, label: "历史推荐" },
  { key: "/strategy", icon: <ExperimentOutlined />, label: "策略管理" },
  { key: "/backtest", icon: <BarChartOutlined />, label: "策略回测" },
  { key: "/settings", icon: <SettingOutlined />, label: "系统设置" },
];

export default function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <Menu
      mode="inline"
      selectedKeys={[location.pathname]}
      items={menuItems}
      onClick={({ key }) => navigate(key)}
      style={{ height: "100%", borderRight: 0 }}
    />
  );
}

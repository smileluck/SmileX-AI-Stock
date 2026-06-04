import { Result, Typography } from "antd";
import { HistoryOutlined } from "@ant-design/icons";

export default function SectorHistory() {
  return (
    <div>
      <Typography.Title level={4} style={{ marginBottom: 24 }}>
        历史板块
      </Typography.Title>
      <Result
        icon={<HistoryOutlined style={{ color: "#1890ff" }} />}
        title="功能开发中"
        subTitle="历史板块数据功能正在开发中，敬请期待"
      />
    </div>
  );
}

export interface NewsItem {
  id: number;
  source: string;
  title: string;
  content: string;
  url: string;
  publish_time: string | null;
  fetch_time: string;
  extra: Record<string, unknown>;
}

export interface SourceInfo {
  name: string;
  label: string;
  count: number;
  today_count: number;
  last_fetch: string | null;
}

export interface SyncResultItem {
  source: string;
  label: string;
  count: number;
  status: string;
}

export interface NewsResponse {
  items: NewsItem[];
  total: number;
}

export interface SyncResponse {
  results: SyncResultItem[];
  total: number;
}

export interface SyncLogItem {
  id: number;
  job_id: string;
  trigger: string;
  results: SyncResultItem[];
  total: number;
  status: string;
  duration: number;
  created_at: string;
}

export interface SyncLogResponse {
  items: SyncLogItem[];
  total: number;
}

export interface ScheduleJob {
  id: string;
  next_run: string;
  trigger: string;
}

export const SOURCE_GROUPS: Record<string, {
  label: string;
  children: { name: string; label: string }[];
}> = {
  eastmoney: {
    label: "东方财富",
    children: [
      { name: "eastmoney", label: "财经" },
      { name: "eastmoney_global", label: "7×24全球" },
    ],
  },
  cls: {
    label: "财联社",
    children: [
      { name: "cls", label: "综合" },
      { name: "cls_red", label: "加红" },
      { name: "cls_announcement", label: "公司" },
      { name: "cls_watch", label: "看盘" },
      { name: "cls_hk_us", label: "港美股" },
      { name: "cls_fund", label: "基金" },
      { name: "cls_remind", label: "提醒" },
    ],
  },
};

export interface IndexItem {
  code: string;
  name: string;
  price: number | null;
  change: number | null;
  change_pct: number | null;
  volume?: number | null;
  amount?: number | null;
  high?: number | null;
  low?: number | null;
  open?: number | null;
  prev_close?: number | null;
  amplitude?: number | null;
  update_time?: string | null;
}

export interface MarketOverviewResponse {
  cn_main: IndexItem[];
  international: IndexItem[];
  fetch_time: string;
}

export interface IndexDailyItem {
  date: string;
  open: number;
  close: number;
  high: number;
  low: number;
  volume: number;
}

export interface IndexHistoryData {
  code: string;
  name: string;
  records: IndexDailyItem[];
}

export interface MarketHistoryResponse {
  indices: IndexHistoryData[];
  fetch_time: string;
}

export const SOURCE_COLOR_MAP: Record<string, string> = {
  eastmoney: "red",
  eastmoney_global: "magenta",
  cls: "orange",
  cls_red: "orange",
  cls_announcement: "orange",
  cls_watch: "orange",
  cls_hk_us: "orange",
  cls_fund: "orange",
  cls_remind: "orange",
  tonghuashun: "blue",
  sina: "purple",
  wallstreetcn: "cyan",
  yicai: "green",
  futu: "geekblue",
  xueqiu: "volcano",
  jrj: "gold",
};

export interface PredictionIndex {
  predicted_change_pct: number | null;
  support: number | null;
  resistance: number | null;
}

export interface PredictionSummary {
  overall_direction: "up" | "down" | "flat";
  confidence: number;
  indices: Record<string, PredictionIndex>;
  key_factors: string[];
  risk_level: "low" | "medium" | "high";
}

export interface ActualData {
  indices: Record<string, { close: number; change_pct: number; volume?: number }>;
  fetch_time: string;
}

export interface MarketAnalysisItem {
  id: number;
  trade_date: string;
  analysis_text: string;
  prediction_text: string;
  prediction_summary: PredictionSummary;
  actual_data: ActualData;
  review_text: string;
  model_used: string;
  status: "pending" | "analyzed" | "reviewed";
  created_at: string;
  updated_at: string;
}

export interface MarketAnalysisResponse {
  items: MarketAnalysisItem[];
  total: number;
}

export interface GenerateAnalysisResponse {
  success: boolean;
  message: string;
  data: MarketAnalysisItem | null;
}


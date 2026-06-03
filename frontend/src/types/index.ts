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

export const SOURCE_COLOR_MAP: Record<string, string> = {
  eastmoney: "red",
  cls: "orange",
  tonghuashun: "blue",
  sina: "purple",
  wallstreetcn: "cyan",
  yicai: "green",
  futu: "geekblue",
  xueqiu: "volcano",
  jrj: "gold",
};

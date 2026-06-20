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

export interface ScoredNewsItem {
  title: string;
  source: string;
  url: string;
  publish_time: string;
  impact_score: number;
  impact_category: string;
}

export interface MarketAnalysisItem {
  id: number;
  trade_date: string;
  analysis_text: string;
  prediction_text: string;
  prediction_summary: PredictionSummary;
  actual_data: ActualData;
  review_text: string;
  scored_news: ScoredNewsItem[];
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

export interface SectorItem {
  code: string;
  name: string;
  price: number | null;
  change_pct: number | null;
  change: number | null;
  volume: number | null;
  amount: number | null;
  up_count: number | null;
  down_count: number | null;
  flat_count: number | null;
  leading_stock: string | null;
  leading_stock_code: string | null;
  leading_stock_change_pct: number | null;
}

export interface SectorCapitalFlowItem {
  code: string;
  name: string;
  change_pct: number | null;
  main_net_inflow: number | null;
  main_net_inflow_pct: number | null;
  super_large_net: number | null;
  large_net: number | null;
  medium_net: number | null;
  small_net: number | null;
}

export interface SectorOverviewResponse {
  industry: SectorItem[];
  concept: SectorItem[];
  fetch_time: string;
}

export interface SectorCapitalFlowResponse {
  industry: SectorCapitalFlowItem[];
  concept: SectorCapitalFlowItem[];
  fetch_time: string;
}

export interface SectorHistoryItem {
  code: string;
  name: string;
  price: number | null;
  change_pct: number | null;
  change: number | null;
  volume: number | null;
  amount: number | null;
  up_count: number | null;
  down_count: number | null;
  flat_count: number | null;
  leading_stock: string | null;
  leading_stock_code: string | null;
  leading_stock_change_pct: number | null;
  main_net_inflow: number | null;
  main_net_inflow_pct: number | null;
  super_large_net: number | null;
  large_net: number | null;
  medium_net: number | null;
  small_net: number | null;
}

export interface SectorHistoryDateResponse {
  trade_date: string;
  sector_type: string;
  items: SectorHistoryItem[];
  item_count: number;
}

export interface SectorAggregatedItem {
  code: string;
  name: string;
  avg_change_pct: number | null;
  total_main_net_inflow: number | null;
  avg_main_net_inflow_pct: number | null;
  best_change_pct: number | null;
  worst_change_pct: number | null;
  trading_days: number;
}

export interface SectorHistoryRangeResponse {
  start_date: string;
  end_date: string;
  sector_type: string;
  sectors: SectorAggregatedItem[];
}

export interface SectorTrendPoint {
  date: string;
  change_pct: number | null;
  main_net_inflow: number | null;
  price: number | null;
  volume: number | null;
}

export interface SectorTrendResponse {
  code: string;
  name: string;
  sector_type: string;
  data: SectorTrendPoint[];
}

export interface SectorDatesResponse {
  dates: string[];
}

export interface SectorSnapshotResponse {
  success: boolean;
  message: string;
  trade_date: string | null;
  industry_count: number;
  concept_count: number;
}

export interface AiDailyReportItem {
  id: number;
  trade_date: string;
  report_text: string;
  market_summary: string;
  sector_hot: string;
  capital_flow: string;
  news_sentiment: string;
  outlook: string;
  risk_warning: string;
  model_used: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface AiDailyReportResponse {
  items: AiDailyReportItem[];
  total: number;
}

// --- Stock: Limit Up ---

export interface LimitUpItem {
  code: string;
  name: string;
  price: number | null;
  change_pct: number | null;
  limit_up_amount: number | null;
  turnover_rate: number | null;
  volume: number | null;
  amount: number | null;
  amplitude: number | null;
  first_limit_up_time: string | null;
  last_limit_up_time: string | null;
  limit_up_times: number;
  reason: string;
  sector: string;
  board: string;
}

export interface LimitUpResponse {
  trade_date: string;
  items: LimitUpItem[];
  item_count: number;
  fetch_time: string;
}

// --- Stock: Hot & Sentiment ---

export interface DrivingConcept {
  name: string;
  change_pct: number;
}

export interface StockHotItem {
  code: string;
  name: string;
  price: number | null;
  change_pct: number | null;
  hot_rank: number | null;
  turnover_rate: number | null;
  amount: number | null;
  volume: number | null;
  net_inflow: number | null;
  industry: string;
  driving_concepts: DrivingConcept[];
  concepts: string[];
  source: string;
}

export interface HotStockSource {
  source: string;
  items: StockHotItem[];
}

export interface HotConceptItem {
  name: string;
  sector_type: string;
  change_pct: number | null;
  main_net_inflow: number | null;
  leading_stock: string;
  leading_stock_code: string;
  leading_stock_change_pct: number | null;
}

export interface MarketSentimentResponse {
  up_count: number;
  down_count: number;
  flat_count: number;
  limit_up_count: number;
  limit_down_count: number;
  sentiment_score: number | null;
  hot_stocks: HotStockSource[];
  hot_concepts: HotConceptItem[];
  fetch_time: string;
}

export interface StockOverviewResponse {
  sentiment: MarketSentimentResponse;
  limit_up: LimitUpResponse;
  fetch_time: string;
}

// --- Stock: Daily Snapshot & Watchlist ---

export interface StockDailyItem {
  id: number | null;
  trade_date: string;
  code: string;
  name: string;
  board: string;
  open: number | null;
  close: number | null;
  high: number | null;
  low: number | null;
  prev_close: number | null;
  change_pct: number | null;
  change: number | null;
  volume: number | null;
  amount: number | null;
  turnover_rate: number | null;
  volume_ratio: number | null;
  amplitude: number | null;
  pe_ttm: number | null;
  pe_static: number | null;
  pb: number | null;
  total_market_cap: number | null;
  circulating_market_cap: number | null;
  main_net_inflow: number | null;
  main_net_inflow_pct: number | null;
  super_large_net: number | null;
  large_net: number | null;
  medium_net: number | null;
  small_net: number | null;
  created_at: string | null;
  is_watchlist: boolean | number;
}

export interface StockDailyListResponse {
  trade_date: string;
  items: StockDailyItem[];
  total: number;
}

export interface WatchlistStockItem extends StockDailyItem {
  watchlist_id: number;
  note: string;
  sort_order: number;
  watchlist_created_at: string;
  watchlist_updated_at: string;
}

export interface WatchlistStockResponse {
  items: WatchlistStockItem[];
  total: number;
}

// --- Stock: Recommendation ---

export interface RecommendationItem {
  id: number;
  trade_date: string;
  code: string;
  name: string;
  reason: string;
  strategy: string;
  target_price: number | null;
  stop_loss_price: number | null;
  risk_level: string;
  current_price: number | null;
  buy_low: number | null;
  buy_high: number | null;
  take_profit_price: number | null;
  confidence: number;
  sector: string;
  score: number;
  model_used: string;
  status: string;
  actual_return_pct: number | null;
  actual_exit_date: string | null;
  phase: string;
  // PR1/PR2 估值与风险审计字段
  pe_ttm?: number | null;
  pe_static?: number | null;
  pb?: number | null;
  total_market_cap?: number | null;
  cum_gain_5d?: number | null;
  cum_gain_20d?: number | null;
  cum_gain_60d?: number | null;
  roe?: number | null;
  revenue_growth?: number | null;
  profit_growth?: number | null;
  catalyst?: string | null;
  high_position_risk?: string | null;
  risk_note?: string | null;
  risk_tags?: string | null;
  price_stale?: number | null;
  created_at: string;
  updated_at: string;
}

export interface RecommendationListResponse {
  items: RecommendationItem[];
  total: number;
}

export interface GenerateRecommendationResponse {
  success: boolean;
  message: string;
  data: RecommendationItem[] | null;
  total: number;
}

// --- Stock AI Analysis ---

export interface StockAnalysisPredictionSummary {
  direction?: "up" | "down" | "flat" | string;
  confidence?: number;
  suggested_action?: "watch" | "buy" | "hold" | "avoid" | string;
  target_price?: number | null;
  support_price?: number | null;
  resistance_price?: number | null;
  risk_level?: "low" | "medium" | "high" | string;
  key_factors?: string[];
}

export interface StockDataAvailabilityItem {
  available?: boolean;
  source?: string;
  message?: string;
  missing_fields?: string[];
  count?: number;
  history_count?: number;
}

export interface StockFundamentalContext {
  code?: string;
  name?: string;
  report_date?: string | null;
  roe?: number | null;
  eps?: number | null;
  revenue_growth?: number | null;
  profit_growth?: number | null;
  gross_margin?: number | null;
  net_margin?: number | null;
  data_source?: string;
  missing_fields?: string[];
}

export interface StockCapitalDetailContext {
  trade_date?: string;
  code?: string;
  name?: string;
  north_hold_qty?: number | null;
  north_hold_market_cap?: number | null;
  north_hold_pct?: number | null;
  margin_balance?: number | null;
  margin_buy?: number | null;
  short_sell_volume?: number | null;
  short_balance?: number | null;
  created_at?: string;
}

export interface StockAnalysisContextData {
  concepts?: string[];
  recent_daily?: Record<string, unknown>[];
  recent_recommendations?: Record<string, unknown>[];
  recent_limit_up_analysis?: Record<string, unknown>[];
  technical_indicators?: Record<string, unknown> | null;
  fundamental?: StockFundamentalContext | null;
  capital_detail?: StockCapitalDetailContext | null;
  data_availability?: Record<string, StockDataAvailabilityItem>;
  [key: string]: unknown;
}

export interface StockAnalysisItem {
  id: number;
  trade_date: string;
  code: string;
  name: string;
  board: string;
  analysis_text: string;
  prediction_text: string;
  prediction_summary: StockAnalysisPredictionSummary;
  stock_data: Record<string, unknown>;
  context_data: StockAnalysisContextData;
  recent_news: Record<string, unknown>[];
  model_used: string;
  status: "pending" | "completed" | "failed" | string;
  created_at: string;
  updated_at: string;
}

export interface StockAnalysisResponse {
  items: StockAnalysisItem[];
  total: number;
}

export interface GenerateStockAnalysisResponse {
  success: boolean;
  message: string;
  data: StockAnalysisItem | null;
}

// --- Sector AI Analysis ---

export interface SectorPredictionItem {
  name: string;
  direction: "up" | "down" | "flat";
  confidence: number;
  heat: number;
  key_drivers: string[];
  risk_level: "low" | "medium" | "high";
}

export interface SectorPredictionSummary {
  predicted_active_sectors: SectorPredictionItem[];
  overall_rotation: string;
  confidence: number;
  key_factors: string[];
  risk_level: "low" | "medium" | "high";
}

export interface SectorActualData {
  trade_date: string;
  sector_type: string;
  top_gainers: { name: string; change_pct: number | null; main_net_inflow: number | null }[];
  top_losers: { name: string; change_pct: number | null; main_net_inflow: number | null }[];
  fetch_time: string;
}

export interface SectorAnalysisItem {
  id: number;
  trade_date: string;
  sector_type: string;
  analysis_text: string;
  prediction_text: string;
  prediction_summary: SectorPredictionSummary;
  actual_data: SectorActualData;
  review_text: string;
  scored_news: ScoredNewsItem[];
  trend_data: Record<string, unknown>;
  model_used: string;
  status: "pending" | "analyzed" | "reviewed";
  created_at: string;
  updated_at: string;
}

export interface SectorAnalysisResponse {
  items: SectorAnalysisItem[];
  total: number;
}

export interface GenerateSectorAnalysisResponse {
  success: boolean;
  message: string;
  data: Record<string, unknown> | SectorAnalysisItem | null;
}

export interface SectorAnalysisTaskStatus {
  active: boolean;
  status: "idle" | "running" | "completed" | "failed";
  trade_date: string;
  sector_type?: string | null;
  stage?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
}

// --- Limit Up AI Analysis ---

export interface LimitUpAnalysisItem {
  id: number;
  trade_date: string;
  code: string;
  name: string;
  price: number | null;
  change_pct: number | null;
  turnover_rate: number | null;
  amount: number | null;
  limit_up_times: number;
  sector: string;
  board: string;
  stock_type: "limit_up" | "broken";
  first_limit_up_time: string | null;
  last_limit_up_time: string | null;
  limit_up_amount: number | null;
  ai_reason: string;
  ai_tomorrow_judge: string;
  ai_tomorrow_prob: string;
  ai_confidence: number;
  ai_key_factors: string[];
  model_used: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface LimitUpAnalysisResponse {
  trade_date: string;
  items: LimitUpAnalysisItem[];
  total: number;
}


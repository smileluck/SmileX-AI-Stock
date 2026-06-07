from pydantic import BaseModel, model_validator


STRATEGY_TYPES = {
    "stock_analysis": {"label": "个股分析策略", "description": "对个股进行多维度综合分析，涵盖基本面、技术面、消息面等"},
    "sector_analysis": {"label": "行业分析策略", "description": "分析行业板块趋势，识别板块轮动和资金流向"},
    "market_analysis": {"label": "大盘分析策略", "description": "分析大盘走势，预测市场方向和风险等级"},
    "stock_review": {"label": "个股复盘策略", "description": "复盘个股历史表现，评估预测准确性和改进方向"},
    "stock_recommendation": {"label": "个股推荐策略", "description": "基于多因子模型推荐潜力个股"},
}


class WeightConfig(BaseModel):
    fundamentals: float = 30
    technicals: float = 25
    news: float = 20
    capital_flow: float = 15
    sentiment: float = 10

    @model_validator(mode="after")
    def weights_sum_to_100(self):
        total = self.fundamentals + self.technicals + self.news + self.capital_flow + self.sentiment
        if abs(total - 100) > 0.01:
            raise ValueError(f"权重总和必须为100，当前为{total}")
        return self


class StrategyCreateRequest(BaseModel):
    name: str
    type: str
    description: str = ""
    prompt_template: str = ""
    weight_config: WeightConfig = WeightConfig()
    news_enabled: bool = True
    news_count: int = 15
    output_format: dict = {}
    is_enabled: bool = True
    model_override: str | None = None


class StrategyUpdateRequest(BaseModel):
    name: str | None = None
    type: str | None = None
    description: str | None = None
    prompt_template: str | None = None
    weight_config: WeightConfig | None = None
    news_enabled: bool | None = None
    news_count: int | None = None
    output_format: dict | None = None
    is_enabled: bool | None = None
    model_override: str | None = None


class StrategyItem(BaseModel):
    id: int
    name: str
    type: str
    description: str
    prompt_template: str
    weight_config: WeightConfig
    news_enabled: bool
    news_count: int
    output_format: dict
    is_enabled: bool
    is_default: bool
    sort_order: int
    model_override: str | None
    created_at: str
    updated_at: str


class StrategyListResponse(BaseModel):
    items: list[StrategyItem]
    total: int


class StrategyTestRequest(BaseModel):
    test_input: str = ""


class StrategyTypeInfo(BaseModel):
    key: str
    label: str
    description: str

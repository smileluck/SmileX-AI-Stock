from sources.base import BaseSource
from sources.eastmoney import EastMoneySource
from sources.eastmoney_global import EastMoneyGlobalSource
from sources.cls import ClsSource
from sources.tonghuashun import TongHuaShunSource
from sources.sina import SinaSource
from sources.wallstreetcn import WallStreetCnSource
from sources.yicai import YicaiSource
from sources.futu import FutuSource
from sources.xueqiu import XueqiuSource
from sources.jrj import JrjSource

SOURCE_LABELS: dict[str, str] = {
    "eastmoney": "东方财富",
    "eastmoney_global": "7×24全球",
    "cls": "财联社",
    "tonghuashun": "同花顺",
    "sina": "新浪财经",
    "wallstreetcn": "华尔街见闻",
    "yicai": "第一财经",
    "futu": "富途快讯",
    "xueqiu": "雪球",
    "jrj": "金融界",
}

SOURCE_REGISTRY: dict[str, type[BaseSource]] = {
    "eastmoney": EastMoneySource,
    "eastmoney_global": EastMoneyGlobalSource,
    "cls": ClsSource,
    "tonghuashun": TongHuaShunSource,
    "sina": SinaSource,
    "wallstreetcn": WallStreetCnSource,
    "yicai": YicaiSource,
    "futu": FutuSource,
    "xueqiu": XueqiuSource,
    "jrj": JrjSource,
}

from sources.base import BaseSource
from sources.eastmoney import EastMoneySource
from sources.eastmoney_global import EastMoneyGlobalSource
from sources.cls import (
    ClsSource,
    ClsRedSource,
    ClsAnnouncementSource,
    ClsWatchSource,
    ClsHkUsSource,
    ClsFundSource,
    ClsRemindSource,
)
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
    "cls_red": "加红",
    "cls_announcement": "公司",
    "cls_watch": "看盘",
    "cls_hk_us": "港美股",
    "cls_fund": "基金",
    "cls_remind": "提醒",
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
    "cls_red": ClsRedSource,
    "cls_announcement": ClsAnnouncementSource,
    "cls_watch": ClsWatchSource,
    "cls_hk_us": ClsHkUsSource,
    "cls_fund": ClsFundSource,
    "cls_remind": ClsRemindSource,
    "tonghuashun": TongHuaShunSource,
    "sina": SinaSource,
    "wallstreetcn": WallStreetCnSource,
    "yicai": YicaiSource,
    "futu": FutuSource,
    "xueqiu": XueqiuSource,
    "jrj": JrjSource,
}

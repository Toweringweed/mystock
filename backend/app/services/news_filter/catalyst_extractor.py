"""L0 催化剂分类器 — 纯正则,7 类 + other 兜底

设计目标:在 LLM 调用之前,用规则快速给资讯打上 catalyst_type 标签,
为 L1.5 LLM 抽取节省成本(如已知是 earnings,prompt 可更聚焦)、
也用于详情页右上角 badge 即时显示。

7 类:
  merger      并购/收购/重组/股权变更
  earnings    业绩/财报/预告/快报/营收/利润
  regulatory  监管/立案/处罚/合规/退市
  contract    合同/订单/中标/签约
  sanction    制裁/禁令/限制/出口管制/实体清单
  research    券商研报/调研/上调/下调评级
  capacity    扩产/产能/投产/量产/扩建/工厂

返回:命中类别名(如多类命中,按优先级取第一个),无命中返回 "other"
优先级:sanction > regulatory > merger > earnings > contract > capacity > research > other
"""
from __future__ import annotations

import re
from typing import Final

# 优先级从高到低 — 同时命中多类时取靠前者
_RULES: Final[list[tuple[str, list[str]]]] = [
    (
        "sanction",
        [
            r"制裁", r"禁令", r"出口管制", r"实体清单", r"entity\s*list",
            r"sanction", r"export\s+control", r"unverified\s+list",
            r"BIS|商务部.{0,8}(管制|限制)",
        ],
    ),
    (
        "regulatory",
        [
            r"立案(?:调查|侦查)?", r"行政处罚", r"违规(?:被罚|处罚)",
            r"\*?ST\b(?=\s|股|公司|$)", r"退市风险", r"暂停上市", r"终止上市",
            r"投资者保护", r"违规担保", r"信息披露违法",
            r"涉嫌(违规|违法|犯罪)", r"被(警示|监管|采取措施)",
            r"(SEC|FTC|DOJ).{0,15}(charge|probe|investigation|fine)",
        ],
    ),
    (
        "merger",
        [
            r"并购", r"收购", r"换股", r"重大资产重组", r"借壳",
            r"控股权(?:变更|转让)", r"实控人(?:变更|易主)",
            r"要约收购", r"私有化", r"分拆上市",
            r"acquir(?:e|ed|ition)", r"merger", r"buyout",
        ],
    ),
    (
        "earnings",
        [
            r"业绩(?:预告|快报|预增|预减|预亏|预盈)", r"年报", r"半年报", r"季报",
            r"营收(?:增长|下降|同比)", r"净利(?:增长|下降|同比)",
            r"扭亏为盈", r"由盈转亏",
            r"earnings\s+(?:beat|miss|surprise)", r"revenue\s+(?:grew|fell|up|down)",
            r"Q[1-4]\s+(?:results|earnings)", r"financial\s+report",
        ],
    ),
    (
        "contract",
        [
            r"中标", r"签约", r"签订(?:战略)?(?:合同|协议)",
            r"重大订单", r"框架协议", r"采购协议",
            r"\d+(?:\.\d+)?\s*(?:亿|万).{0,8}订单",
            r"contract\s+(?:awarded|signed|won)", r"deal\s+with",
            r"strategic\s+partnership",
        ],
    ),
    (
        "capacity",
        [
            r"扩产", r"产能(?:释放|提升|扩张)", r"投产", r"量产",
            r"新建工厂", r"扩建产线", r"产线投运", r"产能利用率",
            r"capacity\s+(?:expansion|ramp|increase)",
            r"(?:fab|plant|factory).{0,8}(?:open|launch|build)",
        ],
    ),
    (
        "research",
        [
            r"(?:首次|维持|上调|下调).{0,4}(?:买入|增持|中性|减持|卖出)?\s*评级",
            r"目标价", r"评级.{0,4}(上调|下调|首次)",
            r"调研纪要", r"分析师会议",
            r"(upgrade|downgrade)\s+to", r"price\s+target", r"rating\s+(?:cut|raised)",
            r"analyst\s+(?:initiates|reiterate)",
        ],
    ),
]

# 预编译,case-insensitive
_COMPILED: Final[list[tuple[str, list[re.Pattern]]]] = [
    (cat, [re.compile(p, re.IGNORECASE) for p in patterns])
    for cat, patterns in _RULES
]


CATALYST_LABELS_ZH: Final[dict[str, str]] = {
    "sanction": "制裁",
    "regulatory": "监管",
    "merger": "并购",
    "earnings": "业绩",
    "contract": "合同",
    "capacity": "产能",
    "research": "研报",
    "other": "其他",
}


def extract_catalyst(title: str | None, content: str | None = None) -> str:
    """从标题 + 正文中识别催化剂类别。

    标题命中权重大于正文(命中即返回);如标题未命中,正文搜首 800 字。
    """
    if not title and not content:
        return "other"

    title_text = title or ""
    body_text = (content or "")[:800]

    # Pass 1: 标题命中(优先级)
    for cat, patterns in _COMPILED:
        for p in patterns:
            if p.search(title_text):
                return cat

    # Pass 2: 正文命中(同优先级顺序)
    for cat, patterns in _COMPILED:
        for p in patterns:
            if p.search(body_text):
                return cat

    return "other"

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from oracle.config import Settings, settings
from oracle.models import Signal


EASTMONEY_NEWS_URL = "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns"
EASTMONEY_INDEX_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get"
CN_MARKET_KEYWORDS = (
    "中国",
    "国务院",
    "发改委",
    "央行",
    "证监会",
    "上交所",
    "深交所",
    "北交所",
    "A股",
    "沪深",
    "地产",
    "专项债",
    "社融",
    "降准",
    "人民币",
    "期货",
    "铁矿",
    "螺纹",
    "半导体",
)
TERM_TRANSLATIONS = {
    "国务院": "State Council",
    "发改委": "NDRC",
    "央行": "PBOC",
    "中国人民银行": "PBOC",
    "证监会": "CSRC",
    "上交所": "Shanghai Stock Exchange",
    "深交所": "Shenzhen Stock Exchange",
    "新华社": "Xinhua",
    "中国证券报": "China Securities Journal",
    "基本公共服务": "basic public services",
    "常住地": "place of residence",
    "中韩半导体ETF": "China-Korea Semiconductor ETF",
    "全球芯片LOF": "Global Chip LOF",
    "重点监控": "heightened market surveillance",
    "MLF": "MLF",
    "中期借贷便利": "medium-term lending facility",
    "人工智能": "artificial intelligence",
    "具身智能": "embodied AI",
    "稳就业": "stabilize employment",
    "稳企业": "stabilize companies",
    "稳市场": "stabilize markets",
    "稳预期": "stabilize expectations",
    "降准": "reserve requirement ratio cut",
    "专项债": "special local-government bonds",
    "地产": "property sector",
    "半导体": "semiconductors",
    "非法跨境证券期货基金": "illegal cross-border securities, futures, and fund activity",
}


def _minutes_since(value: datetime) -> int:
    now = datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return max(0, round((now - value.astimezone(timezone.utc)).total_seconds() / 60))


def _parse_eastmoney_time(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    return parsed.replace(tzinfo=timezone(timedelta(hours=8)))


def _theme_from_text(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ("台海", "台湾", "南海", "军演", "制裁")):
        return "geopolitical_risk"
    if any(word in lowered for word in ("btc", "bitcoin", "比特币", "加密")):
        return "btc_asia_momentum"
    if any(word in lowered for word in ("汇率", "外资", "跨境", "避险", "下跌")):
        return "risk_off_china"
    return "china_stimulus"


def english_market_brief(headline_zh: str, body_zh: str | None, theme: str, source: str) -> str:
    text = f"{headline_zh}\n{body_zh or ''}"
    matched_terms = []
    for zh, en in TERM_TRANSLATIONS.items():
        if zh in text and en not in matched_terms:
            matched_terms.append(en)

    if "开展" in text and ("MLF" in text or "中期借贷便利" in text):
        action = "liquidity operation"
    elif "印发" in text or "实施意见" in text:
        action = "policy document release"
    elif "重点监控" in text or "自律监管" in text:
        action = "regulatory surveillance update"
    elif "回应" in text or "新闻发布会" in text:
        action = "official policy briefing"
    elif "走强" in text or "+" in text:
        action = "live market strength"
    elif "走弱" in text or "下跌" in text:
        action = "live market weakness"
    else:
        action = "Mandarin market signal"

    impact_path = {
        "china_stimulus": "relevant to China growth, liquidity, A-share risk appetite, and China-linked Polymarket pricing",
        "risk_off_china": "relevant to RMB pressure, defensive rotation, and China risk-off repricing",
        "geopolitical_risk": "relevant to Taiwan Strait risk, safe-haven demand, and geopolitical prediction markets",
        "btc_asia_momentum": "relevant to Asia-session crypto positioning and BTC prediction markets",
    }.get(theme, "relevant to China-linked prediction-market repricing")

    term_text = ", ".join(matched_terms[:5]) if matched_terms else "China policy or market structure"
    return f"{source} reports a {action} involving {term_text}; this is {impact_path}."


def _asset_link(theme: str) -> str:
    return {
        "china_stimulus": "china_policy_a_shares_commodities",
        "risk_off_china": "china_fx_equities_rates",
        "geopolitical_risk": "taiwan_strait_safe_haven_assets",
        "btc_asia_momentum": "btc_asia_session",
    }.get(theme, "china_macro")


class LiveMandarinSourceClient:
    def __init__(self, config: Settings = settings) -> None:
        self.config = config

    def _open_json(self, url: str, params: dict[str, Any]) -> Any:
        query = urlencode({key: value for key, value in params.items() if value is not None})
        request = Request(
            f"{url}?{query}",
            headers={"User-Agent": "MandarinMarketOracle/0.3"},
        )
        with urlopen(request, timeout=self.config.request_timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

    def fetch_signals(self, limit: int = 6) -> list[Signal]:
        signals: list[Signal] = []
        for fetcher in (self.eastmoney_news, self.eastmoney_index_tape):
            try:
                signals.extend(fetcher())
            except Exception:
                continue
        signals.sort(key=lambda item: item.freshness_minutes)
        return signals[:limit]

    def eastmoney_news(self) -> list[Signal]:
        payload = self._open_json(
            EASTMONEY_NEWS_URL,
            {
                "client": "web",
                "biz": "web_news_col",
                "column": "345",
                "order": 1,
                "needInteractData": 0,
                "page_index": 1,
                "page_size": 8,
                "types": 1,
                "req_trace": int(time.time() * 1000),
            },
        )
        records = ((payload.get("data") or {}).get("list") or []) if isinstance(payload, dict) else []
        signals: list[Signal] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            title = str(record.get("title") or "").strip()
            summary = str(record.get("summary") or "").strip()
            if not title:
                continue
            combined_text = f"{title}\n{summary}"
            if not any(keyword in combined_text for keyword in CN_MARKET_KEYWORDS):
                continue
            timestamp = _parse_eastmoney_time(record.get("showTime"))
            theme = _theme_from_text(combined_text)
            signals.append(
                Signal(
                    id=f"em-news-{record.get('code') or abs(hash(title))}",
                    source=f"Eastmoney Finance · {record.get('mediaName') or 'news'}",
                    source_type="public_news_api",
                    language="zh",
                    headline_zh=title,
                    headline_en=english_market_brief(title, summary, theme, str(record.get("mediaName") or "Eastmoney")),
                    theme=theme,
                    asset_link=_asset_link(theme),
                    credibility=0.86,
                    velocity=0.62,
                    freshness_minutes=_minutes_since(timestamp),
                    evidence=[
                        f"Public Eastmoney news API timestamp: {record.get('showTime')}",
                        f"Source URL: {record.get('uniqueUrl') or record.get('url')}",
                        summary[:260] or title,
                    ],
                    risk_flags=[
                        "News impact requires cross-source confirmation before aggressive sizing",
                        "System emits research views only; it does not place orders",
                    ],
                )
            )
        return signals

    def eastmoney_index_tape(self) -> list[Signal]:
        payload = self._open_json(
            EASTMONEY_INDEX_URL,
            {
                "fltt": 2,
                "secids": "1.000001,0.399001,0.399006",
                "fields": "f12,f14,f2,f3,f4,f6",
            },
        )
        rows = ((payload.get("data") or {}).get("diff") or []) if isinstance(payload, dict) else []
        signals: list[Signal] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("f14") or row.get("f12") or "A-share index")
            pct = float(row.get("f3") or 0)
            theme = "risk_off_china" if pct < -0.8 else "china_stimulus"
            direction = "走弱" if pct < 0 else "走强"
            headline_zh = f"{name}实时{direction} {pct:+.2f}%"
            signals.append(
                Signal(
                    id=f"em-index-{row.get('f12')}",
                    source="Eastmoney Push2 · A-share index tape",
                    source_type="public_market_data_api",
                    language="zh",
                    headline_zh=headline_zh,
                    headline_en=english_market_brief(
                        headline_zh,
                        f"Last={row.get('f2')}; change={row.get('f4')}; turnover={row.get('f6')}",
                        theme,
                        "Eastmoney Push2",
                    ),
                    theme=theme,
                    asset_link=_asset_link(theme),
                    credibility=0.9,
                    velocity=min(0.95, 0.35 + abs(pct) / 3),
                    freshness_minutes=5,
                    evidence=[
                        "Eastmoney Push2 public market-data endpoint",
                        f"Index={name}; last={row.get('f2')}; change={row.get('f4')}; pct={pct:+.2f}%",
                        f"Turnover={row.get('f6')}",
                    ],
                    risk_flags=[
                        "Market tape is live but not a standalone causal explanation",
                        "System emits research views only; it does not place orders",
                    ],
                )
            )
        return signals

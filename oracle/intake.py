from __future__ import annotations

from datetime import datetime, timezone

from oracle.engine import OracleService
from oracle.models import Market, Signal, SignalIntakeRequest, SignalIntakeResponse
from oracle.repository import DataRepository
from oracle.sources import english_market_brief


THEME_KEYWORDS = {
    "china_stimulus": ["刺激", "地产", "铁矿", "螺纹", "专项债", "降准", "社融"],
    "risk_off_china": ["汇率", "离岸人民币", "高股息", "中特估", "避险", "防御"],
    "geopolitical_risk": ["台海", "台湾", "南海", "冲突", "制裁", "军演"],
    "btc_asia_momentum": ["btc", "比特币", "永续", "资金费率", "crypto", "币圈"],
}


def infer_theme(text: str) -> str:
    lowered = text.lower()
    for theme, keywords in THEME_KEYWORDS.items():
        if any(keyword.lower() in lowered for keyword in keywords):
            return theme
    return "china_stimulus"


def default_asset_link(theme: str) -> str:
    return {
        "china_stimulus": "iron_ore_rebar_property",
        "risk_off_china": "equities_rates_fx",
        "geopolitical_risk": "gold_oil_usd_asia_equities",
        "btc_asia_momentum": "btc",
    }.get(theme, "china_macro")


def normalize_signal(request: SignalIntakeRequest) -> Signal:
    theme = request.theme or infer_theme(f"{request.headline_zh}\n{request.body_zh or ''}")
    market_line = (
        f"Mapped to Polymarket market: {request.market_question}"
        if request.market_question
        else "Agent must map the source to a Polymarket contract before preparing a research view"
    )
    evidence = request.evidence or [
        f"Human-curated Mandarin source: {request.source}",
        "Signal submitted through controlled intake with source attribution",
        market_line,
    ]
    risk_flags = request.risk_flags or [
        "Human-curated signal requires independent confirmation",
        "Research-only view; no real-money order execution",
    ]
    stable_id = datetime.now(timezone.utc).strftime("usr-%Y%m%d%H%M%S")
    return Signal(
        id=stable_id,
        source=request.source,
        source_type=request.source_type,
        language="zh",
        headline_zh=request.headline_zh,
        headline_en=english_market_brief(request.headline_zh, request.body_zh, theme, request.source),
        theme=theme,
        asset_link=request.asset_link or default_asset_link(theme),
        credibility=request.credibility if request.credibility is not None else 0.72,
        velocity=request.velocity if request.velocity is not None else 0.64,
        freshness_minutes=request.freshness_minutes,
        evidence=evidence,
        risk_flags=risk_flags,
    )


def normalize_market(request: SignalIntakeRequest, theme: str) -> Market | None:
    if not request.market_slug or not request.market_question:
        return None
    if request.market_yes_price is None:
        raise ValueError("A real Polymarket yes price is required; 0.5 fallback pricing is disabled.")
    yes_price = request.market_yes_price
    return Market(
        id=f"usr-market-{request.market_slug}",
        slug=request.market_slug,
        question=request.market_question,
        category=request.market_category or "polymarket-live",
        matched_theme=theme,
        yes_price=yes_price,
        no_price=round(1 - yes_price, 4),
        liquidity_usdc=request.market_liquidity_usdc or 0,
        volume_usdc=request.market_volume_usdc or 0,
        expiry=request.market_expiry or datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc),
    )


class SignalIntakeService:
    def __init__(self, repository: DataRepository | None = None) -> None:
        self.repository = repository or DataRepository()

    def submit(self, request: SignalIntakeRequest) -> SignalIntakeResponse:
        signal = normalize_signal(request)
        market = normalize_market(request, signal.theme)
        if market:
            self.repository.append_user_market(market)
        self.repository.append_user_signal(signal)
        recommendation = OracleService(repository=self.repository).recommendations(signal_id=signal.id)[0]
        return SignalIntakeResponse(signal=signal, recommendation=recommendation)

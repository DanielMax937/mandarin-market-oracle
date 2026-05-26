from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from oracle.config import Settings, settings
from oracle.llm_reasoning import LLMReasoningClient, PROMPT_VERSION, SYSTEM_PROMPT, user_prompt
from oracle.models import (
    AgentMetadata,
    Decision,
    Direction,
    Market,
    Receipt,
    Recommendation,
    Signal,
    Snapshot,
)
from oracle.polymarket import PolymarketClient, PolymarketSearchResult
from oracle.repository import DataRepository


def canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "0x" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def freshness_score(minutes: int) -> float:
    return max(0.1, min(1.0, 1 - minutes / 180))


def estimate_agent_probability(signal: Signal, market: Market) -> float:
    signal_strength = (
        signal.credibility * 0.42
        + signal.velocity * 0.34
        + freshness_score(signal.freshness_minutes) * 0.24
    )
    risk_penalty = min(len(signal.risk_flags) * 0.025, 0.09)
    liquidity_dampener = 0.02 if market.liquidity_usdc > 150_000 else 0
    probability = market.yes_price + (signal_strength - 0.55) * 0.46
    probability = probability - risk_penalty + liquidity_dampener
    return max(0.05, min(0.92, probability))


def decide(signal: Signal, market: Market, config: Settings = settings) -> Decision:
    config.validate_compliance_boundary()
    agent_probability = estimate_agent_probability(signal, market)
    market_probability = market.yes_price
    edge = agent_probability - market_probability
    conviction = (
        signal.credibility * 0.55
        + signal.velocity * 0.30
        + freshness_score(signal.freshness_minutes) * 0.15
    )
    capped_kelly = min(max(abs(edge) * conviction, 0), config.max_position_pct)
    direction = Direction.YES if edge > 0.055 else Direction.NO if edge < -0.055 else Direction.WAIT
    risk_unit_size = config.bankroll_usdc * capped_kelly if direction != Direction.WAIT else 0
    impact_path = {
        "china_stimulus": "policy expectation -> mainland risk appetite -> China-linked prediction-market repricing",
        "risk_off_china": "defensive rotation -> CNH/rates stress -> global macro probability repricing",
        "geopolitical_risk": "Mandarin public velocity -> safe-haven demand -> geopolitical market repricing",
        "btc_asia_momentum": "Asia-session positioning -> perp funding and spot bid -> BTC event probability repricing",
    }.get(signal.theme, "Mandarin signal -> event probability repricing")
    if direction == Direction.WAIT:
        rationale = (
            f"The signal maps to {market.slug}, but edge is only {edge:.1%}. "
            f"Impact path: {impact_path}. The agent waits because rumor and confirmation risk "
            "are not compensated by the current market price."
        )
    else:
        rationale = (
            f"The signal maps to {market.slug}. Impact path: {impact_path}. "
            f"Market implies {market_probability:.1%}; the agent estimates {agent_probability:.1%}, "
            f"creating a {abs(edge):.1%} edge after credibility, velocity, freshness, and risk-flag penalties."
        )
    return Decision(
        direction=direction,
        market_probability=round(market_probability, 4),
        agent_probability=round(agent_probability, 4),
        edge=round(edge, 4),
        conviction=round(conviction, 4),
        risk_unit_size=round(risk_unit_size, 2),
        rationale=rationale,
    )


def decision_trace(signal: Signal, market: Market, decision: Decision, config: Settings = settings) -> dict[str, Any]:
    fresh = freshness_score(signal.freshness_minutes)
    signal_strength = (
        signal.credibility * 0.42
        + signal.velocity * 0.34
        + fresh * 0.24
    )
    risk_penalty = min(len(signal.risk_flags) * 0.025, 0.09)
    liquidity_dampener = 0.02 if market.liquidity_usdc > 150_000 else 0
    raw_agent_probability = market.yes_price + (signal_strength - 0.55) * 0.46
    adjusted_agent_probability = raw_agent_probability - risk_penalty + liquidity_dampener
    conviction = (
        signal.credibility * 0.55
        + signal.velocity * 0.30
        + fresh * 0.15
    )
    raw_edge = adjusted_agent_probability - market.yes_price
    capped_kelly = min(max(abs(raw_edge) * conviction, 0), config.max_position_pct)
    threshold = 0.055
    return {
        "formula": "market_yes + (signal_strength - 0.55) * 0.46 - risk_penalty + liquidity_adjustment",
        "inputs": [
            {
                "label": "Credibility",
                "value": round(signal.credibility, 4),
                "weight": 0.42,
                "why": "Source trust and attribution quality.",
            },
            {
                "label": "Velocity",
                "value": round(signal.velocity, 4),
                "weight": 0.34,
                "why": "How quickly the Mandarin signal is moving through market channels.",
            },
            {
                "label": "Freshness",
                "value": round(fresh, 4),
                "weight": 0.24,
                "why": f"{signal.freshness_minutes} minutes since source timestamp.",
            },
        ],
        "adjustments": [
            {
                "label": "Risk penalty",
                "value": round(-risk_penalty, 4),
                "why": f"{len(signal.risk_flags)} caveats reduce aggressive sizing.",
            },
            {
                "label": "Liquidity adjustment",
                "value": round(liquidity_dampener, 4),
                "why": "More liquid markets get a small confidence adjustment."
                if liquidity_dampener
                else "No liquidity adjustment below the 150k USDC threshold.",
            },
        ],
        "outputs": {
            "signal_strength": round(signal_strength, 4),
            "raw_agent_probability": round(raw_agent_probability, 4),
            "adjusted_agent_probability": round(max(0.05, min(0.92, adjusted_agent_probability)), 4),
            "market_probability": decision.market_probability,
            "edge": decision.edge,
            "edge_threshold": threshold,
            "conviction": round(conviction, 4),
            "kelly_fraction_capped": round(capped_kelly, 4),
            "max_position_pct": config.max_position_pct,
            "direction_rule": "YES if edge > 5.5%; NO if edge < -5.5%; otherwise WAIT.",
        },
    }


def matching_market(signal: Signal, markets: list[Market]) -> Market:
    for market in markets:
        if market.matched_theme == signal.theme:
            return market
    raise LookupError(f"No market found for theme {signal.theme}")


def market_query(signal: Signal) -> str:
    return {
        "china_stimulus": "china economy",
        "risk_off_china": "china stocks",
        "geopolitical_risk": "china taiwan",
        "btc_asia_momentum": "bitcoin",
    }.get(signal.theme, "china")


def market_from_search_result(signal: Signal, result: PolymarketSearchResult) -> Market | None:
    if not result.slug or not (result.question or result.title) or result.yes_price is None:
        return None
    if result.closed is True or result.active is False:
        return None
    expiry = result.expiry
    if expiry is None:
        return None
    yes_price = float(result.yes_price)
    return Market(
        id=f"polymarket-{result.id or result.slug}",
        slug=result.slug,
        question=result.question or result.title or result.slug,
        category=result.category or "polymarket-live",
        matched_theme=signal.theme,
        yes_price=round(yes_price, 4),
        no_price=round(1 - yes_price, 4),
        liquidity_usdc=float(result.liquidity or 0),
        volume_usdc=float(result.volume or 0),
        expiry=expiry,
    )


def build_receipt(
    signal: Signal,
    market: Market,
    decision: Decision,
    config: Settings = settings,
) -> Receipt:
    evidence_payload = {
        "signal_id": signal.id,
        "headline_zh": signal.headline_zh,
        "headline_en": signal.headline_en,
        "evidence": signal.evidence,
        "risk_flags": signal.risk_flags,
    }
    recommendation_payload = {
        "signal_id": signal.id,
        "market_slug": market.slug,
        "direction": decision.direction.value,
        "market_probability": decision.market_probability,
        "agent_probability": decision.agent_probability,
        "edge": decision.edge,
        "risk_unit_size": decision.risk_unit_size,
    }
    recommendation_hash = canonical_hash(recommendation_payload)
    return Receipt(
        receipt_id=f"arc-testnet-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{signal.id}",
        network=config.provenance_network,
        tx_hash=None,
        market_slug=market.slug,
        signal_id=signal.id,
        direction=decision.direction,
        market_probability=decision.market_probability,
        agent_probability=decision.agent_probability,
        edge=decision.edge,
        risk_unit_size=decision.risk_unit_size,
        evidence_hash=canonical_hash(evidence_payload),
        recommendation_hash=recommendation_hash,
    )


class OracleService:
    def __init__(
        self,
        repository: DataRepository | None = None,
        config: Settings = settings,
        polymarket_client: PolymarketClient | None = None,
        reasoning_client: LLMReasoningClient | None = None,
    ) -> None:
        self.repository = repository or DataRepository()
        self.config = config
        self.polymarket_client = polymarket_client or PolymarketClient(config)
        self.reasoning_client = reasoning_client or LLMReasoningClient(config)

    def resolve_market(
        self,
        signal: Signal,
        markets: list[Market],
        live_cache: dict[str, Market | None] | None = None,
    ) -> Market:
        try:
            return matching_market(signal, markets)
        except LookupError:
            pass

        query = market_query(signal)
        if live_cache is not None and query in live_cache:
            market = live_cache[query]
            if market:
                return market
            raise LookupError(f"No live Polymarket market with a real price found for {signal.theme}")

        for result in self.polymarket_client.search(query, limit=10):
            market = market_from_search_result(signal, result)
            if market:
                if live_cache is not None:
                    live_cache[query] = market
                return market
        if live_cache is not None:
            live_cache[query] = None
        raise LookupError(f"No live Polymarket market with a real price found for {signal.theme}")

    def recommendations(self, signal_id: str | None = None, include_llm: bool = False) -> list[Recommendation]:
        signals = self.repository.signals()
        if signal_id:
            signals = [signal for signal in signals if signal.id == signal_id]
            if not signals:
                raise LookupError(f"Unknown signal id: {signal_id}")

        markets = self.repository.markets()
        live_cache: dict[str, Market | None] = {}
        recommendations: list[Recommendation] = []
        for signal in signals:
            try:
                market = self.resolve_market(signal, markets, live_cache)
            except LookupError:
                if signal_id:
                    raise
                continue
            decision = decide(signal, market, self.config)
            llm_reasoning = self.reasoning_client.explain(signal, market, decision) if include_llm else None
            receipt = build_receipt(signal, market, decision, self.config)
            recorded_receipt = self.repository.receipt_for(receipt.recommendation_hash)
            if recorded_receipt:
                receipt = recorded_receipt
            recommendations.append(
                Recommendation(
                    signal=signal,
                    market=market,
                    decision=decision,
                    decision_trace=decision_trace(signal, market, decision, self.config),
                    llm_reasoning=llm_reasoning,
                    receipt=receipt,
                )
            )
        return recommendations

    def explain_recommendation(self, signal_id: str) -> Recommendation:
        return self.recommendations(signal_id=signal_id, include_llm=True)[0]

    def agent_metadata(self) -> AgentMetadata:
        metadata = self.reasoning_client.metadata()
        return AgentMetadata(
            mode="deterministic pricing + OpenAI LLM reasoning",
            llm_enabled=bool(metadata["llm_enabled"]),
            provider=str(metadata["provider"]),
            model=str(metadata["model"]),
            base_url=str(metadata["base_url"]),
            prompt_version=str(metadata["prompt_version"]),
        )

    def prompt_config(self, signal_id: str | None = None) -> dict[str, Any]:
        sample = None
        try:
            signals = self.repository.signals()
            if signal_id:
                signals = [signal for signal in signals if signal.id == signal_id]
            markets = self.repository.markets()
            live_cache: dict[str, Market | None] = {}
            for signal in signals:
                try:
                    market = self.resolve_market(signal, markets, live_cache)
                except LookupError:
                    continue
                decision = decide(signal, market, self.config)
                sample = user_prompt(signal, market, decision)
                break
        except Exception:
            sample = "Prompt sample unavailable until a live signal maps to a priced Polymarket market."
        return {
            "prompt_version": PROMPT_VERSION,
            "system_prompt": SYSTEM_PROMPT,
            "user_prompt_template": user_prompt.__doc__ or "See oracle/llm_reasoning.py:user_prompt.",
            "sample_user_prompt": sample,
        }

    def snapshot(self) -> Snapshot:
        return Snapshot(
            execution_mode=self.config.execution_mode,
            provenance_network=self.config.provenance_network,
            verification_contract=getattr(self.config, "arc_reasoning_registry_address", None),
            agent=self.agent_metadata(),
            bankroll_usdc=self.config.bankroll_usdc,
            recommendations=self.recommendations(),
        )

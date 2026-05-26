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
    MarketCandidate,
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


THEME_MARKET_RULES: dict[str, dict[str, Any]] = {
    "china_stimulus": {
        "queries": ("china gdp", "china economic growth", "china economy"),
        "anchors": ("china", "chinese"),
        "preferred": ("gdp", "growth", "economic growth", "economy", "tariff", "trade", "yuan", "renminbi"),
        "excluded": ("taiwan", "invade", "invasion", "blockade", "gta", "bitcoin", "btc", "crypto"),
        "min_score": 3.0,
        "strong_score": 5.8,
        "candidate_min_score": 2.0,
    },
    "risk_off_china": {
        "queries": ("hang seng", "hsi", "china yuan", "china economy", "china gdp"),
        "anchors": ("china", "chinese", "yuan", "renminbi", "hang seng", "hsi", "hong kong"),
        "preferred": ("hang seng", "hsi", "hong kong", "yuan", "renminbi", "cnh", "stocks", "equities"),
        "excluded": (
            "taiwan",
            "invade",
            "invasion",
            "blockade",
            "gta",
            "bitcoin",
            "btc",
            "crypto",
            "temperature",
            "weather",
            "°c",
        ),
        "min_score": 3.0,
        "strong_score": 5.3,
        "candidate_min_score": 2.0,
    },
    "geopolitical_risk": {
        "queries": ("china invade taiwan", "china taiwan", "taiwan blockade"),
        "anchors": ("taiwan", "china"),
        "preferred": ("taiwan", "invade", "invasion", "blockade", "military", "war"),
        "excluded": ("gdp", "growth", "bitcoin", "btc", "crypto", "gta"),
        "min_score": 3.0,
        "strong_score": 5.2,
        "candidate_min_score": 2.0,
    },
    "btc_asia_momentum": {
        "queries": ("bitcoin", "btc", "crypto"),
        "anchors": ("bitcoin", "btc", "crypto"),
        "preferred": ("bitcoin", "btc", "crypto", "ethereum", "solana"),
        "excluded": ("taiwan", "gdp", "growth", "stock"),
        "min_score": 2.5,
        "strong_score": 4.7,
        "candidate_min_score": 1.5,
    },
}


SIGNAL_MARKET_INTENTS: dict[str, dict[str, tuple[str, ...]]] = {
    "hsi": {
        "signal": ("恒指", "恒生", "港股", "hong kong", "hang seng", "hsi"),
        "market": ("hang seng", "hsi", "hong kong"),
    },
    "semiconductor": {
        "signal": ("芯片", "半导体", "huawei", "华为", "semiconductor", "chip"),
        "market": ("semiconductor", "chip", "huawei", "nvidia", "tsmc"),
    },
    "brokerage": {
        "signal": ("券商", "证券", "brokerage", "securities"),
        "market": ("stocks", "equities", "securities", "brokerage"),
    },
}


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def signal_text(signal: Signal) -> str:
    return " ".join(
        (
            signal.headline_zh,
            signal.headline_en,
            signal.theme,
            signal.asset_link,
            " ".join(signal.evidence),
        )
    ).lower()


def signal_market_intents(signal: Signal) -> tuple[str, ...]:
    text = signal_text(signal)
    return tuple(
        name
        for name, terms in SIGNAL_MARKET_INTENTS.items()
        if _contains_any(text, terms["signal"])
    )


def market_queries(signal: Signal) -> tuple[str, ...]:
    rule = THEME_MARKET_RULES.get(signal.theme)
    queries: list[str] = []
    intents = signal_market_intents(signal)
    if "hsi" in intents:
        queries.extend(("hang seng", "hsi"))
    if "semiconductor" in intents:
        queries.extend(("semiconductor", "china semiconductor"))
    if "brokerage" in intents:
        queries.extend(("china stocks", "china securities"))
    queries.extend(tuple(rule["queries"]) if rule else ("china",))
    return tuple(dict.fromkeys(queries))


def market_query(signal: Signal) -> str:
    return market_queries(signal)[0]


def _search_result_text(result: PolymarketSearchResult) -> str:
    return " ".join(
        value
        for value in (
            result.question,
            result.title,
            result.slug,
            result.category,
        )
        if value
    ).lower()


def market_relevance_score(signal: Signal, result: PolymarketSearchResult) -> float:
    text = _search_result_text(result)
    rule = THEME_MARKET_RULES.get(signal.theme, {})
    anchors = tuple(rule.get("anchors", ()))
    preferred = tuple(rule.get("preferred", ()))
    excluded = tuple(rule.get("excluded", ()))

    score = 0.0
    if anchors:
        score += 2.0 if any(term in text for term in anchors) else -2.0
    for term in preferred:
        if term in text:
            score += 1.25 if " " in term else 1.0
    for term in excluded:
        if term in text:
            score -= 2.5
    if signal.theme in {"china_stimulus", "risk_off_china"} and "china" in text and "gdp" in text:
        score += 1.5
    if signal.theme == "geopolitical_risk" and "china" in text and "taiwan" in text:
        score += 1.5
    if signal.theme == "btc_asia_momentum" and ("bitcoin" in text or "btc" in text):
        score += 1.0
    for intent in signal_market_intents(signal):
        terms = SIGNAL_MARKET_INTENTS[intent]
        if _contains_any(text, terms["market"]):
            score += 1.75
        elif intent in {"hsi", "semiconductor"}:
            score -= 1.3
    if result.yes_price is not None:
        score += max(0.0, 1 - abs(float(result.yes_price) - 0.5) * 2) * 0.8
    score += min(float(result.liquidity or 0), 1_000_000) / 1_000_000 * 0.25
    score += min(float(result.volume or 0), 5_000_000) / 5_000_000 * 0.15
    return round(score, 4)


def market_match_label(signal: Signal, score: float) -> str:
    rule = THEME_MARKET_RULES.get(signal.theme, {})
    min_score = float(rule.get("min_score", 2.0))
    strong_score = float(rule.get("strong_score", min_score + 2.0))
    if score >= strong_score:
        return "Strong match"
    if score >= min_score:
        return "Best available proxy"
    return "Weak candidate"


def market_candidate_reason(signal: Signal, result: PolymarketSearchResult, score: float, selected: bool) -> str:
    text = _search_result_text(result)
    rule = THEME_MARKET_RULES.get(signal.theme, {})
    matched_terms = [
        term
        for term in tuple(rule.get("anchors", ())) + tuple(rule.get("preferred", ()))
        if term in text
    ]
    intent_matches = []
    for intent in signal_market_intents(signal):
        terms = SIGNAL_MARKET_INTENTS[intent]
        if _contains_any(text, terms["market"]):
            intent_matches.append(intent)
    if matched_terms:
        basis = f"matched {', '.join(dict.fromkeys(matched_terms[:4]))}"
    elif intent_matches:
        basis = f"matched signal-specific intent {', '.join(intent_matches)}"
    else:
        basis = "matched only broad theme terms"

    label = market_match_label(signal, score)
    if selected and label == "Best available proxy":
        return f"Selected as the highest-scoring proxy because no stronger direct market passed the threshold; {basis}."
    if selected:
        return f"Selected because it has the highest relevance score; {basis}."
    if label == "Best available proxy":
        return f"Usable proxy candidate; {basis}."
    return f"Lower-confidence candidate; {basis}."


def candidate_from_search_result(
    signal: Signal,
    result: PolymarketSearchResult,
    selected_slug: str | None = None,
) -> MarketCandidate | None:
    market = market_from_search_result(signal, result)
    if not market:
        return None
    score = market_relevance_score(signal, result)
    label = market_match_label(signal, score)
    selected = market.slug == selected_slug
    return MarketCandidate(
        market=market,
        relevance_score=score,
        match_label=label,
        reason=market_candidate_reason(signal, result, score, selected),
        selected=selected,
    )


def rank_market_candidates(
    signal: Signal,
    results: list[PolymarketSearchResult],
    limit: int = 3,
) -> list[MarketCandidate]:
    candidate_min_score = float(THEME_MARKET_RULES.get(signal.theme, {}).get("candidate_min_score", 1.5))
    by_slug: dict[str, MarketCandidate] = {}
    for result in results:
        candidate = candidate_from_search_result(signal, result)
        if not candidate or candidate.relevance_score < candidate_min_score:
            continue
        existing = by_slug.get(candidate.market.slug)
        if existing is None or candidate.relevance_score > existing.relevance_score:
            by_slug[candidate.market.slug] = candidate
    candidates = sorted(
        by_slug.values(),
        key=lambda item: (item.relevance_score, item.market.liquidity_usdc, item.market.volume_usdc),
        reverse=True,
    )
    selected_slug = candidates[0].market.slug if candidates else None
    selected: list[MarketCandidate] = []
    for candidate in candidates[:limit]:
        is_selected = candidate.market.slug == selected_slug
        selected.append(
            candidate.model_copy(
                update={
                    "selected": is_selected,
                    "reason": market_candidate_reason(
                        signal,
                        PolymarketSearchResult(
                            id=candidate.market.id.removeprefix("polymarket-"),
                            slug=candidate.market.slug,
                            question=candidate.market.question,
                            title=candidate.market.question,
                            category=candidate.market.category,
                            liquidity=candidate.market.liquidity_usdc,
                            volume=candidate.market.volume_usdc,
                            active=True,
                            closed=False,
                            yes_price=candidate.market.yes_price,
                            expiry=candidate.market.expiry,
                        ),
                        candidate.relevance_score,
                        is_selected,
                    ),
                }
            )
        )
    return selected


def best_market_search_result(signal: Signal, results: list[PolymarketSearchResult]) -> PolymarketSearchResult | None:
    min_score = float(THEME_MARKET_RULES.get(signal.theme, {}).get("min_score", 2.0))
    candidates = [
        (market_relevance_score(signal, result), float(result.liquidity or 0), float(result.volume or 0), result)
        for result in results
        if result.slug and (result.question or result.title) and result.yes_price is not None
    ]
    candidates = [candidate for candidate in candidates if candidate[0] >= min_score]
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return candidates[0][3]


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
        market, _ = self.resolve_market_with_candidates(signal, markets, live_cache=live_cache)
        return market

    def resolve_market_with_candidates(
        self,
        signal: Signal,
        markets: list[Market],
        live_cache: dict[str, Market | None] | None = None,
        query_cache: dict[str, list[PolymarketSearchResult]] | None = None,
    ) -> tuple[Market, list[MarketCandidate]]:
        try:
            market = matching_market(signal, markets)
            return market, [
                MarketCandidate(
                    market=market,
                    relevance_score=10.0,
                    match_label="Configured match",
                    reason="Selected from an explicitly configured market for this signal theme.",
                    selected=True,
                )
            ]
        except LookupError:
            pass

        intent_key = ",".join(signal_market_intents(signal)) or "broad"
        cache_key = f"{signal.theme}:{signal.asset_link}:{intent_key}"
        if live_cache is not None and cache_key in live_cache:
            market = live_cache[cache_key]
            if market:
                candidate = MarketCandidate(
                    market=market,
                    relevance_score=0.0,
                    match_label="Cached match",
                    reason="Selected from the live market cache for this signal intent.",
                    selected=True,
                )
                return market, [candidate]
            raise LookupError(f"No live Polymarket market with a real price found for {signal.theme}")

        results: list[PolymarketSearchResult] = []
        for query in market_queries(signal):
            if query_cache is not None and query in query_cache:
                results.extend(query_cache[query])
                continue
            query_results = self.polymarket_client.search(query, limit=20)
            if query_cache is not None:
                query_cache[query] = query_results
            results.extend(query_results)

        candidates = rank_market_candidates(signal, results, limit=3)
        min_score = float(THEME_MARKET_RULES.get(signal.theme, {}).get("min_score", 2.0))
        selected = candidates[0] if candidates and candidates[0].relevance_score >= min_score else None
        if selected:
            if live_cache is not None:
                live_cache[cache_key] = selected.market
            return selected.market, candidates

        if live_cache is not None:
            live_cache[cache_key] = None
        raise LookupError(f"No relevant live Polymarket market with a real price found for {signal.theme}")

    def recommendations(self, signal_id: str | None = None, include_llm: bool = False) -> list[Recommendation]:
        signals = self.repository.signals()
        if signal_id:
            signals = [signal for signal in signals if signal.id == signal_id]
            if not signals:
                raise LookupError(f"Unknown signal id: {signal_id}")

        markets = self.repository.markets()
        query_cache: dict[str, list[PolymarketSearchResult]] = {}
        recommendations: list[Recommendation] = []
        for signal in signals:
            try:
                market, market_candidates = self.resolve_market_with_candidates(
                    signal,
                    markets,
                    query_cache=query_cache,
                )
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
                    market_candidates=market_candidates,
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

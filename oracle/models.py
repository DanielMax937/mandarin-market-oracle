from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Direction(str, Enum):
    YES = "YES"
    NO = "NO"
    WAIT = "WAIT"


class Signal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source: str
    source_type: str
    language: str
    headline_zh: str
    headline_en: str
    theme: str
    asset_link: str
    credibility: float = Field(ge=0, le=1)
    velocity: float = Field(ge=0, le=1)
    freshness_minutes: int = Field(ge=0)
    evidence: list[str]
    risk_flags: list[str]


class SignalIntakeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline_zh: str = Field(min_length=4)
    source: str = Field(min_length=2)
    source_url: str | None = None
    body_zh: str | None = None
    source_type: str = "user_attested"
    theme: str | None = None
    asset_link: str | None = None
    credibility: float | None = Field(default=None, ge=0, le=1)
    velocity: float | None = Field(default=None, ge=0, le=1)
    freshness_minutes: int = Field(default=5, ge=0)
    evidence: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    market_slug: str | None = None
    market_question: str | None = None
    market_category: str | None = None
    market_yes_price: float | None = Field(default=None, ge=0, le=1)
    market_liquidity_usdc: float | None = Field(default=None, ge=0)
    market_volume_usdc: float | None = Field(default=None, ge=0)
    market_expiry: datetime | None = None


class SignalIntakeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal: Signal
    recommendation: "Recommendation"


class PolymarketSearchResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    slug: str | None = None
    question: str | None = None
    title: str | None = None
    category: str | None = None
    liquidity: float | None = None
    volume: float | None = None
    active: bool | None = None
    closed: bool | None = None
    yes_price: float | None = Field(default=None, ge=0, le=1)
    expiry: datetime | None = None


class Market(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    slug: str
    question: str
    category: str
    matched_theme: str
    yes_price: float = Field(ge=0, le=1)
    no_price: float = Field(ge=0, le=1)
    liquidity_usdc: float = Field(ge=0)
    volume_usdc: float = Field(ge=0)
    expiry: datetime


class MarketCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market: Market
    relevance_score: float
    match_label: str
    reason: str
    selected: bool = False


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    direction: Direction
    market_probability: float = Field(ge=0, le=1)
    agent_probability: float = Field(ge=0, le=1)
    edge: float
    conviction: float = Field(ge=0, le=1)
    risk_unit_size: float = Field(ge=0)
    rationale: str


class LLMReasoning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    used: bool
    provider: str
    model: str
    base_url: str
    prompt_version: str
    english_summary: str
    market_impact_path: str
    bull_case: str
    bear_case: str
    probability_rationale: str
    risk_caveats: list[str]
    final_explanation: str
    error: str | None = None


class Receipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    receipt_id: str
    network: str
    tx_hash: str | None = None
    market_slug: str
    signal_id: str
    direction: Direction
    market_probability: float
    agent_probability: float
    edge: float
    risk_unit_size: float
    evidence_hash: str
    recommendation_hash: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Recommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal: Signal
    market: Market
    market_candidates: list[MarketCandidate] = Field(default_factory=list)
    decision: Decision
    decision_trace: dict[str, Any] = Field(default_factory=dict)
    llm_reasoning: LLMReasoning | None = None
    receipt: Receipt


class AgentMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str
    llm_enabled: bool
    provider: str
    model: str
    base_url: str
    prompt_version: str


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product: str = "Mandarin Market Oracle"
    execution_mode: str
    provenance_network: str
    verification_contract: str | None = None
    agent: AgentMetadata
    bankroll_usdc: float
    recommendations: list[Recommendation]

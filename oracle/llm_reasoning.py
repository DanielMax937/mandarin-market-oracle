from __future__ import annotations

import json
import hashlib
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import ValidationError

from oracle.config import Settings, settings
from oracle.models import Decision, LLMReasoning, Market, Signal


PROMPT_VERSION = "mandarin-alpha-v1"
SYSTEM_PROMPT = """You are Mandarin Alpha Analyst, an AI research agent for a prediction-market desk.

Your job is to explain how a Mandarin-language market signal could affect a priced Polymarket market.

Rules:
- Use English for the output.
- Preserve the Mandarin source as evidence; do not invent facts beyond the provided source text.
- Do not recommend real-money trading.
- Do not claim certainty or guaranteed profit.
- The deterministic pricing engine already produced direction, market probability, agent probability, edge, and risk size. Explain that reasoning; do not change the numbers.
- Output strict JSON only.
"""


def user_prompt(signal: Signal, market: Market, decision: Decision) -> str:
    evidence = "\n".join(f"- {item}" for item in signal.evidence)
    risk_flags = "\n".join(f"- {item}" for item in signal.risk_flags)
    return f"""Analyze this Mandarin alpha signal for Polymarket.

Mandarin signal:
{signal.headline_zh}

Existing English brief:
{signal.headline_en}

Source:
{signal.source} ({signal.source_type})

Evidence:
{evidence}

Risk flags:
{risk_flags}

Polymarket market:
Question: {market.question}
Slug: {market.slug}
Market YES probability: {decision.market_probability:.2%}
Agent fair probability: {decision.agent_probability:.2%}
Edge: {decision.edge:+.2%}
Direction: {decision.direction.value}
Research risk units: {decision.risk_unit_size:,.0f}

Return compact JSON with exactly these keys. Keep every string under 240 characters:
{{
  "english_summary": "one-sentence English summary of the Mandarin signal",
  "market_impact_path": "causal path from the signal to the Polymarket price",
  "bull_case": "why YES could be underpriced, or why NO could be underpriced if direction is NO",
  "bear_case": "what would invalidate or weaken the signal",
  "probability_rationale": "why agent probability differs from market probability using the provided numbers",
  "risk_caveats": ["2-4 concise caveats"],
  "final_explanation": "short trader-facing explanation of the recommendation"
}}
"""


def _extract_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


class LLMReasoningClient:
    def __init__(self, config: Settings = settings) -> None:
        self.config = config
        self._cache: dict[str, LLMReasoning] = {}

    def metadata(self) -> dict[str, str | bool]:
        return {
            "llm_enabled": self.config.llm_reasoning_enabled and bool(self.config.openai_api_key),
            "provider": "openai-compatible",
            "model": self.config.openai_model,
            "base_url": self.config.openai_base_url,
            "prompt_version": PROMPT_VERSION,
        }

    def explain(self, signal: Signal, market: Market, decision: Decision) -> LLMReasoning:
        cache_key = self._cache_key(signal, market, decision)
        if cache_key in self._cache:
            return self._cache[cache_key]

        base = {
            "used": False,
            "provider": "openai-compatible",
            "model": self.config.openai_model,
            "base_url": self.config.openai_base_url,
            "prompt_version": PROMPT_VERSION,
        }
        if not self.config.llm_reasoning_enabled:
            return self._fallback(base, signal, decision, "LLM reasoning disabled.")
        if not self.config.openai_api_key:
            return self._fallback(base, signal, decision, "OPENAI_API_KEY is not configured.")

        payload = {
            "model": self.config.openai_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt(signal, market, decision)},
            ],
            "temperature": 0.2,
            "max_tokens": 1800,
            "response_format": {"type": "json_object"},
        }
        endpoint = f"{self.config.openai_base_url.rstrip('/')}/chat/completions"
        request = Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.config.openai_api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.config.request_timeout_seconds) as response:
                raw = json.loads(response.read().decode("utf-8"))
            message = raw["choices"][0]["message"]
            content = message.get("content") or message.get("reasoning_content") or ""
            parsed = _extract_json(content)
            reasoning = LLMReasoning.model_validate({**base, "used": True, **parsed})
        except HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")[:400]
            reasoning = self._fallback(base, signal, decision, f"LLM reasoning failed: HTTP {exc.code} {details}")
        except (KeyError, TypeError, ValueError, URLError, TimeoutError, ValidationError) as exc:
            reasoning = self._fallback(base, signal, decision, f"LLM reasoning failed: {exc}")
        self._cache[cache_key] = reasoning
        return reasoning

    def _cache_key(self, signal: Signal, market: Market, decision: Decision) -> str:
        payload = {
            "prompt_version": PROMPT_VERSION,
            "model": self.config.openai_model,
            "signal_id": signal.id,
            "signal_headline": signal.headline_zh,
            "market_slug": market.slug,
            "market_probability": decision.market_probability,
            "agent_probability": decision.agent_probability,
            "direction": decision.direction.value,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _fallback(
        self,
        base: dict[str, Any],
        signal: Signal,
        decision: Decision,
        error: str,
    ) -> LLMReasoning:
        return LLMReasoning(
            **base,
            english_summary=signal.headline_en,
            market_impact_path=decision.rationale,
            bull_case="Use the deterministic signal score and market edge as the primary research view.",
            bear_case="The Mandarin signal may be noisy, stale, or insufficiently related to the Polymarket contract.",
            probability_rationale=decision.rationale,
            risk_caveats=signal.risk_flags,
            final_explanation=decision.rationale,
            error=error,
        )

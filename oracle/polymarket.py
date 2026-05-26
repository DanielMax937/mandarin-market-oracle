from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener

from oracle.config import Settings, settings
from oracle.models import PolymarketSearchResult


class PolymarketClient:
    """Proxy-aware, read-only client for Polymarket Gamma.

    The product never places orders. This client is only for market discovery and
    metadata lookup. Proxy behavior is explicit: POLYMARKET_PROXY_URL wins, then
    standard HTTPS_PROXY/HTTP_PROXY environment variables.
    """

    def __init__(self, config: Settings = settings) -> None:
        self.config = config

    def _proxy_url(self) -> str | None:
        return (
            self.config.polymarket_proxy_url
            or os.getenv("HTTPS_PROXY")
            or os.getenv("https_proxy")
            or os.getenv("HTTP_PROXY")
            or os.getenv("http_proxy")
        )

    def proxy_configured(self) -> bool:
        return self._proxy_url() is not None

    def _open_json(self, path: str, params: dict[str, Any]) -> Any:
        query = urlencode({key: value for key, value in params.items() if value is not None})
        url = f"{self.config.polymarket_base_url.rstrip('/')}{path}"
        if query:
            url = f"{url}?{query}"

        proxy_url = self._proxy_url()
        opener = build_opener(ProxyHandler({"http": proxy_url, "https": proxy_url})) if proxy_url else build_opener()
        request = Request(url, headers={"User-Agent": "MandarinMarketOracle/0.2"})
        try:
            with opener.open(request, timeout=self.config.request_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except URLError as exc:
            raise RuntimeError(f"Polymarket request failed: {exc}") from exc

    def _flatten_search_payload(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []

        records: list[dict[str, Any]] = []
        for key in ("results", "markets"):
            values = payload.get(key)
            if isinstance(values, list):
                records.extend(item for item in values if isinstance(item, dict))

        events = payload.get("events")
        if isinstance(events, list):
            for event in events:
                if not isinstance(event, dict):
                    continue
                markets = event.get("markets")
                if isinstance(markets, list):
                    records.extend(item for item in markets if isinstance(item, dict))

        return records

    def _normalize_record(self, record: dict[str, Any]) -> dict[str, Any]:
        outcome_prices = record.get("outcomePrices")
        yes_price = record.get("yes_price")
        if yes_price is None and isinstance(outcome_prices, str):
            try:
                prices = json.loads(outcome_prices)
                if prices:
                    yes_price = float(prices[0])
            except (TypeError, ValueError, json.JSONDecodeError):
                yes_price = None
        if yes_price is None and isinstance(outcome_prices, list) and outcome_prices:
            try:
                yes_price = float(outcome_prices[0])
            except (TypeError, ValueError):
                yes_price = None
        if yes_price is None:
            for key in ("lastTradePrice", "bestAsk", "bestBid"):
                if record.get(key) is not None:
                    yes_price = record.get(key)
                    break

        expiry = record.get("expiry") or record.get("endDateIso") or record.get("endDate")
        if isinstance(expiry, str) and len(expiry) == 10:
            expiry = f"{expiry}T23:59:00Z"

        return {
            "id": str(record.get("id")) if record.get("id") is not None else None,
            "slug": record.get("slug"),
            "question": record.get("question") or record.get("title"),
            "title": record.get("title") or record.get("question"),
            "category": record.get("category"),
            "liquidity": record.get("liquidity") or record.get("liquidityNum") or record.get("liquidityClob"),
            "volume": record.get("volume") or record.get("volumeNum") or record.get("volumeClob"),
            "active": record.get("active"),
            "closed": record.get("closed"),
            "yes_price": yes_price,
            "expiry": expiry,
        }

    def _real_priced_results(
        self,
        records: list[dict[str, Any]],
    ) -> list[PolymarketSearchResult]:
        results: list[PolymarketSearchResult] = []
        for record in records:
            item = PolymarketSearchResult.model_validate(self._normalize_record(record))
            if item.slug is None or (item.question is None and item.title is None):
                continue
            if item.yes_price is None:
                continue
            if item.closed is True or item.active is False:
                continue
            if item.expiry is None:
                continue
            results.append(item)
        return results

    def _filter_records(self, records: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
        tokens = [token for token in query.lower().strip().split() if token]
        if not tokens:
            return records
        filtered = []
        for record in records:
            haystack = " ".join(
                str(record.get(key, ""))
                for key in ("question", "title", "slug", "description", "category")
            ).lower()
            if any(token in haystack for token in tokens):
                filtered.append(record)
        return filtered

    def search(self, query: str, limit: int = 10) -> list[PolymarketSearchResult]:
        payload = self._open_json("/public-search", {"q": query, "query": query, "limit": limit})
        records = self._filter_records(self._flatten_search_payload(payload), query)
        results = self._real_priced_results(records)
        if not results:
            markets_payload = self._open_json(
                "/markets",
                {"limit": max(limit, 25), "active": "true", "closed": "false", "search": query},
            )
            records = self._filter_records(self._flatten_search_payload(markets_payload), query)
            results = self._real_priced_results(records)
        return results[:limit]

    def active_markets(self, limit: int = 25) -> list[PolymarketSearchResult]:
        payload = self._open_json(
            "/markets",
            {"limit": limit, "active": "true", "closed": "false"},
        )
        records = payload.get("markets", payload) if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            return []
        return self._real_priced_results(records)[:limit]

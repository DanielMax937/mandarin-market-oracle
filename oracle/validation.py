from __future__ import annotations

from typing import Any

from oracle.models import Recommendation


def validation_summary(recommendations: list[Recommendation]) -> dict[str, Any]:
    avg_edge = (
        sum(abs(item.decision.edge) for item in recommendations) / len(recommendations)
        if recommendations
        else None
    )
    wait_count = sum(1 for item in recommendations if item.decision.direction.value == "WAIT")
    proofed_count = sum(1 for item in recommendations if item.receipt.tx_hash)
    live_source_count = sum(
        1
        for item in recommendations
        if item.signal.source_type in {"public_news_api", "public_market_data_api", "user_attested"}
    )
    priced_market_count = sum(1 for item in recommendations if item.market.yes_price is not None)
    return {
        "mode": "live",
        "label": "Live validation tracker",
        "description": (
            "All metrics are computed from current live-source recommendations and recorded "
            "Arc receipts. No replay outcomes or synthetic price moves are included."
        ),
        "recommendation_count": len(recommendations),
        "live_source_count": live_source_count,
        "priced_market_count": priced_market_count,
        "average_abs_edge": round(avg_edge, 4) if avg_edge is not None else None,
        "wait_count": wait_count,
        "proofed_count": proofed_count,
        "events": [],
    }

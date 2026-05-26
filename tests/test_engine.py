from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from oracle.config import Settings
from oracle.engine import OracleService, canonical_hash, decide, decision_trace, matching_market
from oracle.intake import SignalIntakeService, infer_theme
from oracle.models import Market, Signal, SignalIntakeRequest
from oracle.polymarket import PolymarketClient
from oracle.proof import ProofWriter, proof_details
from oracle.repository import DataRepository
from oracle.validation import validation_summary


def sample_signal() -> Signal:
    return Signal(
        id="live-test-signal",
        source="Eastmoney Push2 · A-share index tape",
        source_type="public_market_data_api",
        language="zh",
        headline_zh="上证指数实时走强 +1.20%",
        headline_en="SSE Composite live move +1.20%",
        theme="china_stimulus",
        asset_link="china_policy_a_shares_commodities",
        credibility=0.9,
        velocity=0.75,
        freshness_minutes=5,
        evidence=["Eastmoney public market-data endpoint"],
        risk_flags=["Research-only recommendation; no real-money order execution"],
    )


def sample_market() -> Market:
    return Market(
        id="polymarket-test",
        slug="china-economic-growth-in-2026",
        question="Will China economic growth exceed expectations in 2026?",
        category="polymarket-live",
        matched_theme="china_stimulus",
        yes_price=0.38,
        no_price=0.62,
        liquidity_usdc=250000,
        volume_usdc=700000,
        expiry=datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc),
    )


class EngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = Settings(llm_reasoning_enabled=False)
        self.temp_dir = TemporaryDirectory()
        self.repository = DataRepository(Path(self.temp_dir.name))
        self.repository.source_client.fetch_signals = lambda: [sample_signal()]
        self.repository.append_user_market(sample_market())
        self.service = OracleService(repository=self.repository, config=self.config)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_snapshot_contains_real_source_signal(self) -> None:
        snapshot = self.service.snapshot()
        self.assertEqual(snapshot.execution_mode, "research")
        self.assertFalse(snapshot.agent.llm_enabled)
        self.assertEqual(len(snapshot.recommendations), 1)
        self.assertEqual(snapshot.recommendations[0].signal.source_type, "public_market_data_api")
        self.assertIsNone(snapshot.recommendations[0].llm_reasoning)

    def test_llm_reasoning_is_on_demand(self) -> None:
        item = self.service.explain_recommendation("live-test-signal")
        self.assertIsNotNone(item.llm_reasoning)
        self.assertFalse(item.llm_reasoning.used)
        self.assertIn("disabled", item.llm_reasoning.error)

    def test_first_signal_is_yes_with_positive_edge(self) -> None:
        signal = self.repository.signals()[0]
        market = matching_market(signal, self.repository.markets())
        decision = decide(signal, market, self.config)
        self.assertEqual(decision.direction, "YES")
        self.assertGreater(decision.edge, 0)
        self.assertLessEqual(decision.risk_unit_size, self.config.bankroll_usdc * 0.05)

    def test_hash_is_canonical(self) -> None:
        left = canonical_hash({"b": 2, "a": 1})
        right = canonical_hash({"a": 1, "b": 2})
        self.assertEqual(left, right)

    def test_real_orders_are_blocked(self) -> None:
        unsafe = Settings(allow_real_orders=True)
        signal = self.repository.signals()[0]
        market = matching_market(signal, self.repository.markets())
        with self.assertRaises(RuntimeError):
            decide(signal, market, unsafe)

    def test_theme_inference_catches_btc_asia_signal(self) -> None:
        self.assertEqual(infer_theme("中文交易社区看多 BTC，永续资金费率抬升"), "btc_asia_momentum")

    def test_signal_intake_requires_real_market_price(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repository = DataRepository(Path(temp_dir))
            repository.source_client.fetch_signals = lambda: []
            intake = SignalIntakeService(repository)
            with self.assertRaises(ValueError):
                intake.submit(
                    SignalIntakeRequest(
                        headline_zh="铁矿石夜盘拉升，地产链资金回流",
                        source="analyst submission with source URL",
                        theme="china_stimulus",
                        market_slug="china-economic-growth-in-2026",
                        market_question="Will China economic growth exceed expectations in 2026?",
                    )
                )

    def test_polymarket_proxy_url_precedence(self) -> None:
        config = Settings(polymarket_proxy_url="http://127.0.0.1:7890")
        client = PolymarketClient(config)
        self.assertEqual(client._proxy_url(), "http://127.0.0.1:7890")

    def test_arc_testnet_requires_configuration(self) -> None:
        item = self.service.recommendations(signal_id="live-test-signal")[0]
        with patch.dict(
            "os.environ",
            {
                "ARC_PROOF_MODE": "evm",
                "ARC_REASONING_REGISTRY_ADDRESS": "",
                "ARC_PRIVATE_KEY": "",
            },
            clear=False,
        ):
            result = ProofWriter(self.config).write(item.receipt)
        self.assertEqual(result.mode, "evm")
        self.assertEqual(result.status, "blocked")
        self.assertIn("ARC_REASONING_REGISTRY_ADDRESS", result.message)

    def test_decision_trace_exposes_weighted_agent_logic(self) -> None:
        signal = self.repository.signals()[0]
        market = matching_market(signal, self.repository.markets())
        decision = decide(signal, market, self.config)
        trace = decision_trace(signal, market, decision, self.config)
        self.assertIn("formula", trace)
        self.assertEqual(len(trace["inputs"]), 3)
        self.assertEqual(
            trace["outputs"]["direction_rule"],
            "YES if edge > 5.5%; NO if edge < -5.5%; otherwise WAIT.",
        )
        self.assertLessEqual(
            trace["outputs"]["kelly_fraction_capped"],
            self.config.max_position_pct,
        )

    def test_proof_details_include_registry_payload_and_explorer_links(self) -> None:
        item = self.service.recommendations(signal_id="live-test-signal")[0]
        details = proof_details(item.receipt, "0x219E7613F20f6170E02e3Ebfa87EBeC6A484d800")
        self.assertEqual(details["status"], "prepared")
        self.assertEqual(
            details["payload"]["recommendation_hash"],
            item.receipt.recommendation_hash,
        )
        self.assertIsNone(details["explorer_url"])
        self.assertIn("/address/", details["registry_url"])

    def test_live_validation_summary_uses_current_recommendations_only(self) -> None:
        summary = validation_summary(self.service.recommendations())
        self.assertEqual(summary["mode"], "live")
        self.assertEqual(summary["recommendation_count"], 1)
        self.assertEqual(summary["live_source_count"], 1)
        self.assertEqual(summary["priced_market_count"], 1)
        self.assertEqual(summary["events"], [])


if __name__ == "__main__":
    unittest.main()

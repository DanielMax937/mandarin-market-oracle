from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env.local")
    load_dotenv(ROOT / ".env")
except ImportError:
    pass


@dataclass(frozen=True)
class Settings:
    environment: str = os.getenv("ORACLE_ENV", "development")
    data_dir: Path = Path(os.getenv("ORACLE_DATA_DIR", ROOT / "data"))
    bankroll_usdc: float = float(os.getenv("ORACLE_BANKROLL_USDC", "10000"))
    max_position_pct: float = float(os.getenv("ORACLE_MAX_POSITION_PCT", "0.05"))
    execution_mode: str = os.getenv("ORACLE_EXECUTION_MODE", "research")
    provenance_network: str = os.getenv("ORACLE_PROVENANCE_NETWORK", "arc-testnet")
    allow_real_orders: bool = os.getenv("ORACLE_ALLOW_REAL_ORDERS", "false").lower() == "true"
    polymarket_base_url: str = os.getenv(
        "POLYMARKET_GAMMA_BASE_URL", "https://gamma-api.polymarket.com"
    )
    polymarket_proxy_url: str | None = os.getenv("POLYMARKET_PROXY_URL")
    request_timeout_seconds: float = float(os.getenv("ORACLE_REQUEST_TIMEOUT_SECONDS", "12"))
    arc_reasoning_registry_address: str | None = os.getenv("ARC_REASONING_REGISTRY_ADDRESS")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    llm_reasoning_enabled: bool = os.getenv("ORACLE_LLM_REASONING_ENABLED", "true").lower() == "true"

    def validate_compliance_boundary(self) -> None:
        if self.allow_real_orders:
            raise RuntimeError(
                "Real order execution is disabled for this product build. "
                "Set up a separate regulated deployment before enabling live trading."
            )
        if self.execution_mode not in {"research", "testnet"}:
            raise RuntimeError("Only research/testnet execution modes are allowed in this build.")


settings = Settings()

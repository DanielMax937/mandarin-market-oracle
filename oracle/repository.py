from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, TypeAdapter

from oracle.config import settings
from oracle.models import Market, Receipt, Signal
from oracle.sources import LiveMandarinSourceClient


ModelT = TypeVar("ModelT", bound=BaseModel)


def _load_list(path: Path, model: type[ModelT]) -> list[ModelT]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return TypeAdapter(list[model]).validate_python(raw)


class LiveRepository:
    def __init__(self, data_dir: Path = settings.data_dir) -> None:
        self.data_dir = data_dir
        self.source_client = LiveMandarinSourceClient()

    def signals(self) -> list[Signal]:
        live_signals = self.source_client.fetch_signals()
        user_path = self.data_dir / "user_signals.json"
        if not user_path.exists():
            return live_signals
        return live_signals + _load_list(user_path, Signal)

    def markets(self) -> list[Market]:
        user_path = self.data_dir / "user_markets.json"
        if not user_path.exists():
            return []
        return _load_list(user_path, Market)

    def receipts(self) -> list[Receipt]:
        path = self.data_dir / "proof_receipts.json"
        if not path.exists():
            return []
        return _load_list(path, Receipt)

    def receipt_for(self, recommendation_hash: str) -> Receipt | None:
        for receipt in self.receipts():
            if receipt.recommendation_hash == recommendation_hash:
                return receipt
        return None

    def append_receipt(self, receipt: Receipt) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        path = self.data_dir / "proof_receipts.json"
        existing = _load_list(path, Receipt) if path.exists() else []
        existing = [item for item in existing if item.recommendation_hash != receipt.recommendation_hash]
        existing.append(receipt)
        payload = [item.model_dump(mode="json") for item in existing]
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def append_user_signal(self, signal: Signal) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        path = self.data_dir / "user_signals.json"
        existing = _load_list(path, Signal) if path.exists() else []
        existing.append(signal)
        payload = [item.model_dump(mode="json") for item in existing]
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def append_user_market(self, market: Market) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        path = self.data_dir / "user_markets.json"
        existing = _load_list(path, Market) if path.exists() else []
        existing = [item for item in existing if item.slug != market.slug]
        existing.append(market)
        payload = [item.model_dump(mode="json") for item in existing]
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


DataRepository = LiveRepository

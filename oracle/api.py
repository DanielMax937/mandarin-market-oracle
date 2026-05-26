from __future__ import annotations

import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from oracle.config import ROOT, settings
from oracle.engine import OracleService
from oracle.intake import SignalIntakeService
from oracle.models import SignalIntakeRequest
from oracle.polymarket import PolymarketClient
from oracle.proof import ProofWriter, proof_details
from oracle.validation import validation_summary


app = FastAPI(
    title="Mandarin Market Oracle API",
    version="0.2.0",
    description="Compliance-safe Mandarin signal intelligence for prediction markets.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

service = OracleService()
intake_service = SignalIntakeService()
polymarket_client = PolymarketClient()
proof_writer = ProofWriter()
SNAPSHOT_CACHE_SECONDS = 45
_snapshot_cache: tuple[float, dict] | None = None


def _registry_contract() -> str | None:
    return proof_writer.contract_address or settings.arc_reasoning_registry_address


def _reject_non_live_mode(mode: str | None) -> None:
    if mode not in {None, "live"}:
        raise HTTPException(status_code=400, detail="Only live mode is supported; replay data is disabled.")


def _clear_snapshot_cache() -> None:
    global _snapshot_cache
    _snapshot_cache = None


def _snapshot_payload() -> dict:
    snapshot_model = service.snapshot()
    payload = snapshot_model.model_dump(mode="json")
    payload["dataset_mode"] = "live"
    payload["verification_contract"] = _registry_contract()
    payload["validation"] = validation_summary(snapshot_model.recommendations)
    return payload


@app.get("/api/health")
def health() -> dict[str, str | None]:
    settings.validate_compliance_boundary()
    agent = service.agent_metadata()
    return {
        "status": "ok",
        "execution_mode": settings.execution_mode,
        "provenance_network": settings.provenance_network,
        "verification_contract": settings.arc_reasoning_registry_address,
        "agent_mode": agent.mode,
        "llm_provider": agent.provider,
        "llm_model": agent.model,
        "llm_base_url": agent.base_url,
        "llm_prompt_version": agent.prompt_version,
        "llm_enabled": str(agent.llm_enabled).lower(),
    }


@app.get("/api/snapshot")
def snapshot(mode: str | None = None) -> dict:
    global _snapshot_cache
    _reject_non_live_mode(mode)
    try:
        now = time.monotonic()
        if _snapshot_cache and now - _snapshot_cache[0] < SNAPSHOT_CACHE_SECONDS:
            return _snapshot_cache[1]
        payload = _snapshot_payload()
        _snapshot_cache = (now, payload)
        return payload
    except Exception as exc:  # pragma: no cover - FastAPI boundary
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/recommendations/{signal_id}")
def recommendation(signal_id: str, mode: str | None = None) -> dict:
    _reject_non_live_mode(mode)
    try:
        item = service.recommendations(signal_id=signal_id)[0]
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return item.model_dump(mode="json")


@app.post("/api/recommendations/{signal_id}/reasoning")
def recommendation_reasoning(signal_id: str, mode: str | None = None) -> dict:
    _reject_non_live_mode(mode)
    try:
        item = service.explain_recommendation(signal_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return item.model_dump(mode="json")


@app.get("/api/agent/prompt")
def agent_prompt(signal_id: str | None = None, mode: str | None = None) -> dict:
    _reject_non_live_mode(mode)
    return service.prompt_config(signal_id=signal_id)


@app.get("/api/validation")
def validation(mode: str | None = None) -> dict:
    _reject_non_live_mode(mode)
    return validation_summary(service.recommendations())


@app.get("/api/proofs/{signal_id}/payload")
def proof_payload(signal_id: str, mode: str | None = None) -> dict:
    _reject_non_live_mode(mode)
    try:
        item = service.recommendations(signal_id=signal_id)[0]
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return proof_details(item.receipt, contract_address=_registry_contract())


@app.post("/api/proofs/{signal_id}")
def write_proof(signal_id: str, mode: str | None = None) -> dict:
    _reject_non_live_mode(mode)
    try:
        item = service.recommendations(signal_id=signal_id)[0]
        result = proof_writer.write(item.receipt)
        if result.status == "submitted" and result.tx_hash:
            item.receipt = item.receipt.model_copy(update={"tx_hash": result.tx_hash})
            service.repository.append_receipt(item.receipt)
            _clear_snapshot_cache()
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        **proof_details(item.receipt, contract_address=_registry_contract()),
        **result.as_dict(),
    }


@app.post("/api/intake/signals")
def submit_signal(request: SignalIntakeRequest) -> dict:
    try:
        response = intake_service.submit(request)
        _clear_snapshot_cache()
    except Exception as exc:  # pragma: no cover - FastAPI boundary
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return response.model_dump(mode="json")


@app.get("/api/polymarket/search")
def polymarket_search(q: str, limit: int = 10) -> dict:
    try:
        results = polymarket_client.search(q, limit=min(max(limit, 1), 25))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "query": q,
        "proxy_configured": polymarket_client.proxy_configured(),
        "results": [item.model_dump(mode="json") for item in results],
    }


@app.get("/api/sources/policy")
def source_policy() -> dict:
    return {
        "mode": "controlled-intake",
        "allowed_sources": [
            "human-curated Mandarin market signals",
            "public market data APIs",
            "official Chinese policy and exchange announcements",
            "user-submitted social/news links",
        ],
        "disallowed_sources": [
            "unrestricted large-scale scraping of restricted platforms",
            "real-money execution",
            "custody of user funds",
        ],
        "polymarket_access": "read-only Gamma/CLOB data through configured proxy",
    }


web_dir = Path(ROOT / "web")
if web_dir.exists():
    app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

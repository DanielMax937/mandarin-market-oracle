from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from oracle.config import ROOT, settings
from oracle.engine import OracleService
from oracle.intake import SignalIntakeService
from oracle.models import SignalIntakeRequest
from oracle.polymarket import PolymarketClient
from oracle.proof import ProofWriter


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
def snapshot() -> dict:
    try:
        return service.snapshot().model_dump(mode="json")
    except Exception as exc:  # pragma: no cover - FastAPI boundary
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/recommendations/{signal_id}")
def recommendation(signal_id: str) -> dict:
    try:
        item = service.recommendations(signal_id=signal_id)[0]
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return item.model_dump(mode="json")


@app.post("/api/recommendations/{signal_id}/reasoning")
def recommendation_reasoning(signal_id: str) -> dict:
    try:
        item = service.explain_recommendation(signal_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return item.model_dump(mode="json")


@app.get("/api/agent/prompt")
def agent_prompt(signal_id: str | None = None) -> dict:
    return service.prompt_config(signal_id=signal_id)


@app.post("/api/proofs/{signal_id}")
def write_proof(signal_id: str) -> dict:
    try:
        item = service.recommendations(signal_id=signal_id)[0]
        result = proof_writer.write(item.receipt)
        if result.status == "submitted" and result.tx_hash:
            service.repository.append_receipt(item.receipt.model_copy(update={"tx_hash": result.tx_hash}))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return result.as_dict()


@app.post("/api/intake/signals")
def submit_signal(request: SignalIntakeRequest) -> dict:
    try:
        response = intake_service.submit(request)
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

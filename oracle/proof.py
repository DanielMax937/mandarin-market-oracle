from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from oracle.config import ROOT, Settings, settings
from oracle.engine import canonical_hash
from oracle.models import Receipt


ARC_CONFIG = Path.home() / ".arc-canteen" / "config.yaml"
DEFAULT_ARC_EXPLORER_BASE_URL = "https://testnet.arcscan.app"


@dataclass(frozen=True)
class ProofResult:
    mode: str
    status: str
    receipt_id: str
    tx_hash: str | None
    explorer_url: str | None
    message: str
    payload_hash: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "status": self.status,
            "receipt_id": self.receipt_id,
            "tx_hash": self.tx_hash,
            "explorer_url": self.explorer_url,
            "message": self.message,
            "payload_hash": self.payload_hash,
        }


def _hex_to_bytes32(value: str) -> str:
    clean = value.removeprefix("0x")
    if len(clean) != 64:
        raise ValueError(f"Expected bytes32 hex, got {value}")
    return "0x" + clean


def receipt_payload(receipt: Receipt) -> dict[str, Any]:
    return {
        "recommendation_hash": _hex_to_bytes32(receipt.recommendation_hash),
        "evidence_hash": _hex_to_bytes32(receipt.evidence_hash),
        "market_slug": receipt.market_slug,
        "signal_id": receipt.signal_id,
        "direction": receipt.direction.value,
        "market_probability_bps": round(receipt.market_probability * 10_000),
        "agent_probability_bps": round(receipt.agent_probability * 10_000),
        "risk_unit_size": round(receipt.risk_unit_size * 1_000_000),
    }


def explorer_tx_url(tx_hash: str | None, explorer_base_url: str | None = None) -> str | None:
    if not tx_hash:
        return None
    base_url = (explorer_base_url or DEFAULT_ARC_EXPLORER_BASE_URL).rstrip("/")
    return f"{base_url}/tx/{tx_hash}"


def explorer_address_url(address: str | None, explorer_base_url: str | None = None) -> str | None:
    if not address:
        return None
    base_url = (explorer_base_url or DEFAULT_ARC_EXPLORER_BASE_URL).rstrip("/")
    return f"{base_url}/address/{address}"


def proof_details(
    receipt: Receipt,
    contract_address: str | None = None,
    explorer_base_url: str | None = None,
) -> dict[str, Any]:
    payload = receipt_payload(receipt)
    payload_hash = canonical_hash(payload)
    status = "submitted" if receipt.tx_hash else "prepared"
    return {
        "mode": "evm",
        "status": status,
        "receipt_id": receipt.receipt_id,
        "network": receipt.network,
        "tx_hash": receipt.tx_hash,
        "explorer_url": explorer_tx_url(receipt.tx_hash, explorer_base_url),
        "registry_contract": contract_address,
        "registry_url": explorer_address_url(contract_address, explorer_base_url),
        "message": (
            "Archived Arc testnet transaction is available for verification."
            if receipt.tx_hash
            else "Proof payload is prepared and ready for Arc testnet submission."
        ),
        "payload_hash": payload_hash,
        "payload": payload,
    }


class ProofWriter:
    def __init__(self, config: Settings = settings) -> None:
        self.config = config
        self.mode = os.getenv("ARC_PROOF_MODE", "evm")
        self.rpc_url = os.getenv("ARC_RPC_URL") or self._rpc_from_arc_cli_config()
        self.contract_address = os.getenv("ARC_REASONING_REGISTRY_ADDRESS")
        self.explorer_base_url = os.getenv("ARC_EXPLORER_BASE_URL") or DEFAULT_ARC_EXPLORER_BASE_URL
        self.private_key = os.getenv("ARC_PRIVATE_KEY")

    def _rpc_from_arc_cli_config(self) -> str | None:
        if not ARC_CONFIG.exists():
            return None
        text = ARC_CONFIG.read_text(encoding="utf-8")
        match = re.search(r"server_token:\\s*['\"]?([^'\"\\s]+)", text)
        if not match:
            return None
        token = match.group(1)
        return f"https://rpc.testnet.arc-node.thecanteenapp.com/v1/{token}"

    def write(self, receipt: Receipt) -> ProofResult:
        payload = receipt_payload(receipt)
        payload_hash = canonical_hash(payload)
        if self.mode != "evm":
            return ProofResult(
                mode=self.mode,
                status="blocked",
                receipt_id=receipt.receipt_id,
                tx_hash=None,
                explorer_url=None,
                message="Only Arc testnet EVM proof mode is enabled for this product build.",
                payload_hash=payload_hash,
            )
        return self._write_evm(receipt, payload, payload_hash)

    def _write_evm(
        self,
        receipt: Receipt,
        payload: dict[str, Any],
        payload_hash: str,
    ) -> ProofResult:
        missing = []
        if not self.rpc_url:
            missing.append("ARC_RPC_URL")
        if not self.contract_address:
            missing.append("ARC_REASONING_REGISTRY_ADDRESS")
        if missing:
            return ProofResult(
                mode="evm",
                status="blocked",
                receipt_id=receipt.receipt_id,
                tx_hash=None,
                explorer_url=None,
                message=f"{' and '.join(missing)} required for Arc testnet proof mode.",
                payload_hash=payload_hash,
            )

        chain_id = self._rpc("eth_chainId", [])
        if not self.private_key:
            return ProofResult(
                mode="evm",
                status="prepared",
                receipt_id=receipt.receipt_id,
                tx_hash=None,
                explorer_url=None,
                message=(
                    f"Arc RPC reachable on chain {chain_id}. Set ARC_PRIVATE_KEY to submit "
                    f"the proof to ReasoningRegistry at {self.contract_address}."
                ),
                payload_hash=payload_hash,
            )

        try:
            tx_hash = self._send_registry_transaction(payload)
        except ImportError as exc:
            return ProofResult(
                mode="evm",
                status="blocked",
                receipt_id=receipt.receipt_id,
                tx_hash=None,
                explorer_url=None,
                message=f"EVM dependencies missing: {exc}. Install requirements-evm.txt.",
                payload_hash=payload_hash,
            )

        explorer_url = explorer_tx_url(tx_hash, self.explorer_base_url)
        return ProofResult(
            mode="evm",
            status="submitted",
            receipt_id=receipt.receipt_id,
            tx_hash=tx_hash,
            explorer_url=explorer_url,
            message=(
                f"Submitted proof transaction to Arc-compatible chain {chain_id} "
                f"via ReasoningRegistry at {self.contract_address}."
            ),
            payload_hash=payload_hash,
        )

    def _send_registry_transaction(self, payload: dict[str, Any]) -> str:
        try:
            from web3 import Web3
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ImportError("web3 is not installed") from exc

        if not self.rpc_url or not self.contract_address or not self.private_key:
            raise RuntimeError("ARC_RPC_URL, ARC_REASONING_REGISTRY_ADDRESS, and ARC_PRIVATE_KEY are required")

        abi = [
            {
                "inputs": [
                    {"internalType": "bytes32", "name": "recommendationHash", "type": "bytes32"},
                    {"internalType": "bytes32", "name": "evidenceHash", "type": "bytes32"},
                    {"internalType": "string", "name": "marketSlug", "type": "string"},
                    {"internalType": "string", "name": "signalId", "type": "string"},
                    {"internalType": "string", "name": "direction", "type": "string"},
                    {"internalType": "uint256", "name": "marketProbabilityBps", "type": "uint256"},
                    {"internalType": "uint256", "name": "agentProbabilityBps", "type": "uint256"},
                    {"internalType": "uint256", "name": "riskUnitSize", "type": "uint256"},
                ],
                "name": "recordRecommendation",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function",
            }
        ]

        web3 = Web3(Web3.HTTPProvider(self.rpc_url, request_kwargs={"timeout": self.config.request_timeout_seconds}))
        account = web3.eth.account.from_key(self.private_key)
        contract = web3.eth.contract(
            address=web3.to_checksum_address(self.contract_address),
            abi=abi,
        )
        function = contract.functions.recordRecommendation(
            bytes.fromhex(payload["recommendation_hash"].removeprefix("0x")),
            bytes.fromhex(payload["evidence_hash"].removeprefix("0x")),
            payload["market_slug"],
            payload["signal_id"],
            payload["direction"],
            payload["market_probability_bps"],
            payload["agent_probability_bps"],
            payload["risk_unit_size"],
        )
        transaction = function.build_transaction(
            {
                "from": account.address,
                "nonce": web3.eth.get_transaction_count(account.address),
                "chainId": web3.eth.chain_id,
            }
        )
        if "gas" not in transaction:
            transaction["gas"] = function.estimate_gas({"from": account.address})
        signed = web3.eth.account.sign_transaction(transaction, self.private_key)
        tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
        value = tx_hash.hex()
        return value if value.startswith("0x") else f"0x{value}"

    def _rpc(self, method: str, params: list[Any]) -> Any:
        if not self.rpc_url:
            raise RuntimeError("ARC_RPC_URL is not configured")
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        request = Request(self.rpc_url, data=body, headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=self.config.request_timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except URLError as exc:
            raise RuntimeError(f"Arc RPC request failed: {exc}") from exc
        if "error" in payload:
            raise RuntimeError(f"Arc RPC error: {payload['error']}")
        return payload.get("result")

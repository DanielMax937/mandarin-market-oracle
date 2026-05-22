#!/usr/bin/env python3
"""Print Arc testnet connectivity and wallet readiness."""

from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env.local")
    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def main() -> None:
    try:
        from web3 import Web3
    except ImportError as exc:
        raise SystemExit("Install EVM deps first: .venv/bin/python -m pip install -r requirements-evm.txt") from exc

    rpc_url = os.getenv("ARC_RPC_URL")
    address = os.getenv("ARC_TESTNET_ADDRESS")
    registry = os.getenv("ARC_REASONING_REGISTRY_ADDRESS")
    if not rpc_url:
        raise SystemExit("ARC_RPC_URL is not configured. Run arc-canteen login && arc-canteen rpc-url.")
    if not address:
        raise SystemExit("ARC_TESTNET_ADDRESS is not configured.")

    web3 = Web3(Web3.HTTPProvider(rpc_url))
    balance = web3.eth.get_balance(address)
    print(f"chain_id={web3.eth.chain_id}")
    print(f"address={address}")
    print(f"balance_wei={balance}")
    print(f"balance_native={web3.from_wei(balance, 'ether')}")
    print(f"registry={registry or 'not_configured'}")
    print(f"ready_for_deploy={'yes' if balance > 0 else 'no'}")


if __name__ == "__main__":
    main()

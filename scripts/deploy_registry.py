#!/usr/bin/env python3
"""Deploy ReasoningRegistry to an EVM-compatible Arc testnet.

Requires:
  pip install -r requirements-evm.txt
  ARC_RPC_URL=<rpc>
  ARC_PRIVATE_KEY=<testnet-only-private-key>

This script compiles with solc if available through py-solc-x. If solc is not
available, use Remix/Foundry to deploy contracts/ReasoningRegistry.sol and set
ARC_REASONING_REGISTRY_ADDRESS manually.
"""

from __future__ import annotations

import os
from pathlib import Path
import json
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env.local")
    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def main() -> None:
    rpc_url = os.getenv("ARC_RPC_URL")
    private_key = os.getenv("ARC_PRIVATE_KEY")
    if not rpc_url or not private_key:
        raise SystemExit("ARC_RPC_URL and ARC_PRIVATE_KEY are required")

    try:
        from web3 import Web3
    except ImportError as exc:
        raise SystemExit("Missing web3. Install with: .venv/bin/python -m pip install -r requirements-evm.txt") from exc

    contract_interface = compile_contract()

    web3 = Web3(Web3.HTTPProvider(rpc_url))
    account = web3.eth.account.from_key(private_key)
    contract = web3.eth.contract(
        abi=contract_interface["abi"],
        bytecode=contract_interface["bin"],
    )
    tx = contract.constructor().build_transaction(
        {
            "from": account.address,
            "nonce": web3.eth.get_transaction_count(account.address),
            "chainId": web3.eth.chain_id,
        }
    )
    if "gas" not in tx:
        tx["gas"] = web3.eth.estimate_gas(tx)
    signed = web3.eth.account.sign_transaction(tx, private_key)
    tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"deployment_tx={tx_hash.hex()}")
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
    print(f"contract_address={receipt.contractAddress}")


def compile_contract() -> dict:
    source_path = ROOT / "contracts" / "ReasoningRegistry.sol"
    solc_js = ROOT / "node_modules" / "solc" / "soljson.js"
    if solc_js.exists():
        compiler = """
const fs = require('fs');
const solc = require('__SOLC_PATH__');
const sourcePath = process.argv[2];
const source = fs.readFileSync(sourcePath, 'utf8');
const input = {
  language: 'Solidity',
  sources: { 'ReasoningRegistry.sol': { content: source } },
  settings: { outputSelection: { '*': { '*': ['abi', 'evm.bytecode.object'] } } }
};
const output = JSON.parse(solc.compile(JSON.stringify(input)));
if (output.errors) {
  const fatal = output.errors.filter((e) => e.severity === 'error');
  if (fatal.length) {
    console.error(fatal.map((e) => e.formattedMessage).join('\\n'));
    process.exit(1);
  }
}
const contract = output.contracts['ReasoningRegistry.sol']['ReasoningRegistry'];
console.log(JSON.stringify({ abi: contract.abi, bin: contract.evm.bytecode.object }));
""".replace("__SOLC_PATH__", str((ROOT / "node_modules" / "solc").resolve()))
        with tempfile.NamedTemporaryFile("w", suffix=".cjs", delete=False) as handle:
            handle.write(compiler)
            compiler_path = handle.name
        try:
            result = subprocess.run(
                ["node", compiler_path, str(source_path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise SystemExit(result.stderr or result.stdout)
        finally:
            Path(compiler_path).unlink(missing_ok=True)
        return json.loads(result.stdout)

    try:
        from solcx import compile_files, install_solc
    except ImportError as exc:
        raise SystemExit(
            "Missing compiler. Run `npm install solc@0.8.24` or install py-solc-x."
        ) from exc
    install_solc("0.8.24")
    compiled = compile_files(
        [str(source_path)],
        output_values=["abi", "bin"],
        solc_version="0.8.24",
    )
    return next(iter(compiled.values()))


if __name__ == "__main__":
    main()

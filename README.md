# Mandarin Market Oracle

Production-style Mandarin alpha desk for Polymarket research.

Mandarin Market Oracle reads real Chinese market/news signals, maps them to priced Polymarket markets, estimates fair probability, and records the reasoning hash on Arc testnet. It is intentionally read-only for Polymarket: no real orders, no custody, no deposits, and no real USDC transfer.

## What The Agent Does

1. Pulls live Mandarin signals from public Chinese data endpoints.
2. Classifies each signal by theme, credibility, velocity, freshness, and risk.
3. Searches live Polymarket markets through the proxy-aware Gamma client.
4. Requires a real market YES price; fallback pricing is disabled.
5. Produces a deterministic `YES`, `NO`, or `WAIT` research recommendation.
6. Keeps LLM reasoning on-demand; a trader clicks `Ask LLM Analyst` when explanation is needed.
7. Sizes exposure in testnet risk units for risk communication.
8. Writes the evidence hash and recommendation hash to the deployed Arc testnet registry.
9. Shows a live validation summary computed only from current recommendations and recorded Arc receipts.

## Real Data Sources

Current implemented sources:

- Eastmoney finance news API.
- Eastmoney Push2 A-share index tape.
- User-attested source intake with URL/source attribution.
- Polymarket Gamma market search and market pricing.
- Arc testnet RPC and deployed `ReasoningRegistry`.

Restricted social platforms such as Weibo/Xueqiu are not scraped with brittle or login-bypassing techniques. They enter through controlled intake unless an official or stable API is configured.

## Run Locally

```bash
python3 -m pip install -r requirements.txt
uvicorn oracle.api:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`.

CLI:

```bash
python3 scripts/run_agent.py --snapshot
```

## Proxy For Polymarket

Set this when your network needs a proxy:

```bash
export POLYMARKET_PROXY_URL=http://127.0.0.1:7890
```

The client checks `POLYMARKET_PROXY_URL`, then standard `HTTPS_PROXY` / `HTTP_PROXY`.

## OpenAI Reasoning Agent

The pricing engine is deterministic. The LLM layer is an on-demand analyst/explainer: it receives the Mandarin signal, live Polymarket market, market-implied probability, agent fair probability, edge, direction, and risk units only after the user clicks `Ask LLM Analyst`, then returns compact English JSON for the dashboard.

Keep real credentials in `.env.local`, which is ignored by git:

```bash
ORACLE_LLM_REASONING_ENABLED=true
OPENAI_BASE_URL=<openai-compatible-base-url>
OPENAI_MODEL=<model-name>
OPENAI_API_KEY=<secret>
```

The active prompt can be inspected at:

```bash
curl http://127.0.0.1:8000/api/agent/prompt
```

The actual analysis call is:

```bash
curl -X POST http://127.0.0.1:8000/api/recommendations/<signal-id>/reasoning
```

The dashboard links to the prompt from the decision panel and only spends model tokens after the analyst action.

## Live Validation

The app does not fall back to static records. The validation panel is computed from current live-source recommendations:

- live source coverage
- priced Polymarket market coverage
- average absolute edge
- WAIT count
- Arc proof coverage from recorded receipt hashes

Useful endpoints:

```bash
curl 'http://127.0.0.1:8000/api/snapshot'
curl 'http://127.0.0.1:8000/api/validation'
curl 'http://127.0.0.1:8000/api/proofs/<signal-id>/payload'
```

## Arc Testnet Proofs

Configure Arc testnet:

```bash
export ARC_PROOF_MODE=evm
export ARC_RPC_URL=<arc-testnet-rpc-url>
export ARC_REASONING_REGISTRY_ADDRESS=<deployed-contract-address>
export ARC_PRIVATE_KEY=<testnet-only-private-key>
```

Install EVM dependencies when submitting transactions:

```bash
.venv/bin/python -m pip install -r requirements-evm.txt
```

Write a proof:

```bash
curl -X POST http://127.0.0.1:8000/api/proofs/<signal-id>
```

The local workspace already has an Arc testnet registry deployed:

```text
0x219E7613F20f6170E02e3Ebfa87EBeC6A484d800
```

## Compliance Boundary

- Polymarket is read-only.
- Real order execution is disabled in code.
- No user funds are accepted or custodied.
- Risk sizing is informational and denominated as testnet risk units.
- Provenance is real Arc testnet activity when credentials are configured.

## Verification

```bash
make test
python3 scripts/arc_testnet_status.py
python3 scripts/run_agent.py --snapshot
```

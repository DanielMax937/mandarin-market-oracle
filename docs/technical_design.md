# Technical Design

Mandarin Market Oracle is a research agent for prediction markets. It reads real Mandarin market signals, maps them to priced Polymarket contracts, estimates fair probability, and writes provenance to Arc testnet.

## Architecture

```text
Live Mandarin sources
  -> Signal classifier
  -> Live Polymarket mapper
  -> Probability estimator
  -> On-demand OpenAI-compatible reasoning explainer
  -> Testnet risk sizing
  -> Arc testnet proof writer
  -> Proof ledger
  -> Live validation tracker
  -> Trading-desk dashboard
```

## Source Layer

Implemented collectors:

- Eastmoney finance news API.
- Eastmoney Push2 A-share index tape.
- Controlled user-attested source intake.

The system does not invent data when a source is unavailable. If no live source can be mapped to a priced Polymarket market, the API returns an empty/error state instead of falling back to static records.

## Polymarket Layer

`PolymarketClient` is proxy-aware and read-only. It searches Gamma markets and normalizes live market metadata. A recommendation requires a real YES price from Polymarket; the old neutral fallback price has been removed.

## Recommendation Layer

The estimator combines:

- signal credibility
- velocity
- freshness
- market liquidity
- source risk flags

It returns `YES`, `NO`, or `WAIT`. Sizing is shown as testnet risk units for risk communication only.

Each recommendation now includes a machine-readable decision trace: weighted credibility, velocity, freshness, risk penalties, liquidity adjustment, edge threshold, conviction, and capped Kelly fraction. This makes the agent's decision policy inspectable in the dashboard instead of hiding it inside one paragraph of rationale.

The LLM layer does not decide the trade direction or rewrite probabilities. It is called only after a user action through `/api/recommendations/{signal_id}/reasoning`. It receives the already computed market probability, agent probability, edge, direction, and risk units, then explains the Mandarin signal in English for judges and traders. The prompt version is `mandarin-alpha-v1`, exposed through `/api/agent/prompt`.

LLM credentials live in `.env.local` only:

- `OPENAI_BASE_URL`
- `OPENAI_MODEL`
- `OPENAI_API_KEY`
- `ORACLE_LLM_REASONING_ENABLED`

## Arc Testnet Layer

`ReasoningRegistry` stores recommendation hashes and emits proof events on Arc testnet. `ProofWriter` submits real EVM transactions when `ARC_RPC_URL`, `ARC_REASONING_REGISTRY_ADDRESS`, and a testnet-only `ARC_PRIVATE_KEY` are configured.

Submitted proof transaction hashes are persisted to `data/proof_receipts.json`; unsubmitted recommendations display `not submitted yet`.

The proof payload endpoint exposes the exact registry event payload and payload hash for any recommendation:

```text
/api/proofs/{signal_id}/payload
```

The payload endpoint is derived from the current live recommendation and recorded receipt state.

## Agent Trace Layer

The UI exposes the internal workflow as five agent responsibilities without
changing the underlying deterministic policy:

- Source Scout: source identity, freshness, credibility, and evidence trail.
- Market Mapper: selected Polymarket contract, candidate audit, and proxy labeling.
- Probability Estimator: market probability, agent fair probability, and edge.
- Risk Auditor: risk flags, edge threshold, and testnet-only risk units.
- Proof Recorder: prepared/submitted Arc proof state and hash identity.

This is presentation over real state. It does not add synthetic reasoning,
orders, seed data, or hidden model calls.

## Proof Ledger Layer

The dashboard derives a proof ledger from the current `/api/snapshot` response.
Each row links a live signal to its selected market, direction, edge, research
view hash, and Arc transaction status. Submitted rows can be verified on Arcscan;
prepared rows expose the exact event payload via `/api/proofs/{signal_id}/payload`.

## Live Validation Layer

`/api/validation` reports metrics computed from current live-source recommendations only: recommendation count, live source count, priced market count, average absolute edge, WAIT count, and proof coverage. It does not include replay windows, static outcomes, or synthetic price moves.

## Compliance Boundary

- No real Polymarket order placement.
- No custody.
- No real USDC transfer.
- No mainnet wallet support.
- Testnet gas only.

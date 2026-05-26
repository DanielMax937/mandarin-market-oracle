# Agora Submission Draft

## Project Name

Mandarin Market Oracle

## Problem

Prediction markets are mostly priced by English-language information flows. Many China macro, A-share, commodity, geopolitical, and Asia-session crypto signals appear first in Mandarin market channels.

## Product

Mandarin Market Oracle is an AI research agent that reads live Mandarin market signals, maps them to priced Polymarket markets, estimates fair probability, and writes each reasoning proof to Arc testnet.

One-line pitch:

English prediction markets price English news. Mandarin Market Oracle watches Mandarin market structure first, translates it into probability edge, and anchors the reasoning on Arc.

Core thesis:

The trade is not the product. The verifiable research view is the product.

Current real integrations:

- Eastmoney finance news.
- Eastmoney A-share index tape.
- Read-only Polymarket Gamma market data.
- On-demand OpenAI-compatible analyst reasoning for English explanations.
- Arc testnet EVM proof transactions.
- Live validation metrics computed from current recommendations and recorded Arc receipts.

## Differentiation

The agent starts earlier in the information chain than English-feed prediction-market agents. It explains why a Mandarin signal might affect a Polymarket price, shows the market-implied probability, shows the agent probability, and records the evidence hash. The LLM is deliberately used as an on-demand explanation layer, while the probability, edge, and risk sizing are computed by a deterministic engine.

The dashboard shows the decision trace directly: source credibility, flow velocity, freshness, risk penalties, liquidity adjustment, edge threshold, conviction, and capped Kelly sizing. This makes the agent's agency legible to judges.

## Agent Trace

The live dashboard now presents the agent as a five-stage workflow:

1. Source Scout: pulls and preserves current Mandarin source evidence.
2. Market Mapper: searches live priced Polymarket contracts and explains direct matches versus proxies.
3. Probability Estimator: computes market-implied probability, agent fair probability, and edge.
4. Risk Auditor: applies risk flags, edge thresholds, and testnet-only risk sizing.
5. Proof Recorder: prepares or submits the evidence hash and research-view hash to Arc testnet.

The LLM analyst is deliberately on-demand. It explains the already computed result in English, but it does not choose the market, alter the fair probability, or place orders.

## Proof Ledger

The Web3 verification rail includes a proof ledger for every current research view:

- live market slug
- direction and edge
- evidence hash
- research-view hash
- Arc transaction status
- explorer link when submitted

This makes the Arc layer visible as a product feature, not just a button in the demo.

## Judging Criteria Mapping

- Agentic sophistication: live source classification, market matching, probability estimation, risk auditing, LLM explanation, and proof recording are shown as separate agent responsibilities.
- Traction: the app is deployed online and reads current Eastmoney data plus real priced Polymarket markets; no static replay dataset is used.
- Arc/Circle usage: Arc testnet stores proof events for evidence hashes and research-view hashes. The project keeps a strict no-custody and no-real-order boundary.
- Innovation: the system brings Mandarin-first market structure into English prediction-market research before the signal is fully absorbed by English news flow.

## Safety

This is not a real-money trading system. It does not place Polymarket orders, custody funds, or transfer real USDC. Risk sizing is shown in testnet risk units and proofs target Arc testnet.

## Recording Flow

1. Open the live signal tape.
2. Select a Mandarin signal from Eastmoney news or A-share tape.
3. Show the mapped priced Polymarket market.
4. Compare market YES probability with agent fair probability.
5. Show `YES`, `NO`, or `WAIT` plus rationale.
6. Click `Ask LLM Analyst` to generate the OpenAI English explanation and show the active prompt.
7. Write the recommendation hash to Arc testnet.
8. Show the submitted transaction hash in the proof rail.
9. Use controlled intake only with an attributed real source and a priced market returned by live Polymarket search.

## Live Review Flow

The first screen is designed around live evidence:

- Current Eastmoney news and A-share tape signals.
- Read-only Polymarket Gamma market lookup with real YES prices.
- Registry event payload and payload hash for the selected live recommendation.
- Live validation metrics without replay outcomes or synthetic price moves.

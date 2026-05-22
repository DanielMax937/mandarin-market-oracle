# Agora Submission Draft

## Project Name

Mandarin Market Oracle

## Problem

Prediction markets are mostly priced by English-language information flows. Many China macro, A-share, commodity, geopolitical, and Asia-session crypto signals appear first in Mandarin market channels.

## Product

Mandarin Market Oracle is an AI research agent that reads live Mandarin market signals, maps them to priced Polymarket markets, estimates fair probability, and writes each reasoning proof to Arc testnet.

Current real integrations:

- Eastmoney finance news.
- Eastmoney A-share index tape.
- Read-only Polymarket Gamma market data.
- On-demand OpenAI-compatible analyst reasoning for English explanations.
- Arc testnet EVM proof transactions.

## Differentiation

The agent starts earlier in the information chain than English-feed prediction-market agents. It explains why a Mandarin signal might affect a Polymarket price, shows the market-implied probability, shows the agent probability, and records the evidence hash. The LLM is deliberately used as an on-demand explanation layer, while the probability, edge, and risk sizing are computed by a deterministic engine.

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

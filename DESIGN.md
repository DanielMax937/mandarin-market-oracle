---
name: Mandarin Alpha Trading Desk System
colors:
  primary: "#0A0F14"
  secondary: "#111820"
  tertiary: "#1B2631"
  accent: "#2DD4BF"
  neutral: "#D7DEE8"
typography:
  h1: "32px / 1.05, 800 weight, tight institutional display"
  body: "14px / 1.45, 500 weight, compact dashboard reading"
spacing:
  sm: "8px"
  md: "16px"
  lg: "24px"
rounded:
  sm: "4px"
  md: "8px"
---

## Overview

This design system serves a web dashboard for prediction-market traders and macro analysts. The tone is institutional, dense, calm, and evidence-led. The interface should feel like an intelligence desk rather than a marketing site: live signals, market probability, agent fair value, risk flags, and Arc testnet provenance should be visible without scrolling on desktop. The product promise is "Mandarin alpha for Polymarket", so the UI must foreground China-sourced signals and probability edge over decorative branding.

## Colors

`primary` is the page background and terminal shell. Use it for full-screen surfaces and high-trust context. `secondary` is the main panel surface. `tertiary` is for nested rows, input fields, selected cells, and compact metric blocks. `accent` is reserved for active selection, live state, testnet proof, and positive analytical confidence. `neutral` is the default text color. Use semantic overlays sparingly: green for YES/positive edge, red for NO/risk, amber for WAIT/requires confirmation, and blue only for external market links. Avoid pastel panels, large gradients, and decorative color fields.

## Typography

Use compact system sans fonts with tabular numbers. Headings should be direct and functional, not hero-like. H1 identifies the desk; H2/H3 describe selected signal and market context. Body copy should be short and scannable. Metric numbers use strong weight and tabular figures. Supporting labels are uppercase, small, and muted. Chinese headlines may be larger than English metadata but must wrap cleanly in dense panels.

## Layout

Desktop uses a three-column trading-desk grid: left signal intake/tape, center analysis and probability model, right Arc provenance/portfolio. The top area is a compact command bar plus a one-click demo strip, not a hero. Use 8px rhythm inside panels and 16px between major areas. Panels may be framed, but avoid nested decorative cards. Mobile stacks the same workflow in order: demo, signal tape, analysis, proof. Sticky side panels are allowed on desktop only.

## Components

Expected components include: command bar, status pills, signal tape rows, controlled intake form, market search results, selected-signal panel, score cells, probability comparison rail, agent decision block, risk list, evidence chain, receipt rows, proof action, and research budget summary. Inputs and buttons must be compact but at least 40px tall. Buttons use clear action labels. Selected rows show a left accent rail. Probability bars are functional data graphics, not decoration. Proof states must distinguish blocked, prepared, submitted, and failed.

## Do's and Don'ts

Do keep the first viewport operational and data dense. Do use tabular numbers, restrained borders, and strong contrast. Do make WAIT feel like a disciplined trading decision, not an error. Do show read-only Polymarket and Arc testnet status clearly. Do preserve compliance language around research-only recommendations and no real execution.

Don't use landing-page hero layouts, oversized marketing copy, rounded pill overload, decorative blobs, generic SaaS gradients, or fake performance claims. Don't hide risk flags below the fold. Don't make the interface look like consumer crypto speculation. Don't let long hashes or Chinese headlines overflow their panels. Don't imply real Polymarket trading or real USDC transfer.

const bankroll = 10000;
const maxPositionPct = 0.05;

const state = {
  recommendations: [],
  selectedSignalId: null,
  marketResults: [],
  selectedMarket: null,
  provenanceNetwork: "arc-testnet",
  verificationContract: null,
  agent: null,
};

const formatPct = (value) => `${Math.round(value * 100)}%`;
const formatUsdc = (value) =>
  `${Math.round(value).toLocaleString("en-US")} testnet risk units`;
const shortHash = (value) =>
  value ? `${value.slice(0, 10)}...${value.slice(-8)}` : "not submitted";

function renderSignals() {
  const list = document.querySelector("#signalList");
  document.querySelector("#signalCount").textContent = state.recommendations.length;

  list.innerHTML = state.recommendations
    .map(
      ({ signal }) => `
        <button class="signal-button ${signal.id === state.selectedSignalId ? "active" : ""}" data-signal="${signal.id}">
          <strong>${signal.headline_zh}</strong>
          <span>${signal.source} · ${signal.freshness_minutes}m ago</span>
        </button>
      `,
    )
    .join("");

  list.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedSignalId = button.dataset.signal;
      render();
    });
  });
}

function renderAnalysis() {
  const recommendation = state.recommendations.find(
    (item) => item.signal.id === state.selectedSignalId,
  );
  if (!recommendation) return;
  const { signal, market, decision, receipt } = recommendation;
  const reasoning = recommendation.llm_reasoning;

  document.querySelector("#signalHeadline").textContent = signal.headline_zh;
  document.querySelector("#signalTranslation").textContent = signal.headline_en;
  document.querySelector("#credibility").textContent = formatPct(signal.credibility);
  document.querySelector("#velocity").textContent = formatPct(signal.velocity);
  document.querySelector("#freshness").textContent = `${signal.freshness_minutes}m`;

  document.querySelector("#marketQuestion").textContent = market.question;
  const marketLink = document.querySelector("#marketLink");
  marketLink.href = `https://polymarket.com/event/${market.slug}`;
  marketLink.textContent = market.slug;
  document.querySelector("#marketProb").textContent = formatPct(decision.market_probability);
  document.querySelector("#agentProb").textContent = formatPct(decision.agent_probability);
  document.querySelector("#edge").textContent = `${decision.edge >= 0 ? "+" : ""}${formatPct(decision.edge)}`;
  document.querySelector("#marketBar").style.width = formatPct(decision.market_probability);
  document.querySelector("#agentBar").style.width = formatPct(decision.agent_probability);
  document.querySelector("#marketMeta").textContent =
    `${market.slug} · ${Math.round(market.liquidity_usdc).toLocaleString("en-US")} USDC liquidity · expires ${market.expiry.slice(0, 10)}`;

  const directionPill = document.querySelector("#directionPill");
  directionPill.textContent = decision.direction;
  directionPill.className = `direction-pill ${decision.direction.toLowerCase()}`;
  document.querySelector("#positionSize").textContent = formatUsdc(decision.risk_unit_size);
  document.querySelector("#decisionReason").textContent =
    reasoning?.final_explanation || decision.rationale;
  document.querySelector("#agentMode").textContent = state.agent?.mode || "Deterministic + LLM";
  document.querySelector("#agentModel").textContent = state.agent
    ? `${state.agent.provider} · ${state.agent.model}`
    : "openai-compatible";
  document.querySelector("#llmSummary").textContent =
    reasoning?.english_summary || "LLM analyst has not been run for this signal.";
  document.querySelector("#llmImpact").textContent =
    reasoning?.market_impact_path || "Click Ask LLM Analyst to generate an English causal explanation from the live Mandarin signal and priced Polymarket market.";
  document.querySelector("#llmProbability").textContent =
    reasoning?.probability_rationale || "The deterministic engine has already computed price, fair probability, edge, and risk units.";
  document.querySelector("#llmStatus").textContent = reasoning
    ? reasoning.error || `Prompt ${reasoning.prompt_version} · ${reasoning.model}`
    : "On-demand. No token spend until requested.";

  document.querySelector("#riskList").innerHTML = signal.risk_flags
    .map((flag) => `<li>${flag}</li>`)
    .join("");
  document.querySelector("#evidenceList").innerHTML = signal.evidence
    .map((item) => `<li>${item}</li>`)
    .join("");

  renderReceipt(receipt);
}

function renderReceipt(receipt) {
  const verified = Boolean(receipt.tx_hash);
  const statusClass = verified ? "verified" : "ready";
  const statusText = verified ? "On-chain verified" : "Ready to commit";
  const contractText = state.verificationContract || "contract not configured";
  const hashState = verified ? "Committed" : "Prepared";
  document.querySelector("#receiptCard").innerHTML = `
    <div class="verification-status ${statusClass}">
      <span>${statusText}</span>
      <strong>${state.provenanceNetwork}</strong>
    </div>
    <div class="web3-checks">
      <div>
        <span>Evidence hash</span>
        <strong>${hashState}</strong>
      </div>
      <div>
        <span>Recommendation hash</span>
        <strong>${hashState}</strong>
      </div>
      <div>
        <span>Funds moved</span>
        <strong>0</strong>
      </div>
    </div>
    <div class="receipt-row">
      <span class="receipt-label">Network</span>
      <span class="receipt-value">${state.provenanceNetwork}</span>
    </div>
    <div class="receipt-row">
      <span class="receipt-label">Registry Contract</span>
      <span class="receipt-value">${contractText}</span>
    </div>
    <div class="receipt-row">
      <span class="receipt-label">Reasoning Receipt</span>
      <span class="receipt-value">${receipt.receipt_id}</span>
    </div>
    <div class="receipt-row">
      <span class="receipt-label">Arc Tx Hash</span>
      <span class="receipt-value">${receipt.tx_hash || "click Write Arc Proof to submit"}</span>
    </div>
    <div class="receipt-row">
      <span class="receipt-label">Recommendation</span>
      <span class="receipt-value">${receipt.direction} · ${formatPct(receipt.agent_probability)} fair · ${formatUsdc(receipt.risk_unit_size)}</span>
    </div>
    <div class="receipt-row">
      <span class="receipt-label">Evidence Hash</span>
      <span class="receipt-value">${shortHash(receipt.evidence_hash)}</span>
    </div>
    <div class="receipt-row">
      <span class="receipt-label">Recommendation Hash</span>
      <span class="receipt-value">${shortHash(receipt.recommendation_hash)}</span>
    </div>
  `;
}

function render() {
  renderSignals();
  renderAnalysis();
}

function selectedRecommendation() {
  return state.recommendations.find((item) => item.signal.id === state.selectedSignalId);
}

function setupProofButton() {
  const button = document.querySelector("#writeProofButton");
  const status = document.querySelector("#proofStatus");
  button.addEventListener("click", async () => {
    const recommendation = selectedRecommendation();
    if (!recommendation) return;
    button.disabled = true;
    status.textContent = "Writing Arc proof...";
    try {
      const response = await fetch(`/api/proofs/${encodeURIComponent(recommendation.signal.id)}`, {
        method: "POST",
      });
      if (!response.ok) throw new Error(`API returned ${response.status}`);
      const proof = await response.json();
      status.textContent = `${proof.status}: ${proof.message} ${proof.tx_hash || proof.payload_hash}`;
      await loadData();
    } catch (error) {
      status.textContent = `Proof failed: ${error.message}`;
    } finally {
      button.disabled = false;
    }
  });
}

function setupReasoningButton() {
  const button = document.querySelector("#runReasoningButton");
  const status = document.querySelector("#llmStatus");
  button.addEventListener("click", async () => {
    const recommendation = selectedRecommendation();
    if (!recommendation) return;
    button.disabled = true;
    button.textContent = "Analyzing...";
    status.textContent = "Calling OpenAI-compatible analyst model...";
    try {
      const response = await fetch(
        `/api/recommendations/${encodeURIComponent(recommendation.signal.id)}/reasoning`,
        { method: "POST" },
      );
      if (!response.ok) throw new Error(`API returned ${response.status}`);
      const enriched = await response.json();
      state.recommendations = state.recommendations.map((item) =>
        item.signal.id === enriched.signal.id ? enriched : item,
      );
      state.selectedSignalId = enriched.signal.id;
      render();
    } catch (error) {
      status.textContent = `LLM reasoning failed: ${error.message}`;
    } finally {
      button.disabled = false;
      button.textContent = "Ask LLM Analyst";
    }
  });
}

function setupIntakeForm() {
  const form = document.querySelector("#intakeForm");
  const status = document.querySelector("#intakeStatus");
  const button = form.querySelector("button");
  const searchButton = document.querySelector("#marketSearchButton");

  searchButton.addEventListener("click", async () => {
    const query = document.querySelector("#marketQuery").value.trim();
    if (!query) {
      status.textContent = "Enter a Polymarket search query first.";
      return;
    }
    searchButton.disabled = true;
    status.textContent = "Searching Polymarket through read-only proxy-aware API...";
    try {
      const response = await fetch(`/api/polymarket/search?q=${encodeURIComponent(query)}&limit=6`);
      if (!response.ok) throw new Error(`API returned ${response.status}`);
      const payload = await response.json();
      state.marketResults = payload.results;
      state.selectedMarket = payload.results[0] || null;
      renderMarketResults();
      status.textContent = payload.results.length
        ? `Found ${payload.results.length} market candidates. Select one with a real YES price.`
        : "No priced Polymarket market found.";
    } catch (error) {
      status.textContent = `Polymarket search unavailable: ${error.message}`;
    } finally {
      searchButton.disabled = false;
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    button.disabled = true;
    status.textContent = "Submitting signal through controlled intake...";

    const payload = {
      headline_zh: document.querySelector("#intakeHeadline").value.trim(),
      source: document.querySelector("#intakeSource").value.trim(),
      theme: document.querySelector("#intakeTheme").value || null,
      source_type: "user_attested",
      freshness_minutes: 5,
    };
    if (state.selectedMarket) {
      payload.market_slug = state.selectedMarket.slug;
      payload.market_question = state.selectedMarket.question || state.selectedMarket.title;
      payload.market_category = state.selectedMarket.category || "polymarket-live";
      if (state.selectedMarket.yes_price == null) {
        status.textContent = "Selected market has no real YES price. Pick another market.";
        button.disabled = false;
        return;
      }
      payload.market_yes_price = state.selectedMarket.yes_price;
      payload.market_liquidity_usdc = state.selectedMarket.liquidity || 0;
      payload.market_volume_usdc = state.selectedMarket.volume || 0;
      payload.market_expiry = state.selectedMarket.expiry || null;
    }

    try {
      const response = await fetch("/api/intake/signals", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error(`API returned ${response.status}`);
      const result = await response.json();
      state.recommendations = [result.recommendation, ...state.recommendations];
      state.selectedSignalId = result.signal.id;
      form.reset();
      state.marketResults = [];
      state.selectedMarket = null;
      renderMarketResults();
      status.textContent = "Signal accepted. Recommendation and Arc testnet proof prepared.";
      render();
    } catch (error) {
      status.textContent = `Intake unavailable: ${error.message}`;
    } finally {
      button.disabled = false;
    }
  });
}

function renderMarketResults() {
  const container = document.querySelector("#marketResults");
  container.innerHTML = state.marketResults
    .map((market, index) => {
      const active = state.selectedMarket && market.slug === state.selectedMarket.slug;
      const price = market.yes_price == null ? "n/a" : formatPct(Number(market.yes_price));
      const liquidity = market.liquidity == null ? "n/a" : Math.round(market.liquidity).toLocaleString("en-US");
      return `
        <button class="market-result ${active ? "active" : ""}" type="button" data-index="${index}">
          <strong>${market.question || market.title || market.slug}</strong>
          <span>${price} YES · ${liquidity} USDC liquidity</span>
        </button>
      `;
    })
    .join("");

  container.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedMarket = state.marketResults[Number(button.dataset.index)];
      renderMarketResults();
    });
  });
}

async function loadData() {
  try {
    const snapshot = await fetch("/api/snapshot").then((response) => {
      if (!response.ok) throw new Error(`API returned ${response.status}`);
      return response.json();
    });
    state.recommendations = snapshot.recommendations;
    state.provenanceNetwork = snapshot.provenance_network || state.provenanceNetwork;
    state.verificationContract = snapshot.verification_contract || state.verificationContract;
    state.agent = snapshot.agent || state.agent;
  } catch (error) {
    throw new Error(`Live API unavailable: ${error.message}`);
  }

  if (!state.recommendations.length) {
    throw new Error("No live Mandarin signal could be mapped to a priced Polymarket market.");
  }
  state.selectedSignalId = state.recommendations[0].signal.id;
  render();
}

setupIntakeForm();
setupProofButton();
setupReasoningButton();
loadData().catch((error) => {
  document.body.innerHTML = `<pre>Unable to load live data: ${error.message}</pre>`;
});

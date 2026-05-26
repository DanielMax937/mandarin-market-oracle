const state = {
  recommendations: [],
  selectedSignalId: null,
  marketResults: [],
  selectedMarket: null,
  provenanceNetwork: "arc-testnet",
  verificationContract: null,
  agent: null,
  validation: null,
  proofDetails: {},
  activeProofStatusKey: null,
  loadError: null,
};

const escapeHtml = (value) =>
  String(value == null ? "" : value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  })[char]);

const formatPct = (value) => {
  if (value == null || Number.isNaN(Number(value))) return "n/a";
  const pct = Number(value) * 100;
  const digits = Math.abs(pct) < 10 && pct !== 0 ? 1 : 0;
  return `${pct.toFixed(digits)}%`;
};
const formatSignedPct = (value) => {
  if (value == null || Number.isNaN(Number(value))) return "n/a";
  return `${Number(value) >= 0 ? "+" : ""}${formatPct(value)}`;
};
const formatUsdc = (value) =>
  `${Math.round(value || 0).toLocaleString("en-US")} testnet risk units`;
const formatScore = (value) =>
  Number(value || 0).toFixed(1);
const shortHash = (value) =>
  value ? `${value.slice(0, 10)}...${value.slice(-8)}` : "not submitted";
const shortSlug = (value) =>
  value && value.length > 46 ? `${value.slice(0, 36)}...` : value || "unmapped";
const proofCacheKey = (signalId) => signalId;

async function requestJson(url, options = {}) {
  if (typeof XMLHttpRequest !== "undefined") {
    return new Promise((resolve, reject) => {
      const request = new XMLHttpRequest();
      request.open(options.method || "GET", url);
      const headers = options.headers || {};
      Object.keys(headers).forEach((key) => {
        const value = headers[key];
        request.setRequestHeader(key, value);
      });
      const finish = () => {
        if (request.readyState !== 4) return;
        if (request.status < 200 || request.status >= 300) {
          reject(new Error(`API returned ${request.status}`));
          return;
        }
        try {
          resolve(JSON.parse(request.responseText));
        } catch (error) {
          reject(error);
        }
      };
      request.onload = finish;
      request.onreadystatechange = finish;
      request.onerror = () => reject(new Error("Network request failed"));
      request.send(options.body || null);
    });
  }
  const response = await window.fetch(url, options);
  if (!response.ok) throw new Error(`API returned ${response.status}`);
  return response.json();
}

function selectedRecommendation() {
  return state.recommendations.find((item) => item.signal.id === state.selectedSignalId);
}

function renderStatus() {
  const status = document.querySelector("#modeStatus");
  const fallback = state.loadError ? `${state.loadError} ` : "";
  status.textContent =
    `${fallback}Live mode reads current Mandarin sources, maps them to priced Polymarket markets, ` +
    "and prepares real Arc testnet proof payloads.";
}

function renderValidation() {
  const validation = state.validation;
  const container = document.querySelector("#validationCards");
  if (!validation) {
    container.innerHTML = "";
    return;
  }
  const edge = validation.average_abs_edge == null ? "n/a" : formatPct(validation.average_abs_edge);
  container.innerHTML = `
    <div>
      <span>Proofed</span>
      <strong>${validation.proofed_count}/${validation.recommendation_count}</strong>
    </div>
    <div>
      <span>Live Sources</span>
      <strong>${validation.live_source_count}/${validation.recommendation_count}</strong>
    </div>
    <div>
      <span>Priced Markets</span>
      <strong>${validation.priced_market_count}/${validation.recommendation_count}</strong>
    </div>
    <div>
      <span>Avg Edge</span>
      <strong>${edge}</strong>
    </div>
  `;
}

function renderSignals() {
  const list = document.querySelector("#signalList");
  document.querySelector("#signalCount").textContent = state.recommendations.length;

  list.innerHTML = state.recommendations
    .map(({ signal, decision, receipt }) => {
      const proofLabel = receipt.tx_hash ? "Arc tx" : "proof ready";
      return `
        <button class="signal-button ${
          signal.id === state.selectedSignalId ? "active" : ""
        }" data-signal="${escapeHtml(signal.id)}">
          <strong>${escapeHtml(signal.headline_zh)}</strong>
          <span>${escapeHtml(signal.source)} · ${signal.freshness_minutes}m ago</span>
          <em>${escapeHtml(decision.direction)} · ${formatSignedPct(decision.edge)} edge · ${proofLabel}</em>
        </button>
      `;
    })
    .join("");

  list.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedSignalId = button.dataset.signal;
      render();
    });
  });
}

function renderAnalysis() {
  const recommendation = selectedRecommendation();
  if (!recommendation) return;
  const { signal, market, decision, receipt, decision_trace: trace } = recommendation;
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
  document.querySelector("#edge").textContent = formatSignedPct(decision.edge);
  document.querySelector("#marketBar").style.width = formatPct(decision.market_probability);
  document.querySelector("#agentBar").style.width = formatPct(decision.agent_probability);
  document.querySelector("#marketMeta").textContent =
    `${market.slug} · ${Math.round(market.liquidity_usdc).toLocaleString(
      "en-US",
    )} USDC liquidity · expires ${market.expiry.slice(0, 10)}`;
  renderMarketCandidates(recommendation.market_candidates || [], market.slug);

  const directionPill = document.querySelector("#directionPill");
  directionPill.textContent = decision.direction;
  directionPill.className = `direction-pill ${decision.direction.toLowerCase()}`;
  document.querySelector("#positionSize").textContent = formatUsdc(decision.risk_unit_size);
  document.querySelector("#decisionReason").textContent =
    (reasoning && reasoning.final_explanation) || decision.rationale;
  document.querySelector("#agentMode").textContent =
    (state.agent && state.agent.mode) || "Deterministic + LLM";
  document.querySelector("#agentModel").textContent = state.agent
    ? `${state.agent.provider} · ${state.agent.model}`
    : "openai-compatible";
  renderAgentWorkflow(recommendation);
  document.querySelector("#llmSummary").textContent =
    (reasoning && reasoning.english_summary) || "LLM analyst has not been run for this signal.";
  document.querySelector("#llmImpact").textContent =
    (reasoning && reasoning.market_impact_path) ||
    "Click Ask LLM Analyst to generate an English causal explanation from the live signal.";
  document.querySelector("#llmProbability").textContent =
    (reasoning && reasoning.probability_rationale) ||
    "The deterministic engine has already computed price, fair probability, edge, and risk units.";
  document.querySelector("#llmStatus").textContent = reasoning
    ? reasoning.error || `Prompt ${reasoning.prompt_version} · ${reasoning.model}`
    : "On-demand. No token spend until requested.";
  document.querySelector(".llm-reasoning a").href =
    `/api/agent/prompt?signal_id=${encodeURIComponent(signal.id)}`;

  renderDecisionTrace(trace);
  const currentProofKey = proofCacheKey(signal.id);
  if (state.activeProofStatusKey !== currentProofKey) {
    document.querySelector("#proofStatus").textContent = "";
    state.activeProofStatusKey = currentProofKey;
  }
  document.querySelector("#riskList").innerHTML = signal.risk_flags
    .map((flag) => `<li>${escapeHtml(flag)}</li>`)
    .join("");
  document.querySelector("#evidenceList").innerHTML = signal.evidence
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");

  renderReceipt(receipt, signal.id);
}

function renderAgentWorkflow(recommendation) {
  const container = document.querySelector("#agentWorkflow");
  if (!container) return;
  const { signal, market, decision, receipt, decision_trace: trace } = recommendation;
  const candidates = recommendation.market_candidates || [];
  const selectedCandidate = candidates.find(
    (candidate) => candidate.selected || (candidate.market && candidate.market.slug === market.slug),
  );
  const outputs = (trace && trace.outputs) || {};
  const directness = selectedCandidate
    ? selectedCandidate.match_label
    : "Priced market match";
  const proofStatus = receipt.tx_hash ? "Submitted" : "Prepared";
  const proofCopy = receipt.tx_hash
    ? `Evidence and research hashes are committed on ${state.provenanceNetwork}.`
    : `Evidence and research hashes are ready to submit to ${state.provenanceNetwork}.`;
  const stages = [
    {
      role: "Source Scout",
      badge: String(signal.source_type || "live source").replace(/_/g, " "),
      metric: formatPct(signal.credibility),
      copy: `${signal.source}; ${signal.freshness_minutes}m old; Mandarin evidence preserved for review.`,
    },
    {
      role: "Market Mapper",
      badge: directness,
      metric: `${Math.max(candidates.length, 1)} candidates`,
      copy: `Selected ${shortSlug(market.slug)}. ${
        selectedCandidate ? selectedCandidate.reason : "Mapped from live priced Polymarket search."
      }`,
    },
    {
      role: "Probability Estimator",
      badge: "Deterministic",
      metric: formatSignedPct(decision.edge),
      copy: `Market YES ${formatPct(decision.market_probability)} vs agent fair ${formatPct(
        decision.agent_probability,
      )}; formula uses credibility, velocity, freshness, risk, and liquidity.`,
    },
    {
      role: "Risk Auditor",
      badge: decision.direction,
      metric: formatUsdc(decision.risk_unit_size),
      copy: `${signal.risk_flags.length} risk flags checked. ${
        outputs.direction_rule || "Direction is gated by edge threshold before any testnet risk sizing."
      }`,
    },
    {
      role: "Proof Recorder",
      badge: proofStatus,
      metric: shortHash(receipt.tx_hash || receipt.recommendation_hash),
      copy: proofCopy,
    },
  ];

  container.innerHTML = `
    <div class="agent-workflow-header">
      <span>Agent Trace</span>
      <strong>5-stage live workflow</strong>
    </div>
    <div class="agent-step-list">
      ${stages
        .map(
          (stage) => `
            <div class="agent-step">
              <div>
                <span>${escapeHtml(stage.role)}</span>
                <strong>${escapeHtml(stage.metric)}</strong>
              </div>
              <p>
                <em>${escapeHtml(stage.badge)}</em>
                ${escapeHtml(stage.copy)}
              </p>
            </div>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderMarketCandidates(candidates, selectedSlug) {
  const container = document.querySelector("#candidateMarkets");
  if (!container) return;
  if (!candidates.length) {
    container.innerHTML = `
      <div class="candidate-header">
        <span>Market Match Audit</span>
        <strong>No sufficiently relevant market</strong>
      </div>
      <p class="candidate-empty">No priced Polymarket candidate passed the relevance filter for this signal.</p>
    `;
    return;
  }
  container.innerHTML = `
    <div class="candidate-header">
      <span>Market Match Audit</span>
      <strong>Top ${Math.min(candidates.length, 3)} candidates</strong>
    </div>
    <div class="candidate-list">
      ${candidates
        .map((candidate) => {
          const market = candidate.market || {};
          const selected = candidate.selected || market.slug === selectedSlug;
          const proxy = candidate.match_label === "Best available proxy";
          const className = `candidate-item ${selected ? "selected" : ""} ${proxy ? "proxy" : ""}`;
          return `
            <div class="${className}">
              <div class="candidate-topline">
                <span>${selected ? "Selected" : "Candidate"}</span>
                <strong>${formatScore(candidate.relevance_score)}</strong>
              </div>
              <h4>${escapeHtml(market.question || market.slug || "Unknown market")}</h4>
              <p>${escapeHtml(candidate.reason || candidate.match_label)}</p>
              <small>${escapeHtml(candidate.match_label)} · ${escapeHtml(market.slug || "")}</small>
            </div>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderDecisionTrace(trace) {
  const inputs = document.querySelector("#traceInputs");
  const adjustments = document.querySelector("#traceAdjustments");
  const rule = document.querySelector("#traceRule");
  if (!trace || !trace.inputs) {
    inputs.innerHTML = "";
    adjustments.innerHTML = "";
    rule.textContent = "Decision trace unavailable for this research view.";
    return;
  }
  inputs.innerHTML = trace.inputs
    .map(
      (item) => `
        <div>
          <span>${escapeHtml(item.label)}</span>
          <strong>${formatPct(item.value)}</strong>
          <small>${escapeHtml(item.why)}</small>
        </div>
      `,
    )
    .join("");
  adjustments.innerHTML = trace.adjustments
    .map(
      (item) => `
        <div>
          <span>${escapeHtml(item.label)}</span>
          <strong>${formatSignedPct(item.value)}</strong>
          <small>${escapeHtml(item.why)}</small>
        </div>
      `,
    )
    .join("");
  const outputs = trace.outputs;
  rule.textContent =
    `${outputs.direction_rule} Conviction ${formatPct(outputs.conviction)}, ` +
    `Kelly cap ${formatPct(outputs.kelly_fraction_capped)}, max ${formatPct(outputs.max_position_pct)}.`;
}

function renderReceipt(receipt, signalId) {
  const verified = Boolean(receipt.tx_hash);
  const statusClass = verified ? "verified" : "ready";
  const statusText = verified ? "On-chain verified" : "Ready to commit";
  const contractText = state.verificationContract || "contract not configured";
  const hashState = verified ? "Committed" : "Prepared";
  const details = state.proofDetails[proofCacheKey(signalId)];
  const explorerLink = details && details.explorer_url
    ? `<a href="${escapeHtml(details.explorer_url)}" target="_blank" rel="noreferrer">Open Arc tx</a>`
    : "";
  const contractLink = details && details.registry_url
    ? `<a href="${escapeHtml(details.registry_url)}" target="_blank" rel="noreferrer">Open contract</a>`
    : "";

  document.querySelector("#receiptCard").innerHTML = `
    <div class="verification-status ${statusClass}">
      <span>${statusText}</span>
      <strong>${escapeHtml(state.provenanceNetwork)}</strong>
    </div>
    <div class="web3-checks">
      <div>
        <span>Evidence hash</span>
        <strong>${hashState}</strong>
      </div>
      <div>
        <span>Research view hash</span>
        <strong>${hashState}</strong>
      </div>
      <div>
        <span>Funds moved</span>
        <strong>0</strong>
      </div>
    </div>
    <div class="receipt-row">
      <span class="receipt-label">Network</span>
      <span class="receipt-value">${escapeHtml(state.provenanceNetwork)}</span>
    </div>
    <div class="receipt-row">
      <span class="receipt-label">Registry Contract</span>
      <span class="receipt-value">${escapeHtml(contractText)} ${contractLink}</span>
    </div>
    <div class="receipt-row">
      <span class="receipt-label">Reasoning Receipt</span>
      <span class="receipt-value">${escapeHtml(receipt.receipt_id)}</span>
    </div>
    <div class="receipt-row">
      <span class="receipt-label">Arc Tx Hash</span>
      <span class="receipt-value">
        ${escapeHtml(receipt.tx_hash || "click Write Arc Proof to submit")} ${explorerLink}
      </span>
    </div>
    <div class="receipt-row">
      <span class="receipt-label">Payload Hash</span>
      <span class="receipt-value">${escapeHtml((details && details.payload_hash) || "loading payload hash")}</span>
    </div>
    <div class="receipt-row">
      <span class="receipt-label">Research View</span>
      <span class="receipt-value">${escapeHtml(receipt.direction)} · ${formatPct(
        receipt.agent_probability,
      )} fair · ${formatUsdc(receipt.risk_unit_size)}</span>
    </div>
    <div class="receipt-row">
      <span class="receipt-label">Evidence Hash</span>
      <span class="receipt-value">${shortHash(receipt.evidence_hash)}</span>
    </div>
    <div class="receipt-row">
      <span class="receipt-label">Research View Hash</span>
      <span class="receipt-value">${shortHash(receipt.recommendation_hash)}</span>
    </div>
  `;
  renderProofPayload(details);
  loadProofDetails(signalId);
}

function renderProofPayload(details) {
  const container = document.querySelector("#proofPayload");
  if (!details || !details.payload) {
    container.innerHTML = `
      <span>Registry Event Payload</span>
      <pre>Loading proof payload...</pre>
    `;
    return;
  }
  container.innerHTML = `
    <span>Registry Event Payload</span>
    <pre>${escapeHtml(JSON.stringify(details.payload, null, 2))}</pre>
  `;
}

async function loadProofDetails(signalId) {
  const key = proofCacheKey(signalId);
  if (state.proofDetails[key]) return;
  state.proofDetails[key] = { loading: true };
  try {
    state.proofDetails[key] = await requestJson(
      `/api/proofs/${encodeURIComponent(signalId)}/payload`,
    );
    if (state.selectedSignalId === signalId) renderReceipt(selectedRecommendation().receipt, signalId);
  } catch (error) {
    state.proofDetails[key] = { error: error.message };
    document.querySelector("#proofPayload").innerHTML = `
      <span>Registry Event Payload</span>
      <pre>Unable to load proof payload: ${escapeHtml(error.message)}</pre>
    `;
  }
}

function render() {
  renderStatus();
  renderValidation();
  renderSignals();
  renderAnalysis();
  renderProofLedger();
  const proofButton = document.querySelector("#writeProofButton");
  proofButton.textContent = "Write Arc Proof";
}

function renderProofLedger() {
  const container = document.querySelector("#proofLedger");
  if (!container) return;
  if (!state.recommendations.length) {
    container.innerHTML = "";
    return;
  }
  const submitted = state.recommendations.filter((item) => item.receipt.tx_hash).length;
  container.innerHTML = `
    <div class="proof-ledger-header">
      <span>Proof Ledger</span>
      <strong>${submitted}/${state.recommendations.length} submitted</strong>
    </div>
    <div class="proof-ledger-list">
      ${state.recommendations
        .map(({ signal, market, decision, receipt }) => {
          const active = signal.id === state.selectedSignalId;
          const status = receipt.tx_hash ? "Arc tx" : "prepared";
          return `
            <button class="proof-ledger-row ${active ? "active" : ""}" type="button" data-signal="${escapeHtml(signal.id)}">
              <span>
                <strong>${escapeHtml(status)}</strong>
                <em>${escapeHtml(decision.direction)} · ${formatSignedPct(decision.edge)}</em>
              </span>
              <b>${escapeHtml(shortSlug(market.slug))}</b>
              <small>${escapeHtml(shortHash(receipt.tx_hash || receipt.recommendation_hash))}</small>
            </button>
          `;
        })
        .join("")}
    </div>
  `;
  container.querySelectorAll(".proof-ledger-row").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedSignalId = button.dataset.signal;
      render();
    });
  });
}

function setupProofButton() {
  const button = document.querySelector("#writeProofButton");
  const status = document.querySelector("#proofStatus");
  if (!button || !status) return;
  button.addEventListener("click", async () => {
    const recommendation = selectedRecommendation();
    if (!recommendation) return;
    button.disabled = true;
    status.textContent = "Writing Arc proof...";
    try {
      const proof = await requestJson(
        `/api/proofs/${encodeURIComponent(recommendation.signal.id)}`,
        { method: "POST" },
      );
      state.proofDetails[proofCacheKey(recommendation.signal.id)] = proof;
      status.textContent = `${proof.status}: ${proof.message} ${proof.tx_hash || proof.payload_hash}`;
      await loadData({ preserveSelection: true });
      render();
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
  if (!button || !status) return;
  button.addEventListener("click", async () => {
    const recommendation = selectedRecommendation();
    if (!recommendation) return;
    button.disabled = true;
    button.textContent = "Analyzing...";
    status.textContent = "Calling OpenAI-compatible analyst model...";
    try {
      const enriched = await requestJson(
        `/api/recommendations/${encodeURIComponent(recommendation.signal.id)}/reasoning`,
        { method: "POST" },
      );
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
  if (!form || !status) return;
  const button = form.querySelector('button[type="submit"]');
  const searchButton = document.querySelector("#marketSearchButton");
  if (!button) return;

  if (searchButton) {
    searchButton.addEventListener("click", async () => {
      const query = document.querySelector("#marketQuery").value.trim();
      if (!query) {
        status.textContent = "Enter a Polymarket search query first.";
        return;
      }
      searchButton.disabled = true;
      status.textContent = "Searching Polymarket through read-only proxy-aware API...";
      try {
        const payload = await requestJson(`/api/polymarket/search?q=${encodeURIComponent(query)}&limit=6`);
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
  }

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
      const result = await requestJson("/api/intake/signals", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      state.recommendations = [result.recommendation, ...state.recommendations];
      state.selectedSignalId = result.signal.id;
      form.reset();
      state.marketResults = [];
      state.selectedMarket = null;
      renderMarketResults();
      status.textContent = "Signal accepted. Research view and Arc testnet proof prepared.";
      await loadData({ preserveSelection: true });
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
      const liquidity =
        market.liquidity == null ? "n/a" : Math.round(market.liquidity).toLocaleString("en-US");
      return `
        <button class="market-result ${active ? "active" : ""}" type="button" data-index="${index}">
          <strong>${escapeHtml(market.question || market.title || market.slug)}</strong>
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

async function loadData(options = {}) {
  const { preserveSelection = false } = options;
  const previousSelection = preserveSelection ? state.selectedSignalId : null;
  try {
    document.querySelector("#modeStatus").textContent = "Loading live data...";
    const snapshot = await requestJson("/api/snapshot");
    document.querySelector("#modeStatus").textContent =
      `Loaded ${snapshot.recommendations.length} live research views.`;
    state.recommendations = snapshot.recommendations;
    state.provenanceNetwork = snapshot.provenance_network || state.provenanceNetwork;
    state.verificationContract = snapshot.verification_contract || state.verificationContract;
    state.agent = snapshot.agent || state.agent;
    state.validation = snapshot.validation || null;
  } catch (error) {
    state.loadError = error.message;
    renderStatus();
    throw error;
  }

  if (!state.recommendations.length) {
    throw new Error("No Mandarin signal could be mapped to a priced Polymarket market.");
  }
  const stillExists = state.recommendations.some((item) => item.signal.id === previousSelection);
  state.selectedSignalId = stillExists ? previousSelection : state.recommendations[0].signal.id;
  render();
}

setupIntakeForm();
setupProofButton();
setupReasoningButton();
loadData().catch((error) => {
  document.querySelector("#modeStatus").textContent = `Unable to load data: ${error.message}`;
});

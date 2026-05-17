const state = {
  signals: [],
  filtered: [],
  charts: {},
  autoRefreshSeconds: 60,
  countdown: 60,
  pipelineRunning: false,
  seenHighPriority: new Set(),
};

const $ = (id) => document.getElementById(id);

async function fetchDashboard() {
  const response = await fetch("/api/dashboard");
  if (response.status === 401) {
    window.location.href = "/login";
    return { signals: [], summary: {} };
  }
  if (!response.ok) throw new Error("Unable to load dashboard data");
  return response.json();
}

function setStatus(text) {
  $("statusText").textContent = text;
}

function formatDate(value) {
  if (!value) return "No date";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function signalTime(signal) {
  return new Date(signal.published_at || signal.fetched_at || 0);
}

function startOfDay(date) {
  const result = new Date(date);
  result.setHours(0, 0, 0, 0);
  return result;
}

function endOfDay(date) {
  const result = new Date(date);
  result.setHours(23, 59, 59, 999);
  return result;
}

function matchesDateFilter(signal, preset, fromValue, toValue) {
  const timestamp = signalTime(signal);
  if (Number.isNaN(timestamp.getTime())) return false;

  const now = new Date();
  const todayStart = startOfDay(now);
  const todayEnd = endOfDay(now);
  const yesterday = new Date(todayStart);
  yesterday.setDate(yesterday.getDate() - 1);
  const yesterdayStart = startOfDay(yesterday);
  const yesterdayEnd = endOfDay(yesterday);

  if (preset === "today") {
    return timestamp >= todayStart && timestamp <= todayEnd;
  }
  if (preset === "yesterday") {
    return timestamp >= yesterdayStart && timestamp <= yesterdayEnd;
  }
  if (preset === "last7") {
    const start = new Date(todayStart);
    start.setDate(start.getDate() - 6);
    return timestamp >= start && timestamp <= todayEnd;
  }
  if (preset === "last30") {
    const start = new Date(todayStart);
    start.setDate(start.getDate() - 29);
    return timestamp >= start && timestamp <= todayEnd;
  }

  if (preset === "custom" || fromValue || toValue) {
    const fromDate = fromValue ? startOfDay(new Date(fromValue)) : null;
    const toDate = toValue ? endOfDay(new Date(toValue)) : null;
    if (fromDate && timestamp < fromDate) return false;
    if (toDate && timestamp > toDate) return false;
  }

  return true;
}

function formatDateGroup(value) {
  if (!value) return "No Date";
  return new Intl.DateTimeFormat(undefined, {
    weekday: "short",
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(value));
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function uniqueValues(field) {
  return [...new Set(state.signals.map((signal) => signal[field]).filter(Boolean))].sort();
}

function populateSelect(id, values) {
  const select = $(id);
  const first = select.options[0];
  select.innerHTML = "";
  select.appendChild(first);
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value.replaceAll("_", " ");
    select.appendChild(option);
  });
}

function hydrateFilters() {
  populateSelect("eventFilter", uniqueValues("event_type"));
  populateSelect("sentimentFilter", uniqueValues("sentiment"));
  populateSelect("suggestionFilter", uniqueValues("suggestion"));
  populateSelect("priorityFilter", uniqueValues("priority"));
  populateSelect("riskFilter", uniqueValues("risk_level"));
}

function summarize(signals) {
  const empty = {
    total: signals.length,
    buy: 0,
    sell: 0,
    high_priority: 0,
    avg_confidence: 0,
    avg_score: 0,
    suggestions: {},
    event_types: {},
    priorities: {},
    risks: {},
    top_stocks: [],
    action_queue: [],
  };

  if (!signals.length) return empty;

  const stockCounts = {};
  let confidence = 0;
  let score = 0;
  signals.forEach((signal) => {
    empty.suggestions[signal.suggestion] = (empty.suggestions[signal.suggestion] || 0) + 1;
    empty.event_types[signal.event_type] = (empty.event_types[signal.event_type] || 0) + 1;
    empty.priorities[signal.priority] = (empty.priorities[signal.priority] || 0) + 1;
    empty.risks[signal.risk_level] = (empty.risks[signal.risk_level] || 0) + 1;
    if (signal.suggestion === "BUY") empty.buy += 1;
    if (signal.suggestion === "SELL") empty.sell += 1;
    if (signal.priority === "HIGH") empty.high_priority += 1;
    confidence += Number(signal.confidence || 0);
    score += Math.abs(Number(signal.signal_score || 0));
    signal.stocks.forEach((stock) => {
      stockCounts[stock] = (stockCounts[stock] || 0) + 1;
    });
  });

  empty.avg_confidence = confidence / signals.length;
  empty.avg_score = score / signals.length;
  empty.top_stocks = Object.entries(stockCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8);
  empty.action_queue = signals
    .filter((signal) => ["BUY", "SELL"].includes(signal.suggestion))
    .sort((a, b) => Math.abs(b.signal_score) - Math.abs(a.signal_score))
    .slice(0, 6);
  return empty;
}

function applyFilters() {
  const search = $("searchInput").value.trim().toLowerCase();
  const watchlist = $("watchlistInput").value
    .split(",")
    .map((item) => item.trim().toUpperCase())
    .filter(Boolean);
  const eventType = $("eventFilter").value;
  const sentiment = $("sentimentFilter").value;
  const suggestion = $("suggestionFilter").value;
  const priority = $("priorityFilter").value;
  const risk = $("riskFilter").value;
  const datePreset = $("dateFilter").value;
  const dateFrom = $("dateFromFilter").value;
  const dateTo = $("dateToFilter").value;
  const sortMode = $("sortFilter").value;
  const minConfidence = Number($("confidenceFilter").value);
  $("confidenceValue").textContent = minConfidence.toFixed(2);

  state.filtered = state.signals.filter((signal) => {
    const haystack = [
      signal.headline,
      signal.source,
      signal.reasoning,
      signal.event_type,
      signal.sentiment,
      signal.suggestion,
      signal.priority,
      signal.risk_level,
      signal.stocks.join(" "),
    ]
      .join(" ")
      .toLowerCase();

    return (
      (!search || haystack.includes(search)) &&
      (!watchlist.length || signal.stocks.some((stock) => watchlist.includes(stock.toUpperCase()))) &&
      (!eventType || signal.event_type === eventType) &&
      (!sentiment || signal.sentiment === sentiment) &&
      (!suggestion || signal.suggestion === suggestion) &&
      (!priority || signal.priority === priority) &&
      (!risk || signal.risk_level === risk) &&
      matchesDateFilter(signal, datePreset, dateFrom, dateTo) &&
      Number(signal.confidence || 0) >= minConfidence
    );
  });

  const priorityRank = { HIGH: 3, MEDIUM: 2, LOW: 1 };
  state.filtered.sort((a, b) => {
    if (sortMode === "score") return Math.abs(b.signal_score) - Math.abs(a.signal_score);
    if (sortMode === "confidence") return b.confidence - a.confidence;
    if (sortMode === "oldest") return signalTime(a) - signalTime(b);
    if (sortMode === "newest") return signalTime(b) - signalTime(a);
    return (
      (priorityRank[b.priority] || 0) - (priorityRank[a.priority] || 0) ||
      Math.abs(b.signal_score) - Math.abs(a.signal_score) ||
      b.confidence - a.confidence ||
      signalTime(b) - signalTime(a)
    );
  });

  render();
}

function renderMetrics(summary) {
  $("totalSignals").textContent = summary.total;
  $("buySignals").textContent = summary.buy;
  $("sellSignals").textContent = summary.sell;
  $("highPriority").textContent = summary.high_priority;
  $("avgScore").textContent = Number(summary.avg_score || 0).toFixed(1);
  $("avgConfidence").textContent = Number(summary.avg_confidence || 0).toFixed(2);
}

function renderChart(canvasId, type, labels, data, colors) {
  if (state.charts[canvasId]) state.charts[canvasId].destroy();
  state.charts[canvasId] = new Chart($(canvasId), {
    type,
    data: {
      labels,
      datasets: [
        {
          data,
          backgroundColor: colors,
          borderWidth: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom" },
      },
      scales: type === "bar" ? { y: { beginAtZero: true, ticks: { precision: 0 } } } : {},
    },
  });
}

function renderStocks(summary) {
  const max = Math.max(...summary.top_stocks.map((item) => item[1]), 1);
  $("stockBars").innerHTML = summary.top_stocks
    .map(([stock, count]) => {
      const width = Math.round((count / max) * 100);
      return `
        <div class="stock-row">
          <strong>${escapeHtml(stock)}</strong>
          <div class="bar"><span style="width:${width}%"></span></div>
          <span>${count}</span>
        </div>
      `;
    })
    .join("") || "<p class=\"meta\">No stock mentions yet.</p>";
}

function renderActionQueue(summary) {
  $("actionQueue").innerHTML = summary.action_queue
    .map((signal) => `
      <div class="mini-item">
        <div class="mini-title">${escapeHtml(signal.headline)}</div>
        <div class="mini-meta">
          <span>${escapeHtml(signal.suggestion)}</span>
          <span>${escapeHtml(signal.priority || "LOW")} priority</span>
          <span>${escapeHtml(signal.risk_level || "LOW")} risk</span>
          <span>Score ${Number(signal.signal_score || 0).toFixed(1)}</span>
        </div>
      </div>
    `)
    .join("") || "<p class=\"meta\">No actionable BUY or SELL signals yet.</p>";
}

function renderQuotes(quotes = []) {
  $("quoteList").innerHTML = quotes
    .map((quote) => {
      const cls = quote.change_pct >= 0 ? "quote-up" : "quote-down";
      const sign = quote.change_pct >= 0 ? "+" : "";
      return `
        <div class="mini-item">
          <div class="mini-title">${escapeHtml(quote.ticker)}</div>
          <div class="mini-meta">
            <span>Close ${quote.close}</span>
            <span class="${cls}">${sign}${quote.change_pct}%</span>
            <span>Vol ${Number(quote.volume || 0).toLocaleString()}</span>
          </div>
        </div>
      `;
    })
    .join("") || "<p class=\"meta\">Press Load Prices for a live yFinance snapshot.</p>";
}

function renderSourceHealth(sources = []) {
  $("sourceHealth").innerHTML = sources
    .map((source) => `
      <div class="mini-item">
        <div class="mini-title">${escapeHtml(source.source)}</div>
        <div class="mini-meta">
          <span>${escapeHtml(source.status)}</span>
          <span>${Number(source.item_count || 0)} items</span>
          <span>${escapeHtml(formatDate(source.checked_at))}</span>
        </div>
      </div>
    `)
    .join("") || "<p class=\"meta\">Source health appears after the next server refresh.</p>";
}

function renderAlerts(alerts = []) {
  $("alertList").innerHTML = alerts
    .map((alert) => `
      <div class="mini-item">
        <div class="mini-title">${escapeHtml(alert.status)}</div>
        <div class="mini-meta">
          <span>${escapeHtml(alert.channel)}</span>
          <span>${escapeHtml(formatDate(alert.sent_at))}</span>
        </div>
        <p class="meta">${escapeHtml(alert.message)}</p>
      </div>
    `)
    .join("") || "<p class=\"meta\">High-priority alerts will appear here.</p>";
}

function notifyHighPriority(signals) {
  const actionable = signals.filter((signal) =>
    signal.priority === "HIGH" &&
    ["BUY", "SELL"].includes(signal.suggestion) &&
    Math.abs(Number(signal.signal_score || 0)) >= 80
  );

  actionable.forEach((signal) => {
    if (state.seenHighPriority.has(signal.news_id)) return;
    state.seenHighPriority.add(signal.news_id);
    if (Notification.permission === "granted") {
      new Notification(`${signal.suggestion} ${signal.stocks.join(", ")}`, {
        body: `${signal.headline} | score ${Number(signal.signal_score || 0).toFixed(1)}`,
      });
    }
  });
}

function renderSignals() {
  let lastGroup = "";
  $("signalList").innerHTML = state.filtered
    .map((signal) => {
      const dateValue = signal.published_at || signal.fetched_at;
      const group = formatDateGroup(dateValue);
      const groupHeader = group !== lastGroup
        ? `<div class="date-group"><span>${escapeHtml(group)}</span></div>`
        : "";
      lastGroup = group;
      const suggestionClass = String(signal.suggestion || "").toLowerCase();
      const priorityClass = String(signal.priority || "LOW").toLowerCase();
      const riskClass = `risk-${String(signal.risk_level || "LOW").toLowerCase()}`;
      const sourceLink = signal.url
        ? `<a href="${escapeHtml(signal.url)}" target="_blank" rel="noreferrer">${escapeHtml(signal.source)}</a>`
        : escapeHtml(signal.source);
      return `
        ${groupHeader}
        <article class="signal-card">
          <div>
            <p class="headline">${escapeHtml(signal.headline)}</p>
            <div class="meta">
              <span>${sourceLink}</span>
              <span>${formatDate(signal.published_at || signal.fetched_at)}</span>
              <span>${escapeHtml(signal.impact_horizon.replaceAll("_", " "))}</span>
            </div>
            <p class="reasoning">${escapeHtml(signal.reasoning)}</p>
            <div class="reasons">
              ${(signal.confidence_reasons || []).map((reason) => `<span class="reason">${escapeHtml(reason)}</span>`).join("")}
            </div>
            <div class="chips">
              <span class="chip ${escapeHtml(suggestionClass)}">${escapeHtml(signal.suggestion)}</span>
              <span class="chip">${escapeHtml(signal.sentiment)}</span>
              <span class="chip">${escapeHtml(signal.event_type.replaceAll("_", " "))}</span>
              <span class="chip ${escapeHtml(priorityClass)}">${escapeHtml(signal.priority || "LOW")} PRIORITY</span>
              <span class="chip ${escapeHtml(riskClass)}">${escapeHtml(signal.risk_level || "LOW")} RISK</span>
              ${signal.stocks.map((stock) => `<span class="chip">${escapeHtml(stock)}</span>`).join("")}
            </div>
            <div class="card-actions">
              <button type="button" class="telegram-btn" data-news-id="${escapeHtml(signal.news_id)}">Send Telegram</button>
              <span class="telegram-status" id="telegram-status-${escapeHtml(signal.news_id)}"></span>
            </div>
          </div>
          <div class="score-box">
            <strong>${Number(signal.confidence || 0).toFixed(2)}</strong>
            <span>conf</span>
            <strong>${Number(signal.signal_score || 0).toFixed(1)}</strong>
            <span>score</span>
          </div>
        </article>
      `;
    })
    .join("") || "<p class=\"meta\">No signals match the current filters.</p>";
}

async function sendTelegram(newsId) {
  const statusNode = document.getElementById(`telegram-status-${newsId}`);
  if (statusNode) statusNode.textContent = "Sending...";
  try {
    const response = await fetch(`/api/send-telegram/${encodeURIComponent(newsId)}`, {
      method: "POST",
    });
    const data = await response.json();
    if (statusNode) statusNode.textContent = data.status || "Sent";
    loadOperationalPanels();
  } catch (error) {
    if (statusNode) statusNode.textContent = "Failed";
  }
}

function render() {
  const summary = summarize(state.filtered);
  renderMetrics(summary);
  renderChart(
    "suggestionChart",
    "doughnut",
    Object.keys(summary.suggestions),
    Object.values(summary.suggestions),
    ["#0f8b5f", "#c2413b", "#52606d", "#936a00"]
  );
  renderChart(
    "eventChart",
    "bar",
    Object.keys(summary.event_types).map((label) => label.replaceAll("_", " ")),
    Object.values(summary.event_types),
    ["#2457c5", "#0f8b5f", "#936a00", "#c2413b", "#52606d"]
  );
  renderChart(
    "priorityChart",
    "doughnut",
    Object.keys(summary.priorities),
    Object.values(summary.priorities),
    ["#2457c5", "#936a00", "#52606d"]
  );
  renderChart(
    "riskChart",
    "doughnut",
    Object.keys(summary.risks),
    Object.values(summary.risks),
    ["#c2413b", "#936a00", "#0f8b5f"]
  );
  renderStocks(summary);
  renderActionQueue(summary);
  renderSignals();
  document.querySelectorAll(".telegram-btn").forEach((button) => {
    button.addEventListener("click", () => sendTelegram(button.dataset.newsId));
  });
  setStatus(`${state.filtered.length} of ${state.signals.length} signals shown`);
}

async function loadQuotes() {
  $("quotesBtn").disabled = true;
  $("quoteList").innerHTML = "<p class=\"meta\">Loading market prices...</p>";
  try {
    const tickers = [...new Set(state.filtered.flatMap((signal) => signal.stocks))]
      .filter((ticker) => ticker.endsWith(".NS"))
      .slice(0, 12)
      .join(",");
    const response = await fetch(`/api/quotes?tickers=${encodeURIComponent(tickers)}`);
    const data = await response.json();
    renderQuotes(data.quotes || []);
  } catch (error) {
    $("quoteList").innerHTML = `<p class="meta">${escapeHtml(error.message)}</p>`;
  } finally {
    $("quotesBtn").disabled = false;
  }
}

async function refreshPipeline() {
  if (state.pipelineRunning) return;
  state.pipelineRunning = true;
  $("refreshBtn").disabled = true;
  setStatus("Fetching and analyzing fresh news...");
  try {
    const response = await fetch("/api/run-pipeline", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ limit: 30 }),
    });
    const stats = await response.json();
    await load();
    state.countdown = state.autoRefreshSeconds;
    updateCountdown();
    setStatus(`Pipeline finished: ${stats.processed} processed, ${stats.duplicates} already stored. Next auto refresh in ${state.autoRefreshSeconds}s.`);
  } catch (error) {
    setStatus(error.message);
  } finally {
    $("refreshBtn").disabled = false;
    state.pipelineRunning = false;
  }
}

async function syncDashboard() {
  await load();
  setStatus(`Synced at ${new Date().toLocaleTimeString()}. Server scheduler keeps fetching news in the background.`);
}

async function resetDatabase() {
  if (!confirm("Reset all stored news signals and vectors?")) return;
  $("resetBtn").disabled = true;
  try {
    await fetch("/api/reset-db", { method: "POST" });
    await load();
    setStatus("Database reset.");
  } finally {
    $("resetBtn").disabled = false;
  }
}

async function load() {
  const data = await fetchDashboard();
  state.signals = data.signals;
  state.filtered = data.signals;
  hydrateFilters();
  applyFilters();
  notifyHighPriority(data.signals);
  loadOperationalPanels();
}

async function loadOperationalPanels() {
  try {
    const [healthResponse, alertsResponse] = await Promise.all([
      fetch("/api/source-health"),
      fetch("/api/alerts"),
    ]);
    if (healthResponse.ok) {
      const health = await healthResponse.json();
      renderSourceHealth(health.sources || []);
    }
    if (alertsResponse.ok) {
      const alerts = await alertsResponse.json();
      renderAlerts(alerts.alerts || []);
    }
  } catch (error) {
    renderSourceHealth([]);
  }
}

function updateCountdown() {
  $("refreshCountdown").textContent = state.countdown;
}

function startAutoRefresh() {
  updateCountdown();
  window.setInterval(() => {
    if (!$("autoRefreshToggle").checked) {
      $("refreshCountdown").textContent = "off";
      return;
    }

    state.countdown -= 1;
    if (state.countdown <= 0) {
      state.countdown = state.autoRefreshSeconds;
      syncDashboard();
    }
    updateCountdown();
  }, 1000);
}

[
  "searchInput",
  "watchlistInput",
  "eventFilter",
  "sentimentFilter",
  "suggestionFilter",
  "priorityFilter",
  "riskFilter",
  "dateFilter",
  "dateFromFilter",
  "dateToFilter",
  "sortFilter",
  "confidenceFilter",
].forEach((id) => {
  $(id).addEventListener("input", applyFilters);
});

$("quotesBtn").addEventListener("click", loadQuotes);
$("refreshBtn").addEventListener("click", refreshPipeline);
$("resetBtn").addEventListener("click", resetDatabase);
$("autoRefreshToggle").addEventListener("change", () => {
  state.countdown = state.autoRefreshSeconds;
  updateCountdown();
});

load().catch((error) => setStatus(error.message));
startAutoRefresh();
if ("Notification" in window && Notification.permission === "default") {
  Notification.requestPermission();
}

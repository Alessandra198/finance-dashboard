/**
 * Chart.js dashboards: overview (doughnut | stacked bar), savings rate, expense size histogram, merchants (pie | bar).
 */

if (typeof Chart !== "undefined") {
  Chart.defaults.font.family = "'Lora', Cambria, 'Hoefler Text', Georgia, serif";
  Chart.defaults.color = "#3d4a39";
  Chart.defaults.maintainAspectRatio = false;
}

const sage = {
  income: "#5B8A72",
  expense: "#C4786E",
  net: "#7A9B6E",
  grid: "rgba(61, 74, 57, 0.12)",
  text: "#3d4a39",
};

let overviewChart;
let savingsChart;
let expenseSizeChart;
let merchantChart;

/** Expense-only histogram: absolute purchase amount in dollars → bucket index. */
const EXPENSE_SIZE_BUCKET_LABELS = ["Under $25", "$25–100", "$100–250", "$250–500", "$500+"];

/** Light → deep sage for increasing bucket size. */
const EXPENSE_SIZE_BUCKET_COLORS = ["#c5e0d1", "#9ccbb2", "#7aab8f", sage.income, "#3d6548"];

let lastSummary = null;
let lastTransactions = [];

let overviewMode = "doughnut";
let merchantMode = "pie";

function destroyChart(ch) {
  if (ch) ch.destroy();
}

function expenseDollarsFromTxn(t) {
  const c = Number(t?.amount_cents);
  if (!Number.isFinite(c) || c >= 0) return null;
  return Math.abs(c) / 100;
}

function countExpenseSizeBuckets(transactions) {
  const counts = [0, 0, 0, 0, 0];
  for (const t of transactions || []) {
    const d = expenseDollarsFromTxn(t);
    if (d == null) continue;
    if (d < 25) counts[0] += 1;
    else if (d < 100) counts[1] += 1;
    else if (d < 250) counts[2] += 1;
    else if (d < 500) counts[3] += 1;
    else counts[4] += 1;
  }
  return counts;
}

function topMerchantsFromTransactions(transactions, topN = 10) {
  const map = new Map();
  for (const t of transactions || []) {
    const cents = Number(t.amount_cents);
    if (!Number.isFinite(cents) || cents >= 0) continue;
    const key = (t.description || "").trim() || "(no description)";
    map.set(key, (map.get(key) || 0) + Math.abs(cents));
  }
  return Array.from(map.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, topN);
}

function renderOverview() {
  if (!lastSummary) return;
  const ctx = document.getElementById("overviewChart")?.getContext("2d");
  if (!ctx) return;

  const summary = lastSummary;
  destroyChart(overviewChart);

  if (overviewMode === "doughnut") {
    const inc = summary.income_cents / 100;
    const exp = summary.expense_cents / 100;
    overviewChart = new Chart(ctx, {
      type: "doughnut",
      data: {
        labels: ["Income", "Expenses"],
        datasets: [
          {
            data: [inc, exp],
            backgroundColor: [sage.income, sage.expense],
            borderWidth: 2,
            borderColor: "#f4f6f2",
            hoverOffset: 6,
          },
        ],
      },
      options: {
        responsive: true,
        layout: { padding: 4 },
        plugins: {
          legend: { position: "bottom", labels: { boxWidth: 10 } },
          tooltip: {
            callbacks: {
              label: (c) => `${c.label}: $${Number(c.parsed).toFixed(2)}`,
            },
          },
        },
      },
    });
    return;
  }

  const monthly = summary.monthly && summary.monthly.length ? summary.monthly : [];
  const labels = monthly.length ? monthly.map((m) => m.month.slice(0, 7)) : ["—"];
  const income = monthly.length ? monthly.map((m) => m.income_cents / 100) : [0];
  const expense = monthly.length ? monthly.map((m) => m.expense_cents / 100) : [0];

  overviewChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Income",
          data: income,
          backgroundColor: sage.income,
          stack: "s",
        },
        {
          label: "Expenses",
          data: expense,
          backgroundColor: sage.expense,
          stack: "s",
        },
      ],
    },
    options: {
      responsive: true,
      layout: { padding: 4 },
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 10 } },
        tooltip: {
          callbacks: {
            label: (c) => `${c.dataset.label}: $${Number(c.parsed.y).toFixed(2)}`,
          },
        },
      },
      scales: {
        x: { stacked: true, grid: { color: sage.grid }, ticks: { maxRotation: 45 } },
        y: {
          stacked: true,
          beginAtZero: true,
          grid: { color: sage.grid },
          ticks: {
            callback: (v) => `$${v}`,
            maxTicksLimit: 6,
          },
        },
      },
    },
  });
}

function renderSavings() {
  if (!lastSummary) return;
  const ctx = document.getElementById("savingsChart")?.getContext("2d");
  if (!ctx) return;

  const monthly = lastSummary.monthly && lastSummary.monthly.length ? lastSummary.monthly : [];
  const labels = monthly.length ? monthly.map((m) => m.month.slice(0, 7)) : ["—"];
  const rates = monthly.length
    ? monthly.map((m) => {
        const inc = m.income_cents;
        if (!inc || inc <= 0) return 0;
        return (m.net_cents / inc) * 100;
      })
    : [0];

  destroyChart(savingsChart);
  savingsChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Savings rate (%)",
          data: rates,
          backgroundColor: sage.net,
          borderColor: sage.income,
          borderWidth: 1,
        },
      ],
    },
    options: {
      responsive: true,
      layout: { padding: 4 },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (c) => `${c.parsed.y.toFixed(1)}%`,
          },
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: { maxRotation: 45 } },
        y: {
          beginAtZero: true,
          suggestedMax: 100,
          grid: { color: sage.grid },
          ticks: {
            callback: (v) => `${v}%`,
            maxTicksLimit: 5,
          },
        },
      },
    },
  });
}

function renderExpenseSizeHistogram() {
  const ctx = document.getElementById("expenseSizeChart")?.getContext("2d");
  if (!ctx) return;

  const counts = countExpenseSizeBuckets(lastTransactions);
  const labels = EXPENSE_SIZE_BUCKET_LABELS;
  destroyChart(expenseSizeChart);

  expenseSizeChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Transactions",
          data: counts,
          backgroundColor: EXPENSE_SIZE_BUCKET_COLORS,
          borderWidth: 1,
          borderColor: "#f4f6f2",
        },
      ],
    },
    options: {
      responsive: true,
      layout: { padding: 4 },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (c) => {
              const n = Number(c.parsed.y);
              return `${n} transaction${n === 1 ? "" : "s"}`;
            },
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { maxRotation: 0, autoSkip: false, font: { size: 11 } },
        },
        y: {
          beginAtZero: true,
          grace: "5%",
          grid: { color: sage.grid },
          ticks: {
            precision: 0,
            maxTicksLimit: 8,
          },
        },
      },
    },
  });
}

/**
 * Merchant colors (rank order): light, airy tints that match --accent / --card / sage.* on the site,
 * not deep jewel tones. Hues alternate warm ↔ cool so large wedges stay easy to tell apart.
 */
const MERCHANT_PALETTE = [
  sage.income, // #5B8A72 — same as UI accent / overview income
  sage.expense, // #C4786E — same as expense / overview expense
  "#A8C5D4", // soft dusk blue (pairs with sage UI cool notes)
  "#D4C896", // pale brass / oat
  "#8ECBC0", // sea-mist teal
  "#C4A8C8", // wisteria mist
  "#D1B8AC", // blush stone (near #f4f6f2 card warmth)
  "#B5CF9E", // spring green (lighter cousin of sage.net)
  "#E0A8A8", // tea rose
  "#B4C2E0", // airy periwinkle
  "#D4B85C", // soft harvest gold
  sage.net, // #7A9B6E — savings / net green
  "#E8B8A8", // apricot clay
  "#C8B898", // greige wheat
  "#D8B8D0", // orchid haze
  "#B8D4B0", // washed sage
  "#C8C4DC", // lilac gray
];

function merchantColors(n) {
  if (n <= 0) return [];
  if (n <= MERCHANT_PALETTE.length) return MERCHANT_PALETTE.slice(0, n);
  const out = MERCHANT_PALETTE.slice();
  let i = 0;
  while (out.length < n) {
    out.push(MERCHANT_PALETTE[i % MERCHANT_PALETTE.length]);
    i += 1;
  }
  return out;
}

/** Two columns: left has ceil(n/2) rows, right the rest (even n → equal rows; odd n → left has one extra). */
function renderMerchantLegend(labels, colors) {
  const el = document.getElementById("merchantLegend");
  if (!el) return;

  if (!labels.length) {
    el.innerHTML = "";
    el.hidden = true;
    return;
  }

  el.hidden = false;
  el.innerHTML = "";

  const n = labels.length;
  const leftCount = Math.ceil(n / 2);
  const colLeft = document.createElement("div");
  colLeft.className = "merchantLegendCol";
  const colRight = document.createElement("div");
  colRight.className = "merchantLegendCol";

  for (let i = 0; i < leftCount; i++) {
    colLeft.appendChild(_merchantLegendRow(labels[i], colors[i]));
  }
  for (let j = leftCount; j < n; j++) {
    colRight.appendChild(_merchantLegendRow(labels[j], colors[j]));
  }

  el.appendChild(colLeft);
  el.appendChild(colRight);
}

function _merchantLegendRow(text, color) {
  const row = document.createElement("div");
  row.className = "merchantLegendItem";
  const sw = document.createElement("span");
  sw.className = "merchantLegendSwatch";
  sw.style.backgroundColor = color;
  sw.setAttribute("aria-hidden", "true");
  const t = document.createElement("span");
  t.className = "merchantLegendLabel";
  t.textContent = text;
  row.appendChild(sw);
  row.appendChild(t);
  return row;
}

function renderMerchants() {
  const ctx = document.getElementById("merchantChart")?.getContext("2d");
  if (!ctx) return;

  const merchantCard = document.querySelector(".chartCard--merchant");
  if (merchantCard) {
    merchantCard.classList.toggle("chartCard--merchant--stack", merchantMode === "bar");
  }

  const top = topMerchantsFromTransactions(lastTransactions, 10);
  const labels = top.map(([name]) => name);
  const values = top.map(([, cents]) => cents / 100);
  const colors = merchantColors(labels.length);

  destroyChart(merchantChart);

  if (top.length === 0) {
    renderMerchantLegend([], []);
    merchantChart = new Chart(ctx, {
      type: "bar",
      data: { labels: ["—"], datasets: [{ label: "Expense ($)", data: [0], backgroundColor: sage.grid }] },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true } },
      },
    });
    return;
  }

  renderMerchantLegend(labels, colors);

  if (merchantMode === "pie") {
    merchantChart = new Chart(ctx, {
      type: "pie",
      data: {
        labels,
        datasets: [
          {
            data: values,
            backgroundColor: colors,
            borderWidth: 2,
            borderColor: "#f4f6f2",
          },
        ],
      },
      options: {
        responsive: true,
        layout: { padding: 4 },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (c) => `${c.label}: $${Number(c.parsed).toFixed(2)}`,
            },
          },
        },
      },
    });
    return;
  }

  merchantChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Expense ($)",
          data: values,
          backgroundColor: colors,
          borderWidth: 1,
          borderColor: "#f4f6f2",
        },
      ],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      layout: { padding: 4 },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (c) => `$${Number(c.parsed.x).toFixed(2)}`,
          },
        },
      },
      scales: {
        x: {
          beginAtZero: true,
          grid: { color: sage.grid },
          ticks: { callback: (v) => `$${v}`, maxTicksLimit: 5 },
        },
        y: { grid: { display: false }, ticks: { font: { size: 10 } } },
      },
    },
  });
}

function renderCharts(summary, transactions) {
  lastSummary = summary;
  lastTransactions = Array.isArray(transactions) ? transactions : [];
  renderOverview();
  renderSavings();
  renderExpenseSizeHistogram();
  renderMerchants();
}

function initChartControls() {
  document.querySelectorAll('.toggleBtn[data-chart="overview"]').forEach((btn) => {
    btn.addEventListener("click", () => {
      overviewMode = btn.dataset.mode || "doughnut";
      document.querySelectorAll('.toggleBtn[data-chart="overview"]').forEach((b) => {
        b.classList.toggle("active", b.dataset.mode === overviewMode);
      });
      renderOverview();
    });
  });

  document.querySelectorAll('.toggleBtn[data-chart="merchant"]').forEach((btn) => {
    btn.addEventListener("click", () => {
      merchantMode = btn.dataset.mode || "pie";
      document.querySelectorAll('.toggleBtn[data-chart="merchant"]').forEach((b) => {
        b.classList.toggle("active", b.dataset.mode === merchantMode);
      });
      renderMerchants();
    });
  });
}

window.renderCharts = renderCharts;
window.initChartControls = initChartControls;

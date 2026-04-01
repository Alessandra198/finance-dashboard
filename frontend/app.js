const API_BASE = (() => {
  if (window.FINANCE_API_BASE) return String(window.FINANCE_API_BASE);
  const { protocol, hostname, origin } = window.location;
  if (hostname === "127.0.0.1" || hostname === "localhost") {
    return `${protocol}//127.0.0.1:8000/api`;
  }
  return `${origin}/api`;
})();
const ENABLE_MOCK = false;
const USE_MOCK = ENABLE_MOCK && new URLSearchParams(window.location.search).get("mock") === "1";

const LS = {
  users: "fd_mock_users",
  session: "fd_mock_session",
  txns: "fd_mock_txns",
};
const LS_REMEMBER_EMAIL = "fd_remember_email";
let lastSavedTxnId = null;
let toastSeq = 0;
const CHARTS_SCRIPT_VERSION = "20260327-5";
const CHARTS_CACHE_TTL_MS = 90_000;
const chartsSummaryCache = new Map();
const chartsTxCache = new Map();
let chartsLoaderPromise = null;
let chartsControlsInitialized = false;
let chartsRequestSeq = 0;
let sessionReadOnly = false;

function nowIsoLocalInput() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

function dollarsInputToCents(raw) {
  const n = Number(String(raw ?? "").trim());
  if (!Number.isFinite(n)) throw new Error("Please enter a valid amount");
  const cents = Math.round(n * 100);
  if (cents === 0) throw new Error("amount cannot be 0");
  return cents;
}

function centsToDollarsInput(cents) {
  const n = Number(cents || 0) / 100;
  const fixed = n.toFixed(2);
  return fixed.endsWith(".00") ? fixed.slice(0, -3) : fixed;
}

/** Recent list "When" column: local date and time to the minute only. */
function formatRecentWhen(isoOrDate) {
  const d = new Date(isoOrDate);
  if (!Number.isFinite(d.getTime())) return String(isoOrDate ?? "");
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function waitMs(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function debounce(fn, ms) {
  let timer = null;
  return (...args) => {
    if (timer) window.clearTimeout(timer);
    timer = window.setTimeout(() => fn(...args), ms);
  };
}

function applyRememberedLoginEmail() {
  const emailInput = document.getElementById("email");
  const rememberChk = document.getElementById("loginRememberMe");
  if (!emailInput || !rememberChk) return;
  const stored = localStorage.getItem(LS_REMEMBER_EMAIL);
  if (stored) {
    emailInput.value = stored;
    rememberChk.checked = true;
  } else {
    emailInput.value = "";
    rememberChk.checked = false;
  }
}

function invalidateChartsCache() {
  chartsSummaryCache.clear();
  chartsTxCache.clear();
  chartsRequestSeq += 1;
}

function _cacheGet(map, key) {
  const hit = map.get(key);
  if (!hit) return null;
  if (Date.now() - hit.ts > CHARTS_CACHE_TTL_MS) {
    map.delete(key);
    return null;
  }
  return hit.data;
}

function _cacheSet(map, key, data) {
  map.set(key, { ts: Date.now(), data });
}

function loadChartsScript() {
  if (typeof window.renderCharts === "function" && typeof window.initChartControls === "function") {
    return Promise.resolve();
  }
  if (chartsLoaderPromise) return chartsLoaderPromise;
  chartsLoaderPromise = new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = `charts.js?v=${CHARTS_SCRIPT_VERSION}`;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("Could not load charts module"));
    document.head.appendChild(s);
  });
  return chartsLoaderPromise;
}

async function ensureChartsReady() {
  await loadChartsScript();
  if (!chartsControlsInitialized && typeof window.initChartControls === "function") {
    window.initChartControls();
    chartsControlsInitialized = true;
  }
}

async function sha256Hex(input) {
  const bytes = new TextEncoder().encode(String(input ?? ""));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const arr = Array.from(new Uint8Array(digest));
  return arr.map((b) => b.toString(16).padStart(2, "0")).join("");
}

function showReloadOverlay() {
  const el = document.getElementById("reloadOverlay");
  if (!el) return;
  el.classList.remove("is-hiding");
  el.classList.add("is-visible");
}

async function hideReloadOverlay() {
  const el = document.getElementById("reloadOverlay");
  if (!el) return;
  el.classList.add("is-hiding");
  await waitMs(170);
  el.classList.remove("is-visible", "is-hiding");
}

function setStatus(message, { error } = {}) {
  const el = document.getElementById("status");
  if (!el) return;
  el.textContent = message || "";
  el.classList.toggle("error", Boolean(error));
}

function setTxnStatus(message, { error } = {}) {
  const el = document.getElementById("txnStatus");
  if (!el) return;
  el.textContent = message || "";
  el.classList.toggle("error", Boolean(error));
}

function applyReadOnlyUi() {
  const banner = document.getElementById("readOnlyBanner");
  if (banner) banner.hidden = !sessionReadOnly;
  const form = document.getElementById("txnForm");
  if (!form) return;
  for (const el of form.querySelectorAll("input:not([type=hidden]), button[type=submit]")) {
    el.disabled = sessionReadOnly;
  }
}

function showToast(message, { kind = "info", duration = 2200 } = {}) {
  const stack = document.getElementById("toastStack");
  if (!stack || !message) return;
  const toast = document.createElement("div");
  const id = ++toastSeq;
  toast.className = `toast toast--${kind}`;
  toast.dataset.toastId = String(id);
  toast.textContent = message;
  stack.appendChild(toast);
  window.setTimeout(() => {
    toast.classList.add("toast--out");
    window.setTimeout(() => toast.remove(), 180);
  }, duration);
}

function showView(name) {
  const authScreens = document.getElementById("authScreens");
  const views = ["authLoginView", "authRegisterView", "dashboardView", "chartsView"];
  for (const id of views) {
    const el = document.getElementById(id);
    if (el) el.hidden = id !== name;
  }
  if (authScreens) {
    const onAuth = name === "authLoginView" || name === "authRegisterView";
    authScreens.hidden = !onAuth;
  }
  const tabs = document.getElementById("tabs");
  if (tabs) tabs.hidden = name === "authLoginView" || name === "authRegisterView";

  for (const btn of document.querySelectorAll(".tab[data-view]")) {
    btn.classList.toggle("active", btn.dataset.view + "View" === name);
  }
}

function readJson(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

function mockEnsureSeeded() {
  const users = readJson(LS.users, []);
  if (users.length === 0) {
    const mockEmail =
      typeof window.FINANCE_MOCK_USER_EMAIL === "string" ? window.FINANCE_MOCK_USER_EMAIL.trim() : "";
    if (mockEmail) {
      const demoHash = "5a57206c20e693c1b24fc68dae83c71b0008e043099943cde61a99a8a9c07b64";
      writeJson(LS.users, [{ id: 1, email: mockEmail, password_hash: demoHash, read_only: false }]);
    } else {
      writeJson(LS.users, []);
    }
  }
  const txns = readJson(LS.txns, []);
  if (txns.length === 0) {
    writeJson(LS.txns, []);
  }
}

function mockGetSession() {
  return readJson(LS.session, null);
}

function mockSetSession(user) {
  writeJson(LS.session, {
    id: user.id,
    email: user.email,
    read_only: Boolean(user.read_only),
  });
}

function mockClearSession() {
  localStorage.removeItem(LS.session);
}

function parseHttpError(data, status) {
  return new Error(data?.detail || `Request failed (${status})`);
}

async function apiFetch(path, opts = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(opts.headers || {}),
    },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw parseHttpError(data, res.status);
  return data;
}

const mockApi = {
  async register({ email, password }) {
    mockEnsureSeeded();
    email = (email || "").trim().toLowerCase();
    if (!email) throw new Error("Email is required");
    if (!password || password.length < 8) throw new Error("Password must be at least 8 characters");

    const users = readJson(LS.users, []);
    if (users.some((u) => u.email.toLowerCase() === email)) {
      throw new Error("Email already registered");
    }
    const id = Math.max(0, ...users.map((u) => u.id)) + 1;
    const password_hash = await sha256Hex(password);
    const user = { id, email, password_hash, read_only: false };
    users.push(user);
    writeJson(LS.users, users);
    mockSetSession(user);
    return { ok: true };
  },
  async login({ email, password }) {
    mockEnsureSeeded();
    email = (email || "").trim().toLowerCase();
    const users = readJson(LS.users, []);
    const password_hash = await sha256Hex(password);
    const user = users.find((u) => u.email.toLowerCase() === email);
    if (!user || user.password_hash !== password_hash) throw new Error("Invalid credentials");
    mockSetSession(user);
    return { ok: true };
  },
  async logout() {
    mockClearSession();
    return { ok: true };
  },
  async me() {
    const s = mockGetSession();
    if (!s) throw new Error("Not authenticated");
    return { id: s.id, email: s.email, read_only: Boolean(s.read_only) };
  },
  async listTransactions() {
    const me = await this.me();
    const txns = readJson(LS.txns, []).filter((t) => t.user_id === me.id);
    txns.sort((a, b) => (a.occurred_at < b.occurred_at ? 1 : -1));
    return txns;
  },
  async createTransaction(payload) {
    const me = await this.me();
    if (payload.amount_cents === 0) throw new Error("amount_cents cannot be 0");
    const txns = readJson(LS.txns, []);
    const id = Math.max(0, ...txns.map((t) => t.id)) + 1;
    const created_at = new Date().toISOString();
    const txn = {
      id,
      user_id: me.id,
      category_id: payload.category_id ?? null,
      amount_cents: Number(payload.amount_cents),
      description: payload.description || "",
      occurred_at: new Date(payload.occurred_at).toISOString(),
      created_at,
    };
    txns.push(txn);
    writeJson(LS.txns, txns);
    return txn;
  },
  async updateTransaction(id, payload) {
    const me = await this.me();
    const txns = readJson(LS.txns, []);
    const idx = txns.findIndex((t) => t.id === id && t.user_id === me.id);
    if (idx === -1) throw new Error("Transaction not found");
    if (payload.amount_cents === 0) throw new Error("amount_cents cannot be 0");

    const t = txns[idx];
    if (payload.amount_cents != null) t.amount_cents = Number(payload.amount_cents);
    if (payload.description != null) t.description = payload.description;
    if (payload.occurred_at != null) t.occurred_at = new Date(payload.occurred_at).toISOString();
    if (payload.category_id != null) t.category_id = payload.category_id;
    writeJson(LS.txns, txns);
    return t;
  },
  async deleteTransaction(id) {
    const me = await this.me();
    const txns = readJson(LS.txns, []);
    const next = txns.filter((t) => !(t.id === id && t.user_id === me.id));
    if (next.length === txns.length) throw new Error("Transaction not found");
    writeJson(LS.txns, next);
    return { ok: true };
  },
  async insightsSummary(fromYmd, toYmd) {
    const txnsAll = await this.listTransactions();
    const range = _normalizeInsightsRange(fromYmd, toYmd);
    const txns = txnsAll.filter((t) => _txnInLocalDateRange(t.occurred_at, range.from, range.to));

    const monthlyMap = new Map();
    let income = 0;
    let expense = 0;
    let net = 0;

    for (const t of txns) {
      const amt = Number(t.amount_cents);
      net += amt;
      if (amt > 0) income += amt;
      if (amt < 0) expense += -amt;
      const d = new Date(t.occurred_at);
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
      const cur = monthlyMap.get(key) || { income_cents: 0, expense_cents: 0, net_cents: 0 };
      if (amt > 0) cur.income_cents += amt;
      if (amt < 0) cur.expense_cents += -amt;
      cur.net_cents += amt;
      monthlyMap.set(key, cur);
    }

    const monthly = Array.from(monthlyMap.entries())
      .sort((a, b) => (a[0] < b[0] ? -1 : 1))
      .map(([month, v]) => ({ month, ...v }));

    const catMap = new Map();
    for (const t of txns) {
      const amt = Number(t.amount_cents);
      if (amt >= 0) continue;
      const key = "Uncategorized";
      catMap.set(key, (catMap.get(key) || 0) + -amt);
    }
    const expense_by_category = Array.from(catMap.entries()).map(([category, expense_cents]) => ({
      category,
      expense_cents,
    }));

    return {
      from: range.from,
      to: range.to,
      income_cents: income,
      expense_cents: expense,
      net_cents: net,
      monthly,
      expense_by_category,
    };
  },
};

async function register(body) {
  if (USE_MOCK) return mockApi.register(body);
  return apiFetch("/auth/register", { method: "POST", body: JSON.stringify(body) });
}
async function login(body) {
  if (USE_MOCK) return mockApi.login(body);
  return apiFetch("/auth/login", { method: "POST", body: JSON.stringify(body) });
}
async function logout() {
  if (USE_MOCK) return mockApi.logout();
  return apiFetch("/auth/logout", { method: "POST", body: "{}" });
}
async function me() {
  if (USE_MOCK) return mockApi.me();
  return apiFetch("/auth/me", { method: "GET" });
}

async function listTransactions(limit = 500) {
  if (USE_MOCK) return mockApi.listTransactions();
  const l = Math.min(Math.max(1, limit), 500);
  return apiFetch(`/transactions?limit=${l}&offset=0`, { method: "GET" });
}
async function createTransaction(body) {
  if (USE_MOCK) return mockApi.createTransaction(body);
  return apiFetch("/transactions", { method: "POST", body: JSON.stringify(body) });
}
async function updateTransaction(id, body) {
  if (USE_MOCK) return mockApi.updateTransaction(id, body);
  return apiFetch(`/transactions/${id}`, { method: "PUT", body: JSON.stringify(body) });
}
async function deleteTransaction(id) {
  if (USE_MOCK) return mockApi.deleteTransaction(id);
  return apiFetch(`/transactions/${id}`, { method: "DELETE" });
}
function _defaultInsightsRangeYmd() {
  // Default chart window: six months (Oct 2025–Mar 2026), matching seeded demo savings mix.
  return { from: "2025-10-01", to: "2026-03-31" };
}

function _normalizeInsightsRange(fromYmd, toYmd) {
  if (!fromYmd || !toYmd) return _defaultInsightsRangeYmd();
  if (fromYmd > toYmd) return { from: toYmd, to: fromYmd };
  return { from: fromYmd, to: toYmd };
}

function _txnInLocalDateRange(iso, fromYmd, toYmd) {
  const d = new Date(iso);
  if (!Number.isFinite(d.getTime())) return false;
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  const localYmd = `${y}-${m}-${day}`;
  return localYmd >= fromYmd && localYmd <= toYmd;
}

function getInsightsRangeFromForm() {
  const fromEl = document.getElementById("insightsFrom");
  const toEl = document.getElementById("insightsTo");
  let from = fromEl?.value?.trim();
  let to = toEl?.value?.trim();
  if (!from || !to) {
    const d = _defaultInsightsRangeYmd();
    from = d.from;
    to = d.to;
    if (fromEl) fromEl.value = from;
    if (toEl) toEl.value = to;
  }
  return _normalizeInsightsRange(from, to);
}

async function insightsSummary(fromYmd, toYmd) {
  const range = _normalizeInsightsRange(fromYmd, toYmd);
  const key = `${range.from}|${range.to}`;
  const cached = _cacheGet(chartsSummaryCache, key);
  if (cached) return cached;
  let data;
  if (USE_MOCK) return mockApi.insightsSummary(range.from, range.to);
  const q = new URLSearchParams({ from: range.from, to: range.to });
  data = await apiFetch(`/insights/summary?${q.toString()}`, { method: "GET" });
  _cacheSet(chartsSummaryCache, key, data);
  return data;
}

async function listTransactionsForCharts(fromYmd, toYmd) {
  const range = _normalizeInsightsRange(fromYmd, toYmd);
  const key = `${range.from}|${range.to}`;
  const cached = _cacheGet(chartsTxCache, key);
  if (cached) return cached;

  if (USE_MOCK) {
    const all = await mockApi.listTransactions();
    const filtered = all.filter((t) => _txnInLocalDateRange(t.occurred_at, range.from, range.to));
    _cacheSet(chartsTxCache, key, filtered);
    return filtered;
  }

  const acc = [];
  let offset = 0;
  const limit = 500;
  let pages = 0;
  const maxPages = 1000;
  while (pages < maxPages) {
    const batch = await apiFetch(`/transactions?limit=${limit}&offset=${offset}`, { method: "GET" });
    if (!batch.length) break;
    for (const t of batch) {
      if (_txnInLocalDateRange(t.occurred_at, range.from, range.to)) acc.push(t);
    }
    if (batch.length < limit) break;
    offset += limit;
    pages += 1;
  }
  _cacheSet(chartsTxCache, key, acc);
  return acc;
}

function renderTxnTable(txns) {
  const el = document.getElementById("txnTable");
  if (!el) return;
  let orderedTxns = Array.isArray(txns)
    ? [...txns].sort((a, b) => {
        const ta = Date.parse(a?.occurred_at || "") || 0;
        const tb = Date.parse(b?.occurred_at || "") || 0;
        if (tb !== ta) return tb - ta;
        return Number(b?.id || 0) - Number(a?.id || 0);
      })
    : [];

  el.innerHTML = "";
  const header = document.createElement("div");
  header.className = "tableRow header";
  header.innerHTML = `<div>When</div><div>Amount</div><div>Description</div><div class="actions">Actions</div>`;
  el.appendChild(header);

  if (orderedTxns.length === 0) {
    const empty = document.createElement("div");
    empty.className = "emptyState";
    empty.innerHTML = `
      <div class="emptyStateIcon" aria-hidden="true"></div>
      <div class="emptyStateTitle">No transactions yet</div>
      <div class="emptyStateText">Add your first transaction to start tracking your spending story.</div>
      <button type="button" class="button button--secondary" id="emptyAddTxnBtn">Add first transaction</button>
    `;
    el.appendChild(empty);
    document.getElementById("emptyAddTxnBtn")?.addEventListener("click", () => {
      document.getElementById("amountCents")?.focus();
    });
    return;
  }

  const esc = (s) =>
    String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

  for (const t of orderedTxns) {
    const row = document.createElement("div");
    row.className = "tableRow";
    row.dataset.txnId = String(t.id);
    if (lastSavedTxnId != null && Number(t.id) === Number(lastSavedTxnId)) {
      row.classList.add("tableRow--justSaved");
    }
    const when = formatRecentWhen(t.occurred_at);
    const amt = (Math.abs(Number(t.amount_cents || 0)) / 100).toFixed(2);
    const actionsHtml = sessionReadOnly
      ? '<span class="muted">—</span>'
      : `<button class="linkBtn" data-action="edit" data-id="${t.id}">Edit</button>
        <button class="linkBtn danger" data-action="del" data-id="${t.id}">Delete</button>`;
    row.innerHTML = `
      <div>${when}</div>
      <div>${Number(t.amount_cents) < 0 ? "-" : ""}$${amt}</div>
      <div>${esc(t.description)}</div>
      <div class="actions">${actionsHtml}</div>
    `;
    el.appendChild(row);
  }

  el.querySelectorAll("button[data-action]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = Number(btn.dataset.id);
      if (btn.dataset.action === "del") {
        try {
          await deleteTransaction(id);
          await refreshDashboard();
          setTxnStatus("");
          showToast("Transaction deleted.", { kind: "info", duration: 1800 });
        } catch (err) {
          setTxnStatus(err?.message || "Could not delete transaction", { error: true });
          showToast(err?.message || "Could not delete transaction", { kind: "error", duration: 3200 });
        }
      } else {
        const tx = orderedTxns.find((x) => x.id === id);
        if (!tx) return;
        document.getElementById("editingTxnId").value = String(tx.id);
        document.getElementById("amountCents").value = centsToDollarsInput(tx.amount_cents);
        const d = new Date(tx.occurred_at);
        d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
        document.getElementById("occurredAt").value = d.toISOString().slice(0, 16);
        document.getElementById("description").value = tx.description || "";
        document.getElementById("saveTxnBtn").textContent = "Save changes";
      }
    });
  });
}

async function refreshDashboard() {
  const meData = await me();
  sessionReadOnly = Boolean(meData.read_only);
  const meLabel = document.getElementById("meLabel");
  if (meLabel) meLabel.textContent = meData.email;

  const txns = await listTransactions();
  renderTxnTable(txns);
  applyReadOnlyUi();
  return txns;
}

async function refreshCharts() {
  await ensureChartsReady();
  const reqId = ++chartsRequestSeq;
  const { from, to } = getInsightsRangeFromForm();
  const summary = await insightsSummary(from, to);
  const txns = await listTransactionsForCharts(from, to);
  if (reqId !== chartsRequestSeq) return;
  const chartsEmpty = document.getElementById("chartsEmpty");
  if (chartsEmpty) chartsEmpty.hidden = txns.length > 0;
  if (typeof window.renderCharts === "function") {
    window.renderCharts(summary, txns);
  }
}

async function boot() {
  if (USE_MOCK) mockEnsureSeeded();

  try {
    const meData = await me();
    invalidateChartsCache();
    showView("dashboardView");
    const meLabel = document.getElementById("meLabel");
    if (meLabel) meLabel.textContent = meData.email;
    await refreshDashboard();
  } catch {
    showView("authLoginView");
  }
}

window.addEventListener("DOMContentLoaded", () => {
  const reloadShownAt = Date.now();
  showReloadOverlay();
  document.getElementById("occurredAt").value = nowIsoLocalInput();
  applyRememberedLoginEmail();

  document.getElementById("goRegisterBtn")?.addEventListener("click", () => {
    setStatus("");
    document.getElementById("registerForm")?.reset();
    showView("authRegisterView");
    document.getElementById("regEmail")?.focus();
  });
  document.getElementById("goLoginBtn")?.addEventListener("click", () => {
    setStatus("");
    showView("authLoginView");
    const pw = document.getElementById("password");
    if (pw) pw.value = "";
    applyRememberedLoginEmail();
    document.getElementById("email")?.focus();
  });

  document.getElementById("registerForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    setStatus("Creating account...");
    const email = document.getElementById("regEmail").value.trim();
    const password = document.getElementById("regPassword").value;
    try {
      await register({ email, password });
      setStatus("");
      showToast("Account created. Welcome!", { kind: "success", duration: 2200 });
      await boot();
    } catch (err) {
      setStatus(err.message || "Register failed", { error: true });
      showToast(err.message || "Register failed", { kind: "error", duration: 3200 });
    }
  });

  document.getElementById("loginForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    setStatus("Logging in...");
    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;
    try {
      await login({ email, password });
      if (document.getElementById("loginRememberMe")?.checked) {
        localStorage.setItem(LS_REMEMBER_EMAIL, email);
      } else {
        localStorage.removeItem(LS_REMEMBER_EMAIL);
      }
      setStatus("");
      showToast("Logged in.", { kind: "success", duration: 1700 });
      await boot();
    } catch (err) {
      setStatus(err.message || "Login failed", { error: true });
      showToast(err.message || "Login failed", { kind: "error", duration: 3200 });
    }
  });

  document.getElementById("logoutBtn").addEventListener("click", async () => {
    await logout();
    const pw = document.getElementById("password");
    if (pw) pw.value = "";
    applyRememberedLoginEmail();
    showView("authLoginView");
  });

  document.querySelectorAll(".tab[data-view]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const view = btn.dataset.view;
      showView(view + "View");
      if (view === "dashboard") await refreshDashboard();
      if (view === "charts") {
        await ensureChartsReady();
        getInsightsRangeFromForm();
        await refreshCharts();
      }
    });
  });

  const debouncedChartsRefresh = debounce(() => {
    refreshCharts().catch(() => {
      showToast("Could not load charts for that range.", { kind: "error", duration: 3000 });
    });
  }, 320);

  document.getElementById("insightsFrom")?.addEventListener("input", debouncedChartsRefresh);
  document.getElementById("insightsTo")?.addEventListener("input", debouncedChartsRefresh);
  document.getElementById("insightsApplyBtn")?.addEventListener("click", async () => {
    try {
      debouncedChartsRefresh();
      showToast("Charts updated.", { kind: "info", duration: 1600 });
    } catch (err) {
      console.error(err);
      showToast("Could not load charts for that range.", { kind: "error", duration: 3000 });
    }
  });

  document.getElementById("chartsEmptyResetBtn")?.addEventListener("click", async () => {
    const d = _defaultInsightsRangeYmd();
    const fromEl = document.getElementById("insightsFrom");
    const toEl = document.getElementById("insightsTo");
    if (fromEl) fromEl.value = d.from;
    if (toEl) toEl.value = d.to;
    try {
      await refreshCharts();
      showToast("Date range reset.", { kind: "success", duration: 1800 });
    } catch {
      showToast("Could not refresh charts.", { kind: "error", duration: 3000 });
    }
  });

  document.getElementById("txnForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    setTxnStatus("");
    const saveBtn = document.getElementById("saveTxnBtn");
    const originalBtnText = saveBtn?.textContent || "Add transaction";
    if (saveBtn) {
      saveBtn.disabled = true;
      saveBtn.textContent = "Saving...";
    }
    try {
      const idRaw = document.getElementById("editingTxnId").value;
      const occurredInput = document.getElementById("occurredAt").value;
      const occurredMs = Date.parse(occurredInput);
      if (!Number.isFinite(occurredMs)) {
        throw new Error("Please select a valid date/time");
      }

      let savedTxn = null;
      const payload = {
        occurred_at: new Date(occurredMs).toISOString(),
        amount_cents: dollarsInputToCents(document.getElementById("amountCents").value),
        description: document.getElementById("description").value,
        category_id: null,
      };

      if (idRaw) {
        savedTxn = await updateTransaction(Number(idRaw), payload);
      } else {
        savedTxn = await createTransaction(payload);
      }
      invalidateChartsCache();
      if (savedTxn) lastSavedTxnId = Number(savedTxn.id);
      const txns = await refreshDashboard();
      if (savedTxn) {
        const inFetched = txns.some((t) => t.id === savedTxn.id);
        setTxnStatus("");
        showToast(
          `${idRaw ? "Transaction updated." : "Transaction added."}${inFetched ? "" : " (synced to view)"}`,
          { kind: "success", duration: 2000 },
        );
        const savedRow = document.querySelector(`#txnTable .tableRow[data-txn-id="${savedTxn.id}"]`);
        savedRow?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      } else {
        setTxnStatus("");
        showToast(idRaw ? "Transaction updated." : "Transaction added.", { kind: "success", duration: 2000 });
      }
      document.getElementById("editingTxnId").value = "";
      document.getElementById("saveTxnBtn").textContent = "Add transaction";
      document.getElementById("txnForm").reset();
      document.getElementById("occurredAt").value = nowIsoLocalInput();
    } catch (err) {
      setTxnStatus(err?.message || "Could not save transaction", { error: true });
      showToast(err?.message || "Could not save transaction", { kind: "error", duration: 3200 });
      console.error(err);
    } finally {
      if (saveBtn) {
        saveBtn.disabled = false;
        if (!document.getElementById("editingTxnId").value) {
          saveBtn.textContent = "Add transaction";
        } else {
          saveBtn.textContent = originalBtnText;
        }
      }
    }
  });

  boot().finally(async () => {
    // Keep it short, but long enough to clearly see movement.
    const elapsed = Date.now() - reloadShownAt;
    const minVisibleMs = 950;
    if (elapsed < minVisibleMs) await waitMs(minVisibleMs - elapsed);
    await hideReloadOverlay();
  });

});


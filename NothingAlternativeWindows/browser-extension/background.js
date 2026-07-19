// Nothing Alternative — browser extension blocker
// Polls the backend directly with a Bearer token instead of localhost.

let blocking = false;
let blockedSites = [];

const API_BASE = "https://backend-production-b2cc.up.railway.app";

// ── Load token from storage ───────────────────────────────────────────────
async function getToken() {
  return new Promise(resolve => {
    chrome.storage.local.get(["na_token"], result => {
      resolve(result.na_token || null);
    });
  });
}

// ── Poll session status from the backend ─────────────────────────────────
async function checkSession() {
  const token = await getToken();

  // No token — fall back to localhost for offline/local mode
  if (!token) {
    try {
      const r = await fetch("http://localhost:59284/status", { cache: "no-store" });
      if (!r.ok) { blocking = false; return; }
      const d = await r.json();
      blocking     = d.active   ?? false;
      blockedSites = d.blocked  ?? [];
    } catch {
      blocking = false;
    }
    return;
  }

  // Signed-in mode — poll the real backend
  try {
    const r = await fetch(`${API_BASE}/sessions/status`, {
      cache: "no-store",
      headers: { "Authorization": `Bearer ${token}` }
    });
    if (!r.ok) { blocking = false; return; }
    const d = await r.json();
    blocking     = d.active   ?? false;
    blockedSites = d.blocked  ?? [];
  } catch {
    blocking = false;
  }
}

// Poll every 2 seconds
setInterval(checkSession, 2000);
checkSession();

// ── Helper: does this URL match a blocked site? ───────────────────────────
function isBlocked(urlStr) {
  if (!blocking || !urlStr) return false;
  let hostname;
  try { hostname = new URL(urlStr).hostname.toLowerCase(); }
  catch { return false; }
  return blockedSites.some(site => hostname === site || hostname.endsWith("." + site));
}

// ── Kill tab immediately on navigation ────────────────────────────────────
chrome.webNavigation.onBeforeNavigate.addListener((details) => {
  if (details.frameId !== 0) return;
  if (isBlocked(details.url)) {
    chrome.tabs.remove(details.tabId);
  }
});

// ── Catch redirects and pushState ─────────────────────────────────────────
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (!changeInfo.url && !tab.url) return;
  if (isBlocked(changeInfo.url || tab.url)) {
    chrome.tabs.remove(tabId);
  }
});
// Adds a small "Download with YTGrab" button on YouTube video pages,
// and handles sending links to the YTGrab app.
(() => {
  if (window.__ytgrab) return;
  window.__ytgrab = true;

  // ------------------------------------------------------------ links
  function videoLink(href) {
    try {
      const u = new URL(href, location.href);
      const host = u.hostname.replace(/^(www|m|music)\./, "");
      if (host === "youtu.be") return `https://www.youtube.com/watch?v=${u.pathname.slice(1)}`;
      if (host !== "youtube.com") return null;
      if (u.pathname === "/watch" && u.searchParams.get("v"))
        return `https://www.youtube.com/watch?v=${u.searchParams.get("v")}`;
      const m = u.pathname.match(/^\/(shorts|live)\/([\w-]{6,})/);
      if (m) return `https://www.youtube.com/${m[1]}/${m[2]}`;
    } catch {}
    return null;
  }

  // ------------------------------------------------------------ UI (shadow DOM keeps YouTube's styles out)
  const host = document.createElement("div");
  host.style.cssText = "position:fixed;left:20px;bottom:20px;z-index:2147483647;";
  const root = host.attachShadow({ mode: "closed" });
  root.innerHTML = `
    <style>
      :host { all: initial; }
      .wrap { display: flex; flex-direction: column; align-items: flex-start; gap: 8px;
              font: 500 13px/1.3 -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; }
      button {
        display: none; align-items: center; gap: 8px;
        height: 38px; padding: 0 16px 0 10px;
        border: 1px solid rgba(255,255,255,.14); border-radius: 999px;
        background: #16171B; color: #fff; font: inherit; font-weight: 600; cursor: pointer;
        box-shadow: 0 6px 20px rgba(0,0,0,.28);
        transition: transform .08s ease, opacity .2s ease;
      }
      button:hover { background: #24262c; }
      button:active { transform: scale(.97); }
      button:focus-visible { outline: 2px solid #6DCBFF; outline-offset: 2px; }
      .on button { display: inline-flex; }
      img { width: 20px; height: 20px; border-radius: 5px; }
      .toast {
        display: none; max-width: 300px; padding: 10px 14px; border-radius: 12px;
        background: #16171B; color: #fff; box-shadow: 0 6px 20px rgba(0,0,0,.28);
      }
      .toast.show { display: block; }
      .toast.bad { background: #8E2A24; }
    </style>
    <div class="wrap">
      <div class="toast" role="status" aria-live="polite"></div>
      <button type="button" title="Open this video in the YTGrab app">
        <img alt=""> Download with YTGrab
      </button>
    </div>`;
  const wrap = root.querySelector(".wrap");
  const btn = root.querySelector("button");
  const toastEl = root.querySelector(".toast");
  root.querySelector("img").src = chrome.runtime.getURL("icons/32.png");
  (document.body || document.documentElement).appendChild(host);

  let toastTimer;
  function toast(text, { bad = false, stay = false } = {}) {
    clearTimeout(toastTimer);
    toastEl.textContent = text;
    toastEl.classList.toggle("bad", bad);
    toastEl.classList.add("show");
    if (!stay) toastTimer = setTimeout(() => toastEl.classList.remove("show"), 3500);
  }

  function refresh() {
    wrap.classList.toggle("on", !!videoLink(location.href));
  }
  document.addEventListener("yt-navigate-finish", refresh);
  setInterval(refresh, 1000); // YouTube changes pages without reloading
  refresh();

  // ------------------------------------------------------------ hand-off
  const send = (url) => new Promise((resolve) =>
    chrome.runtime.sendMessage({ type: "send", url }, (r) => resolve(!!(r && r.ok))));

  let busy = false;
  async function handoff(rawUrl) {
    const url = videoLink(rawUrl || location.href);
    if (!url) { toast("Open a YouTube video first, then click YTGrab."); return; }
    if (busy) return;
    busy = true;
    try {
      if (await send(url)) { toast("Sent to YTGrab ✓"); return; }

      // App isn't running: ask Chrome to open it, then keep trying for 20 seconds.
      toast("Opening YTGrab…", { stay: true });
      location.href = "ytgrab://open?url=" + encodeURIComponent(url);
      for (let i = 0; i < 20; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        if (await send(url)) { toast("Sent to YTGrab ✓"); return; }
      }
      toast("Couldn't reach YTGrab. Make sure the app is installed and open, then try again.", { bad: true });
    } finally {
      busy = false;
    }
  }

  btn.addEventListener("click", () => handoff(location.href));
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg && msg.type === "handoff") handoff(msg.url);
  });
})();

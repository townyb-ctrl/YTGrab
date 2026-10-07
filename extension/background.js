// Talks to the YTGrab app, which listens on this computer only.
const APP = "http://127.0.0.1:47681";
const YT_PAGES = ["https://www.youtube.com/*", "https://m.youtube.com/*", "https://music.youtube.com/*"];

async function sendToApp(url) {
  try {
    const res = await fetch(APP + "/open", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    return res.ok;
  } catch {
    return false; // app not running
  }
}

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (msg && msg.type === "send") {
    sendToApp(msg.url).then((ok) => reply({ ok }));
    return true; // reply asynchronously
  }
});

// Toolbar button: send the video in the current tab.
chrome.action.onClicked.addListener(async (tab) => {
  try {
    await chrome.tabs.sendMessage(tab.id, { type: "handoff", url: tab.url });
  } catch {
    // Not a YouTube tab, so there's nothing to send.
    chrome.action.setBadgeBackgroundColor({ color: "#5C606B", tabId: tab.id });
    chrome.action.setBadgeText({ text: "?", tabId: tab.id });
    chrome.action.setTitle({ title: "Open a YouTube video, then click YTGrab", tabId: tab.id });
    setTimeout(() => chrome.action.setBadgeText({ text: "", tabId: tab.id }), 2500);
  }
});

// Right-click menu on YouTube: a video link, or the page you're on.
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "ytgrab",
    title: "Download with YTGrab",
    contexts: ["link", "page", "video"],
    documentUrlPatterns: YT_PAGES,
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  const url = info.linkUrl || info.pageUrl;
  if (tab && tab.id != null) chrome.tabs.sendMessage(tab.id, { type: "handoff", url }).catch(() => {});
});

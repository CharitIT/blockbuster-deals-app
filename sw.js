// App shell: cache-first. deals.json: network-first so the latest offers win,
// with the cached copy as an offline fallback.
const CACHE = "bb-deals-v3";
const SHELL = ["./", "./index.html", "./manifest.webmanifest",
  "./icons/icon-192.png", "./icons/icon-512.png", "./icons/apple-touch-icon.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (url.origin !== location.origin) return;
  if (url.pathname.endsWith("/deals.json")) {
    e.respondWith(
      fetch(e.request, { cache: "no-store" })
        .then(res => { const copy = res.clone(); caches.open(CACHE).then(c => c.put("./deals.json", copy)); return res; })
        .catch(() => caches.match("./deals.json"))
    );
    return;
  }
  e.respondWith(caches.match(e.request).then(hit => hit || fetch(e.request)));
});

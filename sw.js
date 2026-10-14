// Pages (index.html) and deals.json: network-first, so the newest version always wins when online.
// The saved copy is only used when offline. Icons and the manifest are cache-first.
const CACHE = "bb-deals-v13";
const SHELL = ["./", "./index.html", "./manifest.webmanifest",
  "./icons/icon-192.png", "./icons/icon-512.png", "./icons/apple-touch-icon.png"];

self.addEventListener("install", e => {
  // cache: "reload" skips the browser's HTTP cache, so we never store a stale copy.
  e.waitUntil(caches.open(CACHE)
    .then(c => c.addAll(SHELL.map(u => new Request(u, { cache: "reload" }))))
    .then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

function networkFirst(request, key) {
  return fetch(request, { cache: "no-store" })
    .then(res => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(key, copy)); }
      return res;
    })
    .catch(() => caches.match(key).then(hit => hit || caches.match("./")));
}

self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;
  const url = new URL(e.request.url);
  if (url.origin !== location.origin) return;
  if (e.request.mode === "navigate" || url.pathname.endsWith("/") || url.pathname.endsWith("/index.html")) {
    e.respondWith(networkFirst(e.request, "./"));
    return;
  }
  if (url.pathname.endsWith("/deals.json")) {
    e.respondWith(networkFirst(e.request, "./deals.json"));
    return;
  }
  e.respondWith(caches.match(e.request).then(hit => hit || fetch(e.request)));
});

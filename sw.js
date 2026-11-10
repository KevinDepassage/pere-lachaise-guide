/* Service worker : garde la page, les polices et les photos déjà vues pour un usage hors connexion.
   Page : réseau d'abord (pour recevoir les mises à jour), cache en secours.
   Polices et photos : cache d'abord. Les API (Overpass, Wikidata) ne sont pas mises en cache ici :
   la page conserve elle-même la base complète dans le stockage local. */
const CACHE = "plg-v1";
const CORE = ["./", "./index.html", "./manifest.webmanifest"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(CORE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  if (req.mode === "navigate" || (url.origin === location.origin && /\/(index\.html)?$/.test(url.pathname))) {
    e.respondWith(
      fetch(req).then(r => { const copy = r.clone(); caches.open(CACHE).then(c => c.put("./index.html", copy)); return r; })
        .catch(() => caches.match("./index.html"))
    );
    return;
  }

  const cacheFirst = /fonts\.(googleapis|gstatic)\.com$/.test(url.hostname) ||
    (url.hostname === "commons.wikimedia.org" && url.pathname.includes("Special:FilePath")) ||
    url.hostname === "upload.wikimedia.org" ||
    url.origin === location.origin;
  if (!cacheFirst) return;

  e.respondWith(
    caches.match(req).then(hit => hit || fetch(req).then(r => {
      if (r.ok || r.type === "opaque") { const copy = r.clone(); caches.open(CACHE).then(c => c.put(req, copy)); }
      return r;
    }))
  );
});

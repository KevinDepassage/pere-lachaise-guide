/* Service worker : garde la page, les données, les polices et les photos déjà vues pour un usage hors connexion.
   Page et fichiers de données du site : réseau d'abord (pour recevoir les mises à jour), cache en secours.
   Polices et photos : cache d'abord. Les API (Overpass, Wikidata) ne sont pas mises en cache ici :
   la page conserve elle-même la base complète dans le stockage local. */
const CACHE = "plg-v2";
const CORE = ["./", "./index.html", "./manifest.webmanifest", "./tombes-pl.json", "./osm-pl.json"];

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

  if (req.mode === "navigate") {
    e.respondWith(
      fetch(req).then(r => { const copy = r.clone(); caches.open(CACHE).then(c => c.put("./index.html", copy)); return r; })
        .catch(() => caches.match("./index.html"))
    );
    return;
  }
  // Fichiers du site (données comprises) : réseau d'abord pour recevoir les mises à jour, cache en secours
  if (url.origin === location.origin) {
    e.respondWith(
      fetch(req).then(r => { if (r.ok) { const copy = r.clone(); caches.open(CACHE).then(c => c.put(req, copy)); } return r; })
        .catch(() => caches.match(req, {ignoreSearch: true}))
    );
    return;
  }

  const cacheFirst = /fonts\.(googleapis|gstatic)\.com$/.test(url.hostname) ||
    (url.hostname === "commons.wikimedia.org" && url.pathname.includes("Special:FilePath")) ||
    url.hostname === "upload.wikimedia.org";
  if (!cacheFirst) return;

  e.respondWith(
    caches.match(req).then(hit => hit || fetch(req).then(r => {
      if (r.ok || r.type === "opaque") { const copy = r.clone(); caches.open(CACHE).then(c => c.put(req, copy)); }
      return r;
    }))
  );
});

/* PeatGuard background script: makes the app installable and lets it open
   with the last downloaded data when there is no signal.
   Change VERSION to force every phone to drop its old copy. */
var VERSION = 'pg-v3';
var SHELL = ['./', 'index.html', 'style.css', 'app.js', 'config.js', 'leaflet-heat.js', 'land.json', 'manifest.json',
  'icons/icon-192.png', 'icons/apple-touch-icon.png',
  'data/today.json', 'data/metrics.json', 'data/air.json', 'data/replay.json', 'data/impact.json',
  'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css'];
var CDN = ['cdnjs.cloudflare.com', 'fonts.googleapis.com', 'fonts.gstatic.com'];

self.addEventListener('install', function (e) {
  e.waitUntil(caches.open(VERSION).then(function (c) {
    return Promise.all(SHELL.map(function (u) { return c.add(u).catch(function () {}); }));
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener('activate', function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k !== VERSION; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener('fetch', function (e) {
  var req = e.request;
  if (req.method !== 'GET') return;
  var url = new URL(req.url);

  // The app itself and its daily data: always try the network first so
  // people see today's prediction; fall back to the saved copy offline.
  if (url.origin === self.location.origin) {
    e.respondWith(fetch(req).then(function (res) {
      if (res.ok) { var copy = res.clone(); caches.open(VERSION).then(function (c) { c.put(req, copy); }); }
      return res;
    }).catch(function () {
      return caches.match(req, { ignoreSearch: true }).then(function (hit) {
        return hit || (req.mode === 'navigate' ? caches.match('index.html') : Response.error());
      });
    }));
    return;
  }

  // Map library and fonts: use the saved copy, refresh it in the background.
  if (CDN.indexOf(url.hostname) >= 0) {
    e.respondWith(caches.open(VERSION).then(function (c) {
      return c.match(req).then(function (hit) {
        var net = fetch(req).then(function (res) { if (res.ok || res.type === 'opaque') c.put(req, res.clone()); return res; }).catch(function () { return hit; });
        return hit || net;
      });
    }));
  }
  // Everything else (map tiles, live air quality) goes straight to the network.
});

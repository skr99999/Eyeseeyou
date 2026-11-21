const cacheName = new URL("./", self.location).pathname + "eyeseeyou-mobile-v4";
const files = [
  "./index.html", "./style.css?v=3", "./app.js", "./replay-data.js", "./guide.js",
  "./guide-camera.css", "./vision.js",
  "./manifest.webmanifest", "./icon-192.png", "./icon-512.png",
];

self.addEventListener("install", event => {
  event.waitUntil(caches.open(cacheName).then(cache => cache.addAll(files)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", event => {
  const prefix = new URL("./", self.location).pathname + "eyeseeyou-mobile-";
  event.waitUntil(caches.keys().then(keys => Promise.all(keys
    .filter(key => key.startsWith(prefix) && key !== cacheName)
    .map(key => caches.delete(key))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", event => {
  if (event.request.method !== "GET" || !event.request.url.startsWith(self.registration.scope)) return;
  event.respondWith(caches.open(cacheName).then(async cache => {
    if (event.request.mode === "navigate") {
      return (await cache.match("./index.html")) || fetch(event.request);
    }
    const cached = await cache.match(event.request);
    if (cached) return cached;
    const response = await fetch(event.request);
    if (response.ok && event.request.url.startsWith(new URL("./vision-assets/", self.registration.scope).href)) {
      await cache.put(event.request, response.clone()).catch(() => {});
    }
    return response;
  }));
});

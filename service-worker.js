
const CACHE_NAME = "smart-inventory-v1";

const FILES_TO_CACHE = [
    "/",
    "/static/style.css",
    "/static/script.js"
];

// Install and cache important files
self.addEventListener("install", event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => cache.addAll(FILES_TO_CACHE))
    );
});

// Serve cached files when offline
self.addEventListener("fetch", event => {
    event.respondWith(
        caches.match(event.request)
            .then(response => {
                return response || fetch(event.request);
            })
    );
});

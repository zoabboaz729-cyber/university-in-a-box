const CACHE_NAME = 'uib-reading-room-v1';
const ASSET_URLS = [
  '/static/style.css',
  '/static/htmx.min.js',
  '/static/manifest.json',
  '/static/icons/icon-192.svg',
  '/static/icons/icon-512.svg'
];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSET_URLS)));
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
    ))
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  if (event.request.url.startsWith('chrome-extension://')) return;

  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request).then((response) => {
        if (!response || response.status !== 200 || response.type !== 'basic') {
          return response;
        }
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        return response;
      }).catch(() => {
        if (event.request.mode === 'navigate') {
          return caches.match('/static/style.css');
        }
        return caches.match(event.request);
      });
    })
  );
});

self.addEventListener('push', (event) => {
  if (!event.data) {
    return;
  }

  let payload;
  try {
    payload = event.data.json();
  } catch (error) {
    payload = { title: 'University in a Box', body: 'A new update is ready.' };
  }

  const options = {
    body: payload.body || 'A new update is ready.',
    icon: payload.icon || '/static/icons/icon-192.svg',
    badge: payload.badge || '/static/icons/icon-192.svg',
    data: payload.url || '/',
    tag: payload.tag || 'uib-notification'
  };

  event.waitUntil(self.registration.showNotification(payload.title || 'University in a Box', options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  const url = event.notification.data || '/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if (client.url.includes(url) || client.visibilityState === 'visible') {
          client.focus();
          return;
        }
      }
      clients.openWindow(url);
    })
  );
});

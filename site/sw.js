/* 版本答案 service worker：介面檔案先用快取（秒開），資料一律先抓網路、失敗才用上次的資料。 */
const BUILD = '__BUILD__';
const SHELL = `meta-shell-${BUILD}`;
const DATA = 'meta-data';
const SHELL_FILES = ['./', 'index.html', 'styles.css', 'app.js', 'updates.js', 'manifest.webmanifest', 'icons/icon-192.png', 'icons/apple-touch-icon.png'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(SHELL_FILES)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k.startsWith('meta-shell-') && k !== SHELL).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET') return;
  if (url.origin === location.origin && url.pathname.includes('/data/')) {
    const key = url.origin + url.pathname;
    e.respondWith(
      fetch(e.request)
        .then((res) => {
          // 一定要先複製再回傳：等快取打開時，原本的回應可能已經被頁面讀完，再複製就會失敗
          if (res.ok) { const copy = res.clone(); caches.open(DATA).then((c) => c.put(key, copy)); }
          return res;
        })
        .catch(() => caches.open(DATA).then((c) => c.match(key)).then((r) => r || Response.error())),
    );
    return;
  }
  if (url.origin === location.origin) {
    e.respondWith(
      caches.match(e.request, { ignoreSearch: true }).then((hit) => {
        const net = fetch(e.request).then((res) => {
          if (res.ok) { const copy = res.clone(); caches.open(SHELL).then((c) => c.put(e.request, copy)); }
          return res;
        }).catch(() => hit);
        return hit || net;
      }),
    );
    return;
  }
  if (url.hostname.endsWith('gstatic.com') || url.hostname.endsWith('googleapis.com')) {
    e.respondWith(
      caches.open('meta-fonts').then((c) => c.match(e.request).then((hit) => hit || fetch(e.request).then((res) => { c.put(e.request, res.clone()); return res; }))),
    );
  }
});

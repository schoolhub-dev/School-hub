/*
 * Школьный Хаб — Service Worker (PWA)
 * Стратегия:
 *  - навигация: network-first (свежая версия, при офлайне — кэш);
 *  - остальные запросы: cache-first с подстановкой из кэша при офлайне.
 * CDN (Tailwind/Firebase) не кэшируются, чтобы не хранить сторонние ресурсы.
 */

// При обновлении приложения увеличьте версию, чтобы вытеснить старый кэш
const CACHE = 'school-hub-v12';

// Файлы для офлайн-запуска приложения
const PRECACHE = [
  './',
  './index.html',
  './manifest.json',
  './firebase-config.js',
  './auth.js?v=9',
  './moderation.js?v=9',
  './icon-192.png',
  './icon-512.png',
];

// Установка: заполняем кэш основными файлами
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting())
  );
});

// Активация: удаляем старые версии кэша
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

// Обработка запросов
self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  // Навигация по приложению: сначала сеть, при ошибке — кэшированная копия
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put('./index.html', copy));
          return response;
        })
        .catch(() => caches.match('./index.html'))
    );
    return;
  }

  // Статические файлы: сначала кэш, потом сеть
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request).then((response) => {
        if (response && response.status === 200 && response.type === 'basic') {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(request, copy));
        }
        return response;
      });
    })
  );
});
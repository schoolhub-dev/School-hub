/*
 * Школьный Хаб — Service Worker (PWA)
 * Стратегия:
 *  - навигация: network-first (свежая версия, при офлайне — кэш);
 *  - остальные запросы: cache-first с подстановкой из кэша при офлайне.
 * CDN (Tailwind/Firebase) не кэшируются, чтобы не хранить сторонние ресурсы.
 */

// При обновлении приложения увеличьте версию, чтобы вытеснить старый кэш
const CACHE = 'school-hub-v16';

// Файлы для офлайн-запуска приложения.
// Список стикеров кладём обязательно: без него кнопка «Стикеры» после
// переустановки покажет встроенный список вместо вашего.
// Сами картинки (13 webp ≈ 66 КБ) тоже кладём — они крошечные.
// GIF-стикеры по 4–6 МБ в PRECACHE НЕ идут: это 27 МБ на каждом устройстве
// при установке. Они кэшируются по требованию, когда их реально открыли.
const PRECACHE = [
  './',
  './index.html',
  './manifest.json',
  './firebase-config.js?v=5',
  './auth.js?v=9',
  './moderation.js?v=9',
  './icon-192.png',
  './icon-512.png',
  './stickers/manifest.json',
  './stickers/1.webp',
  './stickers/2.webp',
  './stickers/3.webp',
  './stickers/4.webp',
  './stickers/5.webp',
  './stickers/6.webp',
  './stickers/7.webp',
  './stickers/8.webp',
  './stickers/9.webp',
  './stickers/10.webp',
  './stickers/11.webp',
  './stickers/12.webp',
  './stickers/24.webp',
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

  // Статические файлы (включая stickers/*): сначала кэш, потом сеть.
  // GIF-стикеры весят по 4–6 МБ, поэтому в PRECACHE их нет — они попадают
  // в кэш сами, когда их открыли, и дальше отдаются оттуда.
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
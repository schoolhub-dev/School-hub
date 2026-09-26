// Firebase JS SDK v9+ (compat), measurementId is optional.
// Конфиг Firebase проекта school-hub-9d8aa.
const firebaseConfig = {
  apiKey: "AIzaSyAWWpIGsIDNE1lR7OeW9Mx3e7Af7tMmcXo",
  authDomain: "school-hub-9d8aa.firebaseapp.com",
  databaseURL: "https://school-hub-9d8aa-default-rtdb.firebaseio.com",
  projectId: "school-hub-9d8aa",
  storageBucket: "school-hub-9d8aa.firebasestorage.app",
  messagingSenderId: "402021407291",
  appId: "1:402021407291:web:156075f33362657d77da1e",
  measurementId: "G-M3RLSLR9QV"
};

// ИИ-модерация сообщений — через прокси на Deno Deploy (обход CORS).
// Ключ xKiro хранится ТОЛЬКО на прокси (env.XKIRO_API_KEY), клиент его не видит.
// Запросы идут на workerUrl + '/moderate'.
const aiConfig = {
  workerUrl: "https://broad-kestrel-9916.schoolhub-dev.deno.net",
  model: "qwen/qwen3.6-plus:free"
};
window.AI_CONFIG = aiConfig;

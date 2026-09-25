// For Firebase JS SDK v9+ (compat), measurementId is optional.
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

// ИИ-модерация сообщений (xKiro, OpenAI-совместимый роутер).
// ВАЖНО: ключ лежит в клиентском JS и виден любому, кто откроет сайт.
// Для продакшена модерацию лучше выносить на сервер.
const aiConfig = {
  base: "https://api.xkiro.com/v1",
  key: "sk-xt-e46331fadadcd6a0da7d222c6c1d510ff6d12442a6ea59c2",
  model: "deepseek/deepseek-chat"
};
window.AI_CONFIG = aiConfig;
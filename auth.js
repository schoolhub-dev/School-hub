// auth.js — анонимная авторизация Firebase и профиль пользователя (users/{uid}).
// Требует подключённых firebase-app-compat.js, firebase-auth-compat.js,
// firebase-database-compat.js и выполненного initFirebase() (глобальные app/db).
//
// Глобальное состояние: window.HubAuth.{ uid, ready, profile, error }
(function () {
  'use strict';

  const Auth = {

    uid: null,     // UID текущего анонимного пользователя
    ready: false,  // true после восстановления сессии / входа
    profile: null, // кэш профиля users/{uid}
    error: null,   // текст ошибки авторизации (если не удалось войти)

    _onReadyCb: null,
    _started: false,

    // Включить анонимную авторизацию и дождаться готовности.
    // done() вызывается один раз, когда сессия восстановлена или создана.
    start(done) {
      this._onReadyCb = done || null;
      if (this._started) return;
      this._started = true;
      // onAuthStateChanged: если пользователь уже входил ранее,
      // Firebase сам восстановит сессию.
      firebase.auth().onAuthStateChanged((user) => this._onUser(user));
    },

    // Обработка смены состояния сессии
    _onUser(user) {
      if (user) {
        this.uid = user.uid;
        this.error = null;
        this.ready = true;
        this._settle();
        return;
      }
      // Нет активной сессии — входим анонимно.
      // _settle() вызываем ТОЛЬКО после результата входа (then/catch),
      // иначе done() сработает, пока uid ещё не установлен.
      firebase.auth().signInAnonymously()
        .then((cred) => {
          this.uid = cred.user.uid;
          this.error = null;
          this.ready = true;
        })
        .catch((err) => {
          // Авторизация не включена или недоступна — приложение всё равно
          // сможет читать, но писать (чат и т.п.) не будет.
          this.uid = null;
          this.error = (err && err.message) ? err.message : String(err);
          this.ready = true;
        })
        .then(() => this._settle());
    },

    _settle() {
      // Сообщаем всему приложению, что состояние авторизации известно
      document.dispatchEvent(new CustomEvent('auth-ready', {
        detail: { uid: this.uid, error: this.error },
      }));
      const cb = this._onReadyCb;
      if (cb) { this._onReadyCb = null; cb(); }
    },

    // Создать/синхронизировать профиль users/{uid}.
    // nick/class/deviceId/avatar/bio задаёт сам пользователь, createdAt — только при первом входе.
    // banned/mutedUntil здесь НЕ трогаем (старые поля; новых банов нет — они в bannedUsers/).
    // Пустая строка — реальное значение (так чистится bio/avatar);
    // null/undefined — «поле не трогать».
    // Возвращает Promise с профилем.
    syncProfile(patch) {
      const p = patch || {};
      if (!this.uid) return Promise.resolve(this.profile || {});
      const ref = db.ref('/users/' + this.uid);
      // Пишем каждый ребёнок отдельным запросом — это совместимо с правилами,
      // где пользователь может менять только свои поля (и createdAt 1 раз).
      const syncField = (name, value) => {
        if (value == null) return Promise.resolve();
        const v = String(value);
        return ref.child(name).once('value').then((s) => {
          if (s.val() !== v) return ref.child(name).set(v);
        });
      };
      const jobs = [
        syncField('nick', p.nick),
        syncField('class', p.class),
        syncField('deviceId', p.deviceId),
        syncField('avatar', p.avatar),
        syncField('bio', p.bio),
        ref.child('createdAt').once('value').then((s) => {
          if (!s.exists()) return ref.child('createdAt').set(Date.now());
        }),
      ];
      return Promise.all(jobs)
        .then(() => ref.once('value'))
        .then((s) => { this.profile = s.val() || {}; return this.profile; });
    },

    // Свежая копия профиля (например, users/{uid}/banned) из БД
    fetchProfile(uid) {
      const u = uid || this.uid;
      if (!u) return Promise.resolve(null);
      return db.ref('/users/' + u).once('value').then((s) => s.val() || {});
    },
  };

  window.HubAuth = Auth;
})();
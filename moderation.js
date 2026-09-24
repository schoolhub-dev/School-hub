// moderation.js — баны по UID через Firebase Auth.
// Ветка bannedUsers/{uid}: { until, reason, bannedBy, bannedAt }
//   until — таймстамп (мс) до которого действует бан; 0 или отсутствует = бессрочный.
//   ВАЖНО: Firebase `now` в правилах возвращает миллисекунды,
//   поэтому until храним в миллисекундах (не в секундах).
// Зависит от: firebase database (db), window.HubAuth (auth.js).
(function () {
  'use strict';

  const now = () => Date.now();

  const Moderation = {

    // Текущий uid или null, если авторизации нет
    uid() {
      return (window.HubAuth && window.HubAuth.uid) || null;
    },

    // Запись о бане пользователя (или null, если бана нет)
    getBan(uid) {
      if (!uid) return Promise.resolve(null);
      return db.ref('/bannedUsers/' + uid).once('value')
        .then((s) => s.val() || null);
    },

    // Активен ли бан сейчас: бессрочный (until 0/нет) — да; иначе until > now
    isActive(ban) {
      if (!ban) return false;
      const until = Number(ban.until);
      if (!Number.isFinite(until) || until === 0) return true; // бессрочный
      return until > now();
    },

    // Проверка перед отправкой сообщения: done(errText | null)
    checkCanSend(done) {
      const uid = this.uid();
      if (!uid) { done('Авторизация ещё не готова, попробуйте снова'); return; }
      this.getBan(uid).then((ban) => {
        if (!ban || !this.isActive(ban)) {
          // Бан есть, но истёк — разрешаем и чистим запись
          if (ban) db.ref('/bannedUsers/' + uid).remove().catch(() => {});
          done(null);
          return;
        }
        const reason = ban.reason ? ' Причина: ' + ban.reason : '';
        if (Number(ban.until) === 0 || !ban.until) {
          done('Ты забанен навсегда.' + reason);
        } else {
          done('Ты забанен до ' + fmtDateTime(Number(ban.until)) + '.' + reason);
        }
      }).catch((err) => done('Ошибка проверки: ' + ((err && err.message) ? err.message : err)));
    },

    // ---- Админ-действия (пишут в bannedUsers; по правилам — только UID из /admins) ----

    _writeBan(uid, data) {
      const rec = {
        until: Math.floor(Number(data.until) || 0),
        reason: String(data.reason || '').slice(0, 200),
        bannedBy: 'admin',
        bannedAt: now(),
      };
      return db.ref('/bannedUsers/' + uid).set(rec);
    },

    muteHours(uid, hours, reason) {   // мут на N часов
      return this._writeBan(uid, { until: now() + hours * 3600000, reason: reason || 'мут администратором' });
    },

    banForever(uid, reason) {         // бессрочный бан (until: 0)
      return this._writeBan(uid, { until: 0, reason: reason || 'бессрочный бан' });
    },

    unban(uid) {                      // полное снятие бана (удаление записи)
      return db.ref('/bannedUsers/' + uid).remove();
    },

    // Читаемый статус пользователя для списков модерации
    statusOf(ban) {
      if (!ban) return { label: 'активен', cls: 'text-emerald-400' };
      const until = Number(ban.until);
      if (!Number.isFinite(until) || until === 0) return { label: 'забанен навсегда', cls: 'text-rose-400' };
      if (until > now()) return { label: 'забанен до ' + fmtDateTime(until), cls: 'text-amber-400' };
      return { label: 'бан истёк', cls: 'text-slate-500' };
    },
  };

  window.HubModeration = Moderation;

  // Локальная помощь (модуль грузится раньше основного скрипта)
  function fmtDateTime(ts) {
    try { if (typeof fmtDate === 'function') return fmtDate(ts); } catch (e) { /* основная функция ещё не определена */ }
    const d = new Date(ts);
    const p = (x) => String(x).padStart(2, '0');
    return d.getDate() + '.' + p(d.getMonth() + 1) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
  }
})();
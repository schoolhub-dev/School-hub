// moderation.js — проверки бан/мут и админ-инструменты модерации по UID.
// Зависит от: firebase database (db), window.HubAuth (auth.js).
// Глобальное состояние: window.HubModeration.
(function () {
  'use strict';

  const Moderation = {

    // Проверка перед отправкой сообщения в чат.
    // done(errText, profile) — errText !== null => отправку запрещаем.
    checkCanSend(done) {
      const uid = window.HubAuth && window.HubAuth.uid;
      if (!uid) { done('Авторизация ещё не готова, попробуйте ещё раз'); return; }
      window.HubAuth.fetchProfile(uid).then((prof) => {
        if (!prof) { done('Профиль не найден'); return; }
        if (prof.banned) { done('Вы заблокированы администратором'); return; }
        if (prof.mutedUntil && Number(prof.mutedUntil) > Date.now()) {
          done('Вы в муте до ' + fmtDateTime(Number(prof.mutedUntil)));
          return;
        }
        done(null, prof);
      }).catch((err) => {
        done('Ошибка проверки: ' + ((err && err.message) ? err.message : err));
      });
    },

    // ---- Админ-действия (записи в users/{uid}, права по правилам: только admins) ----

    muteHours(uid, hours) {      // мут на N часов
      return db.ref('/users/' + uid + '/mutedUntil').set(Date.now() + hours * 3600000);
    },

    banForever(uid) {            // бан навсегда
      return db.ref('/users/' + uid + '/banned').set(true);
    },

    unban(uid) {                 // снять мут и бан
      return Promise.all([
        db.ref('/users/' + uid + '/mutedUntil').set(0),
        db.ref('/users/' + uid + '/banned').set(false),
      ]);
    },

    // Читаемый статус пользователя для списка модерации
    statusOf(prof) {
      if (!prof) return { label: '—', cls: '' };
      if (prof.banned) return { label: 'забанен', cls: 'text-rose-400' };
      const m = Number(prof.mutedUntil) || 0;
      if (m > Date.now()) return { label: 'замьючен до ' + fmtDateTime(m), cls: 'text-amber-400' };
      if (m === 0 && 'mutedUntil' in prof) return { label: 'не замьючен', cls: 'text-slate-500' };
      return { label: 'активен', cls: 'text-emerald-400' };
    },
  };

  window.HubModeration = Moderation;

  // Локальная помощь (модуль грузится раньше основного скрипта, fmtDate появится позже)
  function fmtDateTime(ts) {
    try {
      if (typeof fmtDate === 'function') return fmtDate(ts);
    } catch (e) { /* основная функция ещё не определена */ }
    const d = new Date(ts);
    const p = (x) => String(x).padStart(2, '0');
    return d.getDate() + '.' + p(d.getMonth() + 1) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
  }
})();
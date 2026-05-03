/**
 * Клиентские события Mini App: дублирование в console и fire-and-forget на POST /api/events.
 * Ошибки сети игнорируются, UI не ломается. Payload — только строки и целые (см. backend EventRequest).
 *
 * В каждый запрос подмешиваются сведения из Telegram.WebApp.initDataUnsafe.user (если есть).
 * Это данные из клиента без проверки подписи initData на сервере — для ответственной аналитики позже
 * можно добавить проверку initData через BOT_TOKEN на backend.
 */
(function () {
  "use strict";

  const ENDPOINT = "/api/events";
  const MAX_KEYS = 32;
  const MAX_KEY_LEN = 64;
  const MAX_STR_VAL = 512;
  const MAX_INT_ABS = 2147483647;

  /**
   * Поля пользователя Telegram из WebApp SDK (только внутри Telegram).
   * @returns {Record<string, string | number>}
   */
  function getTelegramUserPayload() {
    const u = window.Telegram?.WebApp?.initDataUnsafe?.user;
    if (!u || typeof u !== "object") return {};
    /** @type {Record<string, string | number>} */
    const out = {};
    if (typeof u.id === "number" && Number.isFinite(u.id)) {
      const id = Math.floor(u.id);
      if (Math.abs(id) <= MAX_INT_ABS) out.tg_user_id = id;
    }
    if (typeof u.username === "string" && u.username.trim()) {
      out.tg_username = u.username.trim().slice(0, 128);
    }
    if (typeof u.first_name === "string" && u.first_name.trim()) {
      out.tg_first_name = u.first_name.trim().slice(0, 128);
    }
    if (typeof u.last_name === "string" && u.last_name.trim()) {
      out.tg_last_name = u.last_name.trim().slice(0, 128);
    }
    if (typeof u.language_code === "string" && u.language_code.trim()) {
      out.tg_language_code = u.language_code.trim().slice(0, 16);
    }
    return out;
  }

  /**
   * Нормализует payload под ограничения API.
   * @param {Record<string, unknown>} raw
   * @returns {Record<string, string | number>}
   */
  function normalizePayload(raw) {
    if (!raw || typeof raw !== "object") return {};
    /** @type {Record<string, string | number>} */
    const out = {};
    let n = 0;
    for (const [k, v] of Object.entries(raw)) {
      if (n >= MAX_KEYS) break;
      const key = String(k).slice(0, MAX_KEY_LEN);
      if (typeof v === "number" && Number.isFinite(v) && Math.floor(v) === v) {
        if (Math.abs(v) > MAX_INT_ABS) continue;
        out[key] = v;
        n += 1;
      } else if (typeof v === "string") {
        out[key] = v.length > MAX_STR_VAL ? v.slice(0, MAX_STR_VAL) : v;
        n += 1;
      }
    }
    return out;
  }

  /**
   * @param {string} event
   * @param {Record<string, unknown>} [payload]
   */
  function send(event, payload) {
    /* Сначала аргументы вызова, затем поля из Telegram — чтобы tg_user_id не подменяли из app.js */
    const merged = { ...(payload || {}), ...getTelegramUserPayload() };
    const p = normalizePayload(merged);
    if (typeof console !== "undefined" && console.info) {
      console.info("[miniapp]", event, p);
    }
    const bodyObj = { event, payload: p, client_ts_ms: Date.now() };
    let text;
    try {
      text = JSON.stringify(bodyObj);
    } catch {
      return;
    }
    try {
      if (typeof navigator !== "undefined" && navigator.sendBeacon) {
        const blob = new Blob([text], { type: "application/json" });
        if (navigator.sendBeacon(ENDPOINT, blob)) return;
      }
    } catch {
      /* игнорируем */
    }
    try {
      fetch(ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: text,
        keepalive: true,
      }).catch(() => {});
    } catch {
      /* игнорируем */
    }
  }

  window.weatherAppLog = { send };
})();

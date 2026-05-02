"use strict";

const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
}

const LS_CITY_KEY = "wf_miniapp_city";
const LS_DAYS_KEY = "wf_miniapp_days";

/** Индекс ползунка 0..2 → параметр `days` для API. */
const SLIDER_TO_DAYS = ["1", "3", "10"];
/** Подписи под ползунком и для aria-valuetext. */
const SLIDER_LABELS = ["1 день", "3 дня", "10 дней"];

const forecastForm = document.getElementById("forecastForm");
const cityInput = document.getElementById("cityInput");
const daysSlider = document.getElementById("daysSlider");
const daysSliderCaption = document.getElementById("daysSliderCaption");
const forecastButton = document.getElementById("forecastButton");
const forecastError = document.getElementById("forecastError");
const forecastSkeleton = document.getElementById("forecastSkeleton");
const forecastSummary = document.getElementById("forecastSummary");
const forecastCards = document.getElementById("forecastCards");
const citySuggestList = document.getElementById("citySuggestList");

/**
 * Подставляет цвета из Telegram Mini App в CSS-переменные страницы.
 * Если SDK недоступен или themeParams пустые, остаются значения из :root в styles.css.
 */
function applyTelegramTheme() {
  const tp = tg?.themeParams;
  const root = document.documentElement;
  if (!tp) return;

  const hasAny = Object.values(tp).some((v) => typeof v === "string" && v.length > 0);
  if (!hasAny) return;

  const pick = (key, fallback) => (typeof tp[key] === "string" && tp[key] ? tp[key] : fallback);

  root.style.setProperty(
    "--app-page-bg",
    pick("secondary_bg_color", pick("bg_color", "#f4f7fb"))
  );
  root.style.setProperty("--app-card-bg", pick("bg_color", "#ffffff"));
  root.style.setProperty("--app-text", pick("text_color", "#1f2937"));
  root.style.setProperty("--app-muted", pick("hint_color", "#6b7280"));
  root.style.setProperty("--app-accent", pick("button_color", "#2563eb"));
  root.style.setProperty("--app-accent-text", pick("button_text_color", "#ffffff"));
  root.style.setProperty("--app-accent-hover", pick("link_color", pick("button_color", "#1d4ed8")));
  root.style.setProperty("--app-border", pick("hint_color", "#e5e7eb"));
}

applyTelegramTheme();
if (tg?.onEvent) {
  tg.onEvent("themeChanged", applyTelegramTheme);
}

/**
 * Текущий индекс ползунка (0 = 1 день, 1 = 3 дня, 2 = 10 дней).
 * @returns {0 | 1 | 2}
 */
function getSliderIndex() {
  const i = parseInt(daysSlider.value, 10);
  if (i === 0 || i === 1 || i === 2) return i;
  return 1;
}

/**
 * Значение `days` для запроса к API по текущему положению ползунка.
 * @returns {string}
 */
function getDaysQueryParam() {
  return SLIDER_TO_DAYS[getSliderIndex()];
}

/**
 * Обновляет подпись под ползунком и aria-valuetext для скринридеров.
 */
function syncDaysSliderUi() {
  const i = getSliderIndex();
  const label = SLIDER_LABELS[i];
  daysSliderCaption.textContent = label;
  daysSlider.setAttribute("aria-valuetext", label);
}

/**
 * Восстанавливает город и период из localStorage (если значения валидны).
 */
function restoreFormFromStorage() {
  try {
    const city = localStorage.getItem(LS_CITY_KEY);
    if (city && city.length <= 100) {
      cityInput.value = city;
    }
    const days = localStorage.getItem(LS_DAYS_KEY);
    if (days === "1") daysSlider.value = "0";
    else if (days === "3") daysSlider.value = "1";
    else if (days === "10") daysSlider.value = "2";
  } catch {
    /* приватный режим / запрет storage — игнорируем */
  }
}

/**
 * Сохраняет последний успешный запрос в localStorage.
 * @param {string} city
 * @param {string} days
 */
function persistFormToStorage(city, days) {
  try {
    localStorage.setItem(LS_CITY_KEY, city);
    localStorage.setItem(LS_DAYS_KEY, days);
  } catch {
    /* игнорируем */
  }
}

/**
 * Маппинг кода WMO (Open-Meteo) в emoji для карточки дня.
 * Текстовое описание по-прежнему приходит с backend в поле `weather`.
 * @param {unknown} code
 * @returns {string}
 */
function weatherCodeToEmoji(code) {
  const c = Number(code);
  if (!Number.isFinite(c)) return "🌡️";
  if (c === 0) return "☀️";
  if (c >= 1 && c <= 3) {
    return ["🌤️", "⛅", "☁️"][c - 1] || "☁️";
  }
  if (c >= 45 && c <= 48) return "🌫️";
  if (c >= 51 && c <= 57) return "🌦️";
  if (c >= 61 && c <= 67) return "🌧️";
  if (c >= 71 && c <= 77) return "❄️";
  if (c >= 80 && c <= 82) return "🌧️";
  if (c >= 85 && c <= 86) return "🌨️";
  if (c >= 95 && c <= 99) return "⛈️";
  return "🌡️";
}

/**
 * Форматирует дату прогноза (YYYY-MM-DD) для отображения в ru-RU.
 * @param {string} isoDate
 * @returns {string}
 */
function formatForecastDate(isoDate) {
  const d = new Date(`${isoDate}T12:00:00Z`);
  if (Number.isNaN(d.getTime())) return isoDate;
  return d.toLocaleDateString("ru-RU", {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

/**
 * Отображение температуры в карточке (до одного знака после запятой).
 * @param {unknown} t
 * @returns {string}
 */
function formatTempDisplay(t) {
  const n = Number(t);
  if (!Number.isFinite(n)) return "—";
  return Math.abs(n % 1) < 1e-9 ? String(n) : n.toFixed(1);
}

/**
 * Собирает блок «↓ tmin · ↑ tmax» с доступным названием для скринридеров.
 * @param {unknown} minT
 * @param {unknown} maxT
 * @returns {HTMLDivElement}
 */
function buildTempsRow(minT, maxT) {
  const minStr = formatTempDisplay(minT);
  const maxStr = formatTempDisplay(maxT);
  const wrap = document.createElement("div");
  wrap.className = "day-card-temps";
  wrap.setAttribute("role", "group");
  wrap.setAttribute("aria-label", `Минимум ${minStr} °C, максимум ${maxStr} °C`);

  const minBlock = document.createElement("span");
  minBlock.className = "day-card-temp-min";
  const minArrow = document.createElement("span");
  minArrow.className = "day-card-temp-arrow";
  minArrow.setAttribute("aria-hidden", "true");
  minArrow.textContent = "↓";
  const minVal = document.createElement("span");
  minVal.className = "day-card-temp-value";
  minVal.textContent = `${minStr}°C`;
  minBlock.append(minArrow, minVal);

  const sep = document.createElement("span");
  sep.className = "day-card-temp-sep";
  sep.setAttribute("aria-hidden", "true");
  sep.textContent = "·";

  const maxBlock = document.createElement("span");
  maxBlock.className = "day-card-temp-max";
  const maxArrow = document.createElement("span");
  maxArrow.className = "day-card-temp-arrow";
  maxArrow.setAttribute("aria-hidden", "true");
  maxArrow.textContent = "↑";
  const maxVal = document.createElement("span");
  maxVal.className = "day-card-temp-value";
  maxVal.textContent = `${maxStr}°C`;
  maxBlock.append(maxArrow, maxVal);

  wrap.append(minBlock, sep, maxBlock);
  return wrap;
}

/**
 * Преобразует поле `detail` из ответа FastAPI в строку для пользователя.
 * @param {unknown} detail
 * @returns {string}
 */
function formatErrorDetail(detail) {
  if (detail == null) return "Ошибка запроса";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) return String(item.msg);
        return JSON.stringify(item);
      })
      .join("; ");
  }
  if (typeof detail === "object") return JSON.stringify(detail);
  return String(detail);
}

/**
 * GET к backend: парсит JSON и выбрасывает ошибку с понятным текстом при !ok.
 * @param {string} url
 * @returns {Promise<Record<string, unknown>>}
 */
async function fetchJson(url) {
  const response = await fetch(url);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(formatErrorDetail(data?.detail));
  }
  return data;
}

/** Автодополнение городов: debounce и запрос к `GET /api/geocode`. */
const CITY_SUGGEST_DEBOUNCE_MS = 280;
/** @type {ReturnType<typeof setTimeout> | null} */
let citySuggestDebounceId = null;
/** @type {AbortController | null} */
let citySuggestAbort = null;
/** @type {{ name: string; label: string }[]} */
let citySuggestItems = [];
/** Индекс подсвеченного варианта в listbox (-1 если список закрыт). */
let citySuggestActive = -1;

/**
 * Закрывает listbox подсказок и отменяет отложенный/текущий запрос.
 */
function hideCitySuggestions() {
  if (citySuggestDebounceId) {
    clearTimeout(citySuggestDebounceId);
    citySuggestDebounceId = null;
  }
  if (citySuggestAbort) {
    citySuggestAbort.abort();
    citySuggestAbort = null;
  }
  citySuggestItems = [];
  citySuggestActive = -1;
  citySuggestList.hidden = true;
  citySuggestList.innerHTML = "";
  cityInput.setAttribute("aria-expanded", "false");
  cityInput.removeAttribute("aria-activedescendant");
}

/**
 * Синхронизирует визуальное выделение и `aria-activedescendant` с `citySuggestActive`.
 */
function syncCitySuggestHighlight() {
  const children = citySuggestList.querySelectorAll('[role="option"]');
  children.forEach((el, i) => {
    const selected = i === citySuggestActive;
    el.setAttribute("aria-selected", selected ? "true" : "false");
    el.classList.toggle("city-suggest-item--active", selected);
  });
  if (citySuggestActive >= 0 && citySuggestActive < children.length) {
    cityInput.setAttribute("aria-activedescendant", children[citySuggestActive].id);
  } else {
    cityInput.removeAttribute("aria-activedescendant");
  }
}

/**
 * Подставляет выбранный город в поле и закрывает подсказки.
 */
function applyCitySuggestion() {
  if (citySuggestActive < 0 || citySuggestActive >= citySuggestItems.length) return;
  const picked = citySuggestItems[citySuggestActive];
  cityInput.value = picked.name;
  hideCitySuggestions();
}

/**
 * Рендерит варианты подсказок; при пустом массиве закрывает listbox.
 * @param {{ name: string; label: string }[]} items
 */
function showCitySuggestions(items) {
  citySuggestItems = items;
  citySuggestList.innerHTML = "";
  if (items.length === 0) {
    hideCitySuggestions();
    return;
  }
  citySuggestActive = 0;
  items.forEach((item, i) => {
    const li = document.createElement("li");
    li.id = `city-suggest-opt-${i}`;
    li.className = "city-suggest-item";
    li.setAttribute("role", "option");
    li.setAttribute("aria-selected", i === 0 ? "true" : "false");

    const main = document.createElement("span");
    main.className = "city-suggest-item-name";
    main.textContent = item.name;

    li.appendChild(main);
    if (item.label && item.label !== item.name) {
      const sub = document.createElement("span");
      sub.className = "city-suggest-item-sub";
      sub.textContent = item.label;
      li.appendChild(sub);
    }

    li.addEventListener("mousedown", (e) => {
      e.preventDefault();
      citySuggestActive = i;
      applyCitySuggestion();
    });
    citySuggestList.appendChild(li);
  });
  citySuggestList.hidden = false;
  cityInput.setAttribute("aria-expanded", "true");
  syncCitySuggestHighlight();
}

/**
 * Запрашивает подсказки у backend; при ошибке сети/API список скрывается без шума в UI.
 * @param {string} q — уже trim, длина ≥ 2
 */
async function runCitySuggestQuery(q) {
  if (citySuggestAbort) citySuggestAbort.abort();
  citySuggestAbort = new AbortController();
  const { signal } = citySuggestAbort;
  try {
    const res = await fetch(`/api/geocode?query=${encodeURIComponent(q)}`, { signal });
    const raw = await res.json().catch(() => ({}));
    if (!res.ok) {
      hideCitySuggestions();
      return;
    }
    const list = Array.isArray(raw.suggestions) ? raw.suggestions : [];
    const cleaned = list
      .map((row) => ({
        name: typeof row.name === "string" ? row.name : "",
        label: typeof row.label === "string" ? row.label : "",
      }))
      .filter((row) => row.name.length > 0)
      .slice(0, 10);
    if (cityInput.value.trim() !== q) return;
    showCitySuggestions(cleaned);
  } catch (err) {
    if (signal.aborted) return;
    hideCitySuggestions();
  }
}

/**
 * Планирует запрос подсказок после паузы в наборе (debounce).
 */
function scheduleCitySuggest() {
  if (citySuggestDebounceId) clearTimeout(citySuggestDebounceId);
  const q = cityInput.value.trim();
  if (q.length < 2) {
    hideCitySuggestions();
    return;
  }
  citySuggestDebounceId = setTimeout(() => {
    citySuggestDebounceId = null;
    void runCitySuggestQuery(q);
  }, CITY_SUGGEST_DEBOUNCE_MS);
}

function setErrorVisible(message) {
  forecastError.textContent = message;
  forecastError.hidden = false;
}

function setErrorHidden() {
  forecastError.hidden = true;
  forecastError.textContent = "";
}

/**
 * Показывает skeleton-заглушки на время запроса.
 * @param {number} count
 */
function showSkeleton(count) {
  forecastSkeleton.innerHTML = "";
  const n = Math.min(Math.max(count, 1), 10);
  for (let i = 0; i < n; i += 1) {
    const el = document.createElement("div");
    el.className = "skeleton-card";
    forecastSkeleton.appendChild(el);
  }
  forecastSkeleton.hidden = false;
  forecastSkeleton.setAttribute("aria-hidden", "false");
}

function hideSkeleton() {
  forecastSkeleton.hidden = true;
  forecastSkeleton.setAttribute("aria-hidden", "true");
  forecastSkeleton.innerHTML = "";
}

/**
 * Рендерит карточки дней прогноза (безопасно через DOM API).
 * @param {unknown} data — ответ GET /api/forecast
 */
function renderForecastCards(data) {
  forecastCards.innerHTML = "";
  const city = typeof data.city === "string" ? data.city : "";
  const days = typeof data.days === "number" ? data.days : Number(data.days);
  forecastSummary.replaceChildren();
  const cityEl = document.createElement("strong");
  cityEl.className = "forecast-summary-city";
  cityEl.textContent = city;
  const sepEl = document.createElement("span");
  sepEl.className = "forecast-summary-sep";
  sepEl.textContent = " · ";
  const daysEl = document.createElement("span");
  daysEl.className = "forecast-summary-days";
  daysEl.textContent = `${Number.isFinite(days) ? days : "—"} дн.`;
  forecastSummary.append(cityEl, sepEl, daysEl);
  forecastSummary.hidden = false;

  const items = Array.isArray(data.forecast) ? data.forecast : [];
  for (const item of items) {
    const dateStr = typeof item.date === "string" ? item.date : "";
    const minT = item.min_temp_c;
    const maxT = item.max_temp_c;
    const weather = typeof item.weather === "string" ? item.weather : "";
    const emoji = weatherCodeToEmoji(item.weather_code);

    const article = document.createElement("article");
    article.className = "day-card";

    const icon = document.createElement("div");
    icon.className = "day-card-icon";
    icon.textContent = emoji;
    icon.setAttribute("aria-hidden", "true");

    const dateEl = document.createElement("div");
    dateEl.className = "day-card-date";
    dateEl.textContent = formatForecastDate(dateStr);

    const temps = buildTempsRow(minT, maxT);

    const desc = document.createElement("div");
    desc.className = "day-card-desc";
    desc.textContent = weather;

    article.appendChild(icon);
    article.appendChild(dateEl);
    article.appendChild(temps);
    article.appendChild(desc);

    forecastCards.appendChild(article);
  }
}

/**
 * Валидация города: trim, длина 2–100 (как на backend).
 * @param {string} city
 * @returns {string | null} нормализованный город или null при ошибке
 */
function validateCity(city) {
  const t = city.trim();
  if (!t) {
    setErrorVisible("Введите город.");
    return null;
  }
  if (t.length < 2) {
    setErrorVisible("Название города — не менее 2 символов.");
    return null;
  }
  if (t.length > 100) {
    setErrorVisible("Название города слишком длинное (максимум 100 символов).");
    return null;
  }
  return t;
}

/**
 * Запрашивает прогноз, управляет skeleton, ошибкой и disabled кнопки.
 */
async function submitForecast() {
  setErrorHidden();
  hideCitySuggestions();
  const rawCity = cityInput.value;
  const city = validateCity(rawCity);
  if (!city) {
    forecastSummary.hidden = true;
    forecastCards.innerHTML = "";
    cityInput.value = rawCity.trim();
    return;
  }
  cityInput.value = city;

  const days = getDaysQueryParam();
  const daysNum = parseInt(days, 10);

  forecastSummary.hidden = true;
  forecastCards.innerHTML = "";
  showSkeleton(Number.isFinite(daysNum) ? daysNum : 3);

  forecastButton.disabled = true;
  try {
    const data = await fetchJson(
      `/api/forecast?city=${encodeURIComponent(city)}&days=${encodeURIComponent(days)}`
    );
    hideSkeleton();
    renderForecastCards(data);
    persistFormToStorage(city, days);
  } catch (error) {
    hideSkeleton();
    const msg = error instanceof Error ? error.message : String(error);
    setErrorVisible(`Ошибка: ${msg}`);
    forecastSummary.hidden = true;
    forecastCards.innerHTML = "";
  } finally {
    forecastButton.disabled = false;
  }
}

cityInput.addEventListener("input", scheduleCitySuggest);

cityInput.addEventListener("blur", () => {
  window.setTimeout(() => hideCitySuggestions(), 200);
});

cityInput.addEventListener("keydown", (e) => {
  const listOpen = !citySuggestList.hidden && citySuggestItems.length > 0;
  if (e.key === "Escape") {
    if (listOpen) {
      e.preventDefault();
      hideCitySuggestions();
    }
    return;
  }
  if (!listOpen) return;
  if (e.key === "ArrowDown") {
    e.preventDefault();
    citySuggestActive = Math.min(citySuggestActive + 1, citySuggestItems.length - 1);
    syncCitySuggestHighlight();
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    citySuggestActive = Math.max(citySuggestActive - 1, 0);
    syncCitySuggestHighlight();
  } else if (e.key === "Enter") {
    e.preventDefault();
    applyCitySuggestion();
  }
});

restoreFormFromStorage();
syncDaysSliderUi();

daysSlider.addEventListener("input", syncDaysSliderUi);
daysSlider.addEventListener("change", syncDaysSliderUi);

forecastForm.addEventListener("submit", (event) => {
  event.preventDefault();
  submitForecast();
});

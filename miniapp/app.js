const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
}

const mockButton = document.getElementById("mockButton");
const mockResult = document.getElementById("mockResult");
const cityInput = document.getElementById("cityInput");
const daysSelect = document.getElementById("daysSelect");
const forecastButton = document.getElementById("forecastButton");
const forecastResult = document.getElementById("forecastResult");

/**
 * Преобразует поле `detail` из ответа FastAPI в строку для пользователя.
 * @param {unknown} detail — строка, массив объектов валидации или объект.
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

mockButton.addEventListener("click", async () => {
  mockResult.textContent = "Проверяем...";
  try {
    const data = await fetchJson("/api/mock");
    mockResult.textContent = data.message;
  } catch (error) {
    mockResult.textContent = `Ошибка: ${error.message}`;
  }
});

forecastButton.addEventListener("click", async () => {
  const city = cityInput.value.trim();
  const days = daysSelect.value;

  if (!city) {
    forecastResult.textContent = "Введите город.";
    return;
  }

  forecastResult.textContent = "Загружаем прогноз...";
  try {
    const data = await fetchJson(
      `/api/forecast?city=${encodeURIComponent(city)}&days=${encodeURIComponent(days)}`
    );

    const lines = [`Город: ${data.city}`, `Период: ${data.days} дн.`, ""];
    const items = Array.isArray(data.forecast) ? data.forecast : [];
    for (const item of items) {
      lines.push(
        `${item.date}: ${item.min_temp_c}°C … ${item.max_temp_c}°C, ${item.weather}`
      );
    }
    forecastResult.textContent = lines.join("\n");
  } catch (error) {
    forecastResult.textContent = `Ошибка: ${error.message}`;
  }
});

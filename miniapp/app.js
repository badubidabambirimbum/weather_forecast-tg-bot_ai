const tg = window.Telegram?.WebApp;
if (tg) {
  // Сообщаем Telegram, что Mini App готов к отображению.
  tg.ready();
  // Раскрываем веб-вью на максимум, чтобы пользователю было удобнее.
  tg.expand();
}

// Основные элементы интерфейса, с которыми работает скрипт.
const mockButton = document.getElementById("mockButton");
const mockResult = document.getElementById("mockResult");

async function fetchJson(url, options = {}) {
  // Унифицированный helper для HTTP-запросов к backend API.
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data?.detail || "Ошибка запроса";
    throw new Error(detail);
  }
  return data;
}

mockButton.addEventListener("click", async () => {
  // Мгновенно показываем состояние загрузки, чтобы пользователь видел реакцию UI.
  mockResult.textContent = "Проверяем...";
  try {
    // Для прод-окружения используем относительный путь: frontend и API на одном домене.
    const data = await fetchJson("/api/mock");
    mockResult.textContent = data.message;
  } catch (error) {
    mockResult.textContent = `Ошибка: ${error.message}`;
  }
});

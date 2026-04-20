(function () {
  const tg = window.Telegram && window.Telegram.WebApp;
  if (tg) {
    tg.ready();
    tg.expand();
    if (tg.themeParams && tg.themeParams.bg_color) {
      document.body.style.background = tg.themeParams.bg_color;
    }
  }

  const form = document.getElementById("form");
  const cityInput = document.getElementById("city");
  const submitBtn = document.getElementById("submit");
  const errorEl = document.getElementById("error");
  const resultEl = document.getElementById("result");

  function showError(msg) {
    errorEl.textContent = msg;
    errorEl.hidden = !msg;
  }

  function getInitData() {
    var w = window.Telegram && window.Telegram.WebApp;
    if (w && typeof w.initData === "string" && w.initData.length) {
      return w.initData;
    }
    try {
      var u = new URL(window.location.href);
      var q = u.searchParams.get("tgWebAppData");
      if (q) {
        return q;
      }
      if (u.hash) {
        var h = new URLSearchParams(u.hash.replace(/^#/, ""));
        var hq = h.get("tgWebAppData");
        if (hq) {
          return hq;
        }
      }
    } catch (err) {}
    return "";
  }

  function buildInitDataFromUnsafe() {
    var w = window.Telegram && window.Telegram.WebApp;
    var u = w && w.initDataUnsafe;
    if (!u || typeof u !== "object") return "";

    // Для серверной верификации обязательно нужен hash.
    if (!u.hash || typeof u.hash !== "string" || !u.hash.length) return "";

    var parts = [];
    Object.keys(u).forEach(function (k) {
      var v = u[k];
      if (v === undefined || v === null) return;
      if (typeof v === "object") {
        v = JSON.stringify(v);
      } else {
        v = String(v);
      }
      parts.push(
        encodeURIComponent(k) + "=" + encodeURIComponent(v)
      );
    });
    return parts.join("&");
  }

  function getTelegramDebug() {
    var w = window.Telegram && window.Telegram.WebApp;
    var unsafe = w && w.initDataUnsafe && typeof w.initDataUnsafe === "object"
      ? w.initDataUnsafe
      : null;
    return {
      has_telegram_webapp: !!w,
      tg_platform: w && w.platform ? String(w.platform) : null,
      init_data_len:
        w && typeof w.initData === "string" ? w.initData.length : 0,
      has_init_data_unsafe: !!unsafe,
      init_data_unsafe_keys: unsafe ? Object.keys(unsafe) : [],
    };
  }

  async function resolveInitData() {
    var attempts = 10;
    var delayMs = 250;
    for (var i = 0; i < attempts; i++) {
      var d = getInitData();
      if (d) return d;
      d = buildInitDataFromUnsafe();
      if (d) return d;
      await new Promise(function (r) {
        setTimeout(r, delayMs);
      });
    }
    return "";
  }

  function render(data) {
    resultEl.innerHTML = "";
    const loc = document.createElement("div");
    loc.className = "loc";
    loc.textContent = data.location;
    resultEl.appendChild(loc);

    (data.daily || []).forEach(function (d) {
      const box = document.createElement("div");
      box.className = "day";
      const head = document.createElement("div");
      head.className = "day-head";
      const date = document.createElement("span");
      date.className = "day-date";
      date.textContent = d.label;
      const temp = document.createElement("span");
      temp.className = "day-temp";
      temp.textContent =
        d.temp_min != null && d.temp_max != null
          ? d.temp_min + "…" + d.temp_max + " °C"
          : "—";
      head.appendChild(date);
      head.appendChild(temp);
      box.appendChild(head);

      const desc = document.createElement("div");
      desc.className = "day-desc";
      desc.textContent = d.description || "";
      box.appendChild(desc);

      const meta = document.createElement("div");
      meta.className = "day-meta";
      meta.textContent =
        "Ветер до " +
        (d.wind_max_ms != null ? d.wind_max_ms : "—") +
        " м/с · влажность ~" +
        (d.humidity_avg != null ? d.humidity_avg : "—") +
        "% · осадки до " +
        (d.precipitation_prob_max != null ? d.precipitation_prob_max : "—") +
        "%";
      box.appendChild(meta);
      resultEl.appendChild(box);
    });

    resultEl.hidden = false;
  }

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    showError("");
    const city = (cityInput.value || "").trim();
    if (!city) return;

    submitBtn.disabled = true;
    try {
      const initData = await resolveInitData();
      const tgDebug = getTelegramDebug();
      const res = await fetch("/api/weather", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          city: city,
          init_data: initData || null,
          client_debug: tgDebug,
        }),
      });
      const payload = await res.json().catch(function () {
        return {};
      });
      if (!res.ok) {
        var detail = payload.detail;
        if (Array.isArray(detail) && detail[0] && detail[0].msg) {
          detail = detail[0].msg;
        }
        if (
          res.status === 401 &&
          typeof detail === "string" &&
          detail.indexOf("init_data") !== -1
        ) {
          if (
            tgDebug &&
            tgDebug.has_telegram_webapp &&
            tgDebug.has_init_data_unsafe &&
            !tgDebug.init_data_len
          ) {
            detail +=
              " Telegram открыл WebApp, но не передал initData. Обычно помогает: 1) в @BotFather выполнить /setdomain и указать домен вашего ngrok (без https://), 2) заново отправить /start и открыть Mini App новой кнопкой, 3) полностью закрыть и открыть Telegram Desktop.";
          } else {
            detail +=
              " Проверьте, что Mini App открыт кнопкой из Telegram, а не прямой ссылкой в браузере. Обычно так бывает с localtunnel (страница с вводом IP ломает контекст Telegram). Попробуйте ngrok: ngrok http 8000, обновите PUBLIC_BASE_URL. Локально без Telegram: ALLOW_UNVERIFIED_MINI_APP=1 в .env.";
          }
        }
        showError(detail || "Ошибка запроса");
        resultEl.hidden = true;
        return;
      }
      render(payload);
    } catch (err) {
      showError("Нет сети или сервер недоступен");
      resultEl.hidden = true;
    } finally {
      submitBtn.disabled = false;
    }
  });
})();

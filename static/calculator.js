(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const form = $("forecast-form");
  const fields = ["origin", "destination", "date", "price"];
  const normal = new Intl.NumberFormat("ru-RU", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const whole = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
  const percent = new Intl.NumberFormat("ru-RU", { style: "percent", maximumFractionDigits: 1 });
  const scientific = new Intl.NumberFormat("ru-RU", { notation: "scientific", maximumFractionDigits: 2 });
  const number = value => Math.abs(Number(value)) >= 1e10 ? scientific.format(Number(value)) : normal.format(Number(value));
  const currency = value => `${number(value)} ₽`;
  const dateText = (value, long = false) => new Intl.DateTimeFormat("ru-RU", {
    day: "numeric", month: long ? "long" : "short", year: "numeric", timeZone: "UTC"
  }).format(new Date(`${value}T00:00:00Z`));
  let routes = [];
  let busy = false;
  let calculation = 0;
  let dateRequest = 0;
  let activeController;
  let datesController;
  let latestResult = null;

  function updateButton() {
    $("calculate").disabled = busy || !$("origin").value || !$("destination").value || !$("date").value || $("date").disabled;
  }
  function setBusy(value) {
    busy = value;
    $("calculate").querySelector(".spinner").hidden = !value;
    $("calculate").querySelector(".button-arrow").hidden = value;
    $("calculate").querySelector(".button-text").textContent = value ? "Рассчитываем…" : "Рассчитать прогноз";
    form.setAttribute("aria-busy", String(value));
    $("raw-mode").disabled = value;
    updateButton();
  }
  function resetErrors() {
    fields.forEach(name => {
      $(`${name}-error`).textContent = "";
      $(name).removeAttribute("aria-invalid");
    });
    $("message").hidden = true;
  }
  function clearResults(status = "Ожидает расчёта") {
    calculation += 1;
    activeController?.abort();
    setBusy(false);
    $("result").hidden = true;
    latestResult = null;
    $("empty-state").hidden = false;
    $("result-status").textContent = status;
    $("result-status").classList.remove("ready");
    if (window.Plotly && $("chart").classList.contains("js-plotly-plot")) window.Plotly.purge("chart");
    $("chart").replaceChildren();
    const placeholder = document.createElement("div");
    placeholder.className = "chart-placeholder";
    placeholder.textContent = "График появится после расчёта";
    $("chart").append(placeholder);
  }
  function showError(text, fieldErrors = {}) {
    $("message").className = "message";
    $("message").textContent = text;
    $("message").hidden = false;
    Object.entries(fieldErrors).forEach(([name, errors]) => {
      if (!fields.includes(name)) return;
      $(`${name}-error`).textContent = errors.join(" ");
      $(name).setAttribute("aria-invalid", "true");
    });
  }
  async function request(url, options = {}) {
    let response;
    try {
      response = await fetch(url, { credentials: "same-origin", ...options });
    } catch (error) {
      if (error.name === "AbortError") throw error;
      throw new Error("Не удалось связаться с сервером. Проверьте соединение и повторите расчёт.");
    }
    let data;
    try { data = await response.json(); }
    catch { throw new Error("Сервис временно недоступен. Попробуйте ещё раз позже."); }
    if (!response.ok) {
      const error = new Error(data.error?.message || "Не удалось выполнить запрос.");
      error.fields = data.error?.fields;
      throw error;
    }
    return data;
  }
  function fillSelect(select, values) {
    select.replaceChildren(...values.map(({ value, label }) => new Option(label, value)));
    select.disabled = values.length === 0;
  }
  function selectedRoute() {
    return routes.find(route => route.origin === $("origin").value && route.destination === $("destination").value);
  }
  async function loadDates() {
    const token = ++dateRequest;
    datesController?.abort();
    datesController = new AbortController();
    const route = selectedRoute();
    $("date").disabled = true;
    $("date").replaceChildren(new Option("Загружаем даты…", ""));
    updateButton();
    if (!route) return;
    $("price").value = Number(route.base_price).toString();
    $("price-note").textContent = route.price_min !== null && route.price_max !== null
      ? `Рекомендуемый диапазон: ${whole.format(Number(route.price_min))}–${whole.format(Number(route.price_max))} ₽. Можно проверить цену за его пределами.`
      : "Можно проверить любую неотрицательную цену.";
    try {
      const data = await request(`/api/routes/${encodeURIComponent(route.code)}/dates`, { signal: datesController.signal });
      if (token !== dateRequest) return;
      fillSelect($("date"), data.dates.map(item => ({ value: item.date, label: dateText(item.date, true) })));
      updateButton();
    } catch (error) {
      if (token !== dateRequest || error.name === "AbortError") return;
      $("date").replaceChildren(new Option("Даты недоступны", ""));
      showError(error.message);
    }
  }
  async function plot(data, raw = false) {
    if (!window.Plotly) throw new Error("Не удалось загрузить график. Обновите страницу.");
    const points = raw ? data.quantiles : data.nonnegative_quantiles;
    const levels = points.map(point => Number(point.level));
    const demands = points.map(point => Number(point.demand));
    const details = points.map(point => [percent.format(Number(point.level)), number(point.demand)]);
    if (demands.some(value => !Number.isFinite(value))) throw new Error("Масштаб значений слишком велик для графика. Проверьте цену.");
    $("chart").replaceChildren();
    await window.Plotly.newPlot("chart", [
      { x: levels, y: demands, type: "scatter", mode: "lines+markers", name: raw ? "Спрос по формуле" : "Спрос",
        line: { color: "#4269d8", width: 2.5 }, marker: { size: 6, color: "#4269d8" },
        customdata: details, hovertemplate: "Квантиль %{customdata[0]}<br>Спрос: %{customdata[1]}<extra></extra>" },
      { x: [levels[4]], y: [demands[4]], type: "scatter", mode: "markers", name: "Медиана",
        marker: { size: 11, color: "#142b50", line: { color: "white", width: 2 } },
        customdata: [details[4]], hovertemplate: "Медиана · 50%<br>Спрос: %{customdata[1]}<extra></extra>" },
      { x: [0.1, 0.9], y: [data.seats, data.seats], type: "scatter", mode: "lines", name: "Вместимость",
        line: { color: "#b0bccd", dash: "dash", width: 1.5 }, hovertemplate: "Вместимость: %{y}<extra></extra>" }
    ], {
      height: 326, autosize: true, margin: { l: 53, r: 17, b: 64, t: 17 },
      paper_bgcolor: "#fff", plot_bgcolor: "#fff", font: { family: "Segoe UI, Arial, sans-serif", size: 10, color: "#8391a5" },
      xaxis: { tickvals: levels, tickformat: ".0%", title: { text: "Уровень квантиля", standoff: 13 }, fixedrange: true, showgrid: false, zeroline: false },
      yaxis: { title: { text: "Спрос, пассажиров", standoff: 10 }, fixedrange: true, gridcolor: "#edf1f6", zerolinecolor: "#c8d1df", tickformat: ",.0f", separatethousands: true },
      separators: ", ", hovermode: "closest", showlegend: true,
      legend: { orientation: "h", x: 0, y: -0.25, font: { size: 9 }, traceorder: "normal" }
    }, { responsive: true, displayModeBar: false, scrollZoom: false });
  }
  function showDemand(data, raw) {
    $("demand").textContent = number(raw ? data.median_demand : data.nonnegative_median_demand);
    $("demand-label").textContent = raw ? "Медианный спрос по формуле" : "Медианный спрос";
    $("mode-description").textContent = raw ? "Линейная оценка без ограничения нулём" : "Спрос не ниже нуля";
    $("negative-note").hidden = !data.has_negative_quantiles;
    $("negative-note").textContent = raw
      ? "Отрицательные значения — результат линейной формулы, а не количество пассажиров. Продажи всегда не ниже нуля."
      : data.negative_demand
        ? "При этой цене ожидаемого спроса нет. Спрос и продажи показаны как 0; исходный расчёт доступен в режиме «Исходная формула»."
        : "Некоторые нижние сценарии вышли ниже нуля и показаны как 0. Проверить расчёт можно в режиме «Исходная формула».";
  }
  function animateResult() {
    $("result").classList.remove("result-enter");
    void $("result").offsetWidth;
    $("result").classList.add("result-enter");
  }
  async function calculate() {
    clearResults("Выполняем расчёт…");
    resetErrors();
    const price = $("price");
    if (!price.value || !Number.isFinite(price.valueAsNumber) || price.valueAsNumber < 0) {
      showError("Проверьте цену билета.", { price: ["Укажите конечную неотрицательную цену."] });
      price.focus();
      $("result-status").textContent = "Проверьте параметры";
      return;
    }
    const token = calculation;
    activeController = new AbortController();
    const controller = activeController;
    let timedOut = false;
    const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, 15000);
    setBusy(true);
    try {
      const data = await request("/api/forecast", {
        method: "POST", signal: controller.signal,
        headers: { "Content-Type": "application/json", "X-CSRFToken": form.querySelector("[name=csrfmiddlewaretoken]").value },
        body: JSON.stringify({ origin: $("origin").value, destination: $("destination").value, date: $("date").value, price: price.value })
      });
      if (token !== calculation) return;
      const raw = $("raw-mode").checked;
      await plot(data, raw);
      if (token !== calculation) return;
      $("flight-name").textContent = `${data.route.origin} → ${data.route.destination}`;
      $("flight-date").textContent = `${dateText(data.date, true)} · ${data.route.code}`;
      $("flight-price").textContent = currency(data.price);
      $("seats").textContent = whole.format(data.seats);
      showDemand(data, raw);
      $("sales").textContent = number(data.sales);
      $("free").textContent = number(data.free_seats);
      $("load-factor").textContent = `Загрузка ${percent.format(Number(data.load_factor))}`;
      const interpretations = {
        above_capacity: "Спрос превышает вместимость. Прогноз продаж ограничен числом мест.",
        below_capacity: "Спрос ниже вместимости. По прогнозу часть мест останется свободной.",
        at_capacity: "Медианный спрос соответствует вместимости рейса.",
        zero_sales: data.seats === 0 ? "На эту дату вместимость равна нулю, продажи невозможны." : "При этой цене прогноз продаж равен нулю."
      };
      $("interpretation").textContent = interpretations[data.interpretation];
      const imported = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short", year: "numeric", timeZone: "Europe/Moscow" }).format(new Date(data.dataset.imported_at));
      $("dataset-meta").textContent = `Версия ${data.dataset.id.slice(0, 8)} · импорт ${imported}`;
      $("empty-state").hidden = true;
      $("result").hidden = false;
      latestResult = data;
      animateResult();
      $("result-status").textContent = "Прогноз рассчитан";
      $("result-status").classList.add("ready");
    } catch (error) {
      if (token !== calculation) return;
      clearResults("Расчёт недоступен");
      showError(timedOut ? "Сервер не ответил вовремя. Попробуйте ещё раз." : error.name === "AbortError" ? "Запрос отменён." : error.message, error.fields);
    } finally {
      clearTimeout(timeout);
      if (token === calculation || timedOut) setBusy(false);
    }
  }
  $("raw-mode").addEventListener("change", async () => {
    const data = latestResult;
    if (!data || busy) return;
    const token = calculation;
    const raw = $("raw-mode").checked;
    $("raw-mode").disabled = true;
    try {
      await plot(data, raw);
      if (token !== calculation || latestResult !== data) return;
      showDemand(data, raw);
      animateResult();
    } catch (error) {
      if (token === calculation) {
        clearResults("График недоступен");
        showError(error.message);
      }
    } finally {
      $("raw-mode").disabled = busy;
    }
  });
  async function initialize() {
    try {
      const data = await request("/api/routes");
      routes = data.routes;
      if (!routes.length) throw new Error("Нет доступных направлений в текущей версии прогноза.");
      $("period").textContent = `${dateText(data.period.start)} — ${dateText(data.period.end)}`;
      $("coverage").textContent = `${routes.length} направлений · даты из загруженной версии`;
      fillSelect($("origin"), [...new Set(routes.map(route => route.origin))].map(city => ({ value: city, label: city })));
      fillSelect($("destination"), routes.filter(route => route.origin === $("origin").value).map(route => ({ value: route.destination, label: route.destination })));
      await loadDates();
      if (!$("date").disabled) await calculate();
    } catch (error) {
      $("period").textContent = "Прогноз недоступен";
      $("coverage").textContent = "Не удалось получить данные";
      fields.filter(name => name !== "price").forEach(name => { $(name).disabled = true; });
      clearResults("Нет данных");
      showError(error.message);
      const retry = document.createElement("button");
      retry.type = "button";
      retry.className = "nav-link";
      retry.textContent = "Попробовать снова";
      retry.addEventListener("click", () => { resetErrors(); initialize(); });
      $("message").append(document.createElement("br"), retry);
    }
  }
  form.addEventListener("submit", event => { event.preventDefault(); if (!busy) calculate(); });
  $("origin").addEventListener("change", async () => {
    clearResults("Параметры изменены"); resetErrors();
    fillSelect($("destination"), routes.filter(route => route.origin === $("origin").value).map(route => ({ value: route.destination, label: route.destination })));
    await loadDates();
  });
  $("destination").addEventListener("change", async () => { clearResults("Параметры изменены"); resetErrors(); await loadDates(); });
  ["date", "price"].forEach(name => $(name).addEventListener(name === "price" ? "input" : "change", () => { clearResults("Параметры изменены"); resetErrors(); updateButton(); }));
  initialize();
})();

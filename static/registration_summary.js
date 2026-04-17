(async function () {
  const config = window.appConfig || {};
  const statusEl = document.getElementById("status");
  const summaryViewEl = document.getElementById("summary-view");
  const metaEl = document.getElementById("summary-meta");
  const exceptionDatesEl = document.getElementById("exception-dates");
  const latestAvailableDatesEl = document.getElementById("latest-available-dates");
  const weekdays = ["日", "月", "火", "水", "木", "金", "土"];

  function setStatus(message, isError) {
    statusEl.textContent = message;
    statusEl.classList.toggle("error", Boolean(isError));
  }

  function showSummary(show) {
    summaryViewEl.classList.toggle("hidden", !show);
  }

  async function initLiff() {
    if (!config.liffId) {
      throw new Error("LIFF ID が設定されていません。");
    }
    await liff.init({ liffId: config.liffId });
    if (!liff.isLoggedIn()) {
      liff.login();
      return null;
    }
    const context = liff.getContext();
    return context && context.userId ? context.userId : null;
  }

  function formatDateOnly(value) {
    const date = new Date(value);
    const yyyy = date.getFullYear();
    const mm = String(date.getMonth() + 1).padStart(2, "0");
    const dd = String(date.getDate()).padStart(2, "0");
    return `${yyyy}年${mm}月${dd}日（${weekdays[date.getDay()]}）`;
  }

  function formatTimeOnly(value) {
    const date = new Date(value);
    const hh = String(date.getHours()).padStart(2, "0");
    const mi = String(date.getMinutes()).padStart(2, "0");
    return `${hh}:${mi}`;
  }

  function groupDates(values) {
    const groups = new Map();
    [...new Set(values)].sort().forEach((value) => {
      const dateKey = value.slice(0, 10);
      if (!groups.has(dateKey)) {
        groups.set(dateKey, []);
      }
      groups.get(dateKey).push(value);
    });
    return Array.from(groups.entries());
  }

  function renderMeta(payload) {
    metaEl.innerHTML = "";
    const typeLabel = payload.notification_type === "driverlicense" ? "運転免許" : "美容院";
    const items = [
      ["通知種別", typeLabel],
      ["通知状態", payload.notification_enabled ? "ON" : "OFF"],
      ["通知期限日", payload.last_date || "未設定"],
    ];

    items.forEach(([label, value]) => {
      const dt = document.createElement("dt");
      dt.textContent = label;
      const dd = document.createElement("dd");
      dd.textContent = value;
      metaEl.appendChild(dt);
      metaEl.appendChild(dd);
    });
  }

  function renderGroupedList(targetEl, values, emptyText) {
    targetEl.innerHTML = "";
    if (!values || values.length === 0) {
      const emptyEl = document.createElement("p");
      emptyEl.className = "summary-empty";
      emptyEl.textContent = emptyText;
      targetEl.appendChild(emptyEl);
      return;
    }

    groupDates(values).forEach(([dateKey, items]) => {
      const row = document.createElement("div");
      row.className = "summary-row";

      const dateEl = document.createElement("p");
      dateEl.className = "summary-date";
      dateEl.textContent = formatDateOnly(`${dateKey}T00:00:00`);

      const timesEl = document.createElement("p");
      timesEl.className = "summary-times";
      timesEl.textContent = items.map((value) => formatTimeOnly(value)).join(", ");

      row.appendChild(dateEl);
      row.appendChild(timesEl);
      targetEl.appendChild(row);
    });
  }

  function renderSimpleList(targetEl, values, emptyText) {
    targetEl.innerHTML = "";
    if (!values || values.length === 0) {
      const emptyEl = document.createElement("p");
      emptyEl.className = "summary-empty";
      emptyEl.textContent = emptyText;
      targetEl.appendChild(emptyEl);
      return;
    }

    values.forEach((value) => {
      const row = document.createElement("div");
      row.className = "summary-row";

      const textEl = document.createElement("p");
      textEl.className = "summary-times";
      textEl.textContent = value;

      row.appendChild(textEl);
      targetEl.appendChild(row);
    });
  }

  async function loadSummary(userId) {
    const response = await fetch("/api/registration-summary", {
      headers: {
        "X-Line-User-Id": userId,
      },
    });
    if (!response.ok) {
      throw new Error("登録情報の取得に失敗しました。");
    }
    return response.json();
  }

  try {
    const userId = await initLiff();
    if (!userId) {
      return;
    }

    const payload = await loadSummary(userId);
    renderMeta(payload);
    renderGroupedList(exceptionDatesEl, payload.exception_dates, "登録済みの除外日時はありません。");
    if (payload.notification_type === "driverlicense") {
      renderSimpleList(latestAvailableDatesEl, payload.latest_available_dates, "空きはありません。");
    } else {
      renderGroupedList(latestAvailableDatesEl, payload.latest_available_dates, "空きはありません。");
    }
    setStatus("");
    showSummary(true);
  } catch (error) {
    setStatus(error.message || "登録情報の読み込みに失敗しました。", true);
    showSummary(false);
  }
})();

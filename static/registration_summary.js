(async function () {
  const config = window.appConfig || {};
  const statusEl = document.getElementById("status");
  const summaryViewEl = document.getElementById("summary-view");
  const metaEl = document.getElementById("summary-meta");
  const exceptionDatesEl = document.getElementById("exception-dates");
  const latestAvailableDatesEl = document.getElementById("latest-available-dates");
  const changeDateButtonEl = document.getElementById("change-date-button");
  const removeExceptionLinkEl = document.getElementById("remove-exception-link");
  const weekdays = ["日", "月", "火", "水", "木", "金", "土"];

  function setStatus(message, isError) {
    statusEl.textContent = message;
    statusEl.classList.toggle("error", Boolean(isError));
  }

  function showSummary(show) {
    summaryViewEl.classList.toggle("hidden", !show);
  }

  function isPreviewMode() {
    const params = new URLSearchParams(window.location.search);
    return params.get("preview") === "1" || ["localhost", "127.0.0.1"].includes(window.location.hostname);
  }

  async function initLiff() {
    if (isPreviewMode()) {
      return "__preview__";
    }
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
    const items = [
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

  function bindActions(userId) {
    if (removeExceptionLinkEl) {
      if (config.removeUrl) {
        removeExceptionLinkEl.href = config.removeUrl;
      } else {
        removeExceptionLinkEl.classList.add("disabled-link");
        removeExceptionLinkEl.setAttribute("aria-disabled", "true");
      }
    }

    if (!changeDateButtonEl) {
      return;
    }

    changeDateButtonEl.addEventListener("click", async () => {
      if (userId === "__preview__") {
        setStatus("プレビューでは日付変更メッセージは送信されません。");
        return;
      }
      try {
        await liff.sendMessages([{ type: "text", text: "日付変更" }]);
        setStatus("LINEに「日付変更」を送信しました。トーク画面で日付を選択してください。");
      } catch (error) {
        setStatus("日付変更メッセージの送信に失敗しました。LINEトークから「日付変更」を送信してください。", true);
      }
    });
  }

  async function loadSummary(userId) {
    if (userId === "__preview__") {
      return {
        notification_enabled: true,
        last_date: "2099-12-31",
        exception_dates: ["2099-12-20T11:00:00", "2099-12-20T13:30:00", "2099-12-22T15:00:00"],
        latest_available_dates: ["2099-12-24T10:00:00", "2099-12-24T14:30:00", "2099-12-25T18:00:00"],
      };
    }

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
    renderGroupedList(latestAvailableDatesEl, payload.latest_available_dates, "最新の空き状況はありません。");
    bindActions(userId);
    setStatus(userId === "__preview__" ? "プレビュー表示です。" : "最新の登録情報を表示しています。");
    showSummary(true);
  } catch (error) {
    setStatus(error.message || "登録情報の読み込みに失敗しました。", true);
    showSummary(false);
  }
})();

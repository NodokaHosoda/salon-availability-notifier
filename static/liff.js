(async function () {
  const config = window.appConfig || {};
  const statusEl = document.getElementById("status");
  const formEl = document.getElementById("selection-form");
  const listEl = document.getElementById("date-list");
  const submitButton = document.getElementById("submit-button");

  function setStatus(message, isError) {
    statusEl.textContent = message;
    statusEl.classList.toggle("error", Boolean(isError));
  }

  function showForm(show) {
    formEl.classList.toggle("hidden", !show);
  }

  function formatDisplay(isoString) {
    const date = new Date(isoString);
    const weekdays = ["日", "月", "火", "水", "木", "金", "土"];
    const yyyy = date.getFullYear();
    const mm = String(date.getMonth() + 1).padStart(2, "0");
    const dd = String(date.getDate()).padStart(2, "0");
    const hh = String(date.getHours()).padStart(2, "0");
    const mi = String(date.getMinutes()).padStart(2, "0");
    return `${yyyy}年${mm}月${dd}日（${weekdays[date.getDay()]}）${hh}:${mi}`;
  }

  function getEncodedDatesFromQuery() {
    const params = new URLSearchParams(window.location.search);
    const encoded = params.get("dates");
    if (!encoded) {
      return [];
    }
    return encoded
      .split(",")
      .filter(Boolean)
      .map((value) => `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}T${value.slice(8, 10)}:${value.slice(10, 12)}:00`);
  }

  function unique(values) {
    return Array.from(new Set(values));
  }

  function isPreviewMode() {
    const params = new URLSearchParams(window.location.search);
    return params.get("preview") === "1" || ["localhost", "127.0.0.1"].includes(window.location.hostname);
  }

  function renderDates(dateValues) {
    listEl.innerHTML = "";
    dateValues.forEach((value, index) => {
      const card = document.createElement("div");
      card.className = "date-card";

      const input = document.createElement("input");
      input.type = "checkbox";
      input.id = `date-${index}`;
      input.value = value;

      const label = document.createElement("label");
      label.htmlFor = input.id;
      label.textContent = formatDisplay(value);

      card.appendChild(input);
      card.appendChild(label);
      listEl.appendChild(card);
    });
  }

  function getSelectedDates() {
    return Array.from(listEl.querySelectorAll("input:checked")).map((input) => input.value);
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

  async function loadDates(userId) {
    if (config.mode === "add") {
      const addDates = unique(getEncodedDatesFromQuery());
      if (addDates.length > 0) {
        return addDates;
      }
      if (userId === "__preview__") {
        return ["2099-12-24T10:00:00", "2099-12-25T14:30:00"];
      }
      return [];
    }

    if (userId === "__preview__") {
      return ["2099-12-20T11:00:00", "2099-12-22T15:00:00"];
    }

    const response = await fetch("/api/exceptions", {
      headers: {
        "X-Line-User-Id": userId,
      },
    });
    if (!response.ok) {
      throw new Error("除外日一覧の取得に失敗しました。");
    }
    const payload = await response.json();
    return unique(payload.dates || []);
  }

  async function submitDates(userId, dates) {
    if (userId === "__preview__") {
      return config.mode === "add"
        ? { saved_count: dates.length }
        : { removed_count: dates.length };
    }

    const endpoint = config.mode === "add" ? "/api/exceptions" : "/api/exceptions/remove";
    const response = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Line-User-Id": userId,
      },
      body: JSON.stringify({ dates }),
    });
    if (!response.ok) {
      throw new Error("更新に失敗しました。");
    }
    return response.json();
  }

  try {
    const userId = await initLiff();
    if (!userId) {
      return;
    }

    const dates = await loadDates(userId);
    if (userId === "__preview__") {
      setStatus("プレビュー表示です。送信処理はローカルでは実行されません。");
    }
    if (dates.length === 0) {
      setStatus(config.mode === "add" ? "今回追加できる候補はありません。" : "現在、登録済みの除外日はありません。");
      showForm(false);
      return;
    }

    renderDates(dates);
    setStatus("対象の日付を選択してください。");
    showForm(true);

    formEl.addEventListener("submit", async (event) => {
      event.preventDefault();
      const selectedDates = getSelectedDates();
      if (selectedDates.length === 0) {
        setStatus("日付を1件以上選択してください。", true);
        return;
      }

      const confirmMessage = config.mode === "add"
        ? "選択した日付を除外対象に追加しますか？"
        : "選択した日付を除外対象から外しますか？";
      if (!window.confirm(confirmMessage)) {
        return;
      }

      submitButton.disabled = true;
      const payload = await submitDates(userId, selectedDates);
      if (config.mode === "add") {
        setStatus(`${payload.saved_count}件の除外日を追加しました。`);
      } else {
        setStatus(`${payload.removed_count}件の除外日を解除しました。`);
      }
      showForm(false);
    });
  } catch (error) {
    setStatus(error.message || "画面の初期化に失敗しました。", true);
    showForm(false);
  }
})();

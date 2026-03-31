(async function () {
  const config = window.appConfig || {};
  const statusEl = document.getElementById("status");
  const formEl = document.getElementById("selection-form");
  const listEl = document.getElementById("date-list");
  const submitButton = document.getElementById("submit-button");
  const weekdays = ["日", "月", "火", "水", "木", "金", "土"];

  function setStatus(message, isError) {
    statusEl.textContent = message;
    statusEl.classList.toggle("error", Boolean(isError));
  }

  function showForm(show) {
    formEl.classList.toggle("hidden", !show);
  }

  function formatDisplay(isoString) {
    const date = new Date(isoString);
    const yyyy = date.getFullYear();
    const mm = String(date.getMonth() + 1).padStart(2, "0");
    const dd = String(date.getDate()).padStart(2, "0");
    const hh = String(date.getHours()).padStart(2, "0");
    const mi = String(date.getMinutes()).padStart(2, "0");
    return `${yyyy}年${mm}月${dd}日（${weekdays[date.getDay()]}）${hh}:${mi}`;
  }

  function formatDateLabel(dateKey) {
    const date = new Date(`${dateKey}T00:00:00`);
    const yyyy = date.getFullYear();
    const mm = String(date.getMonth() + 1).padStart(2, "0");
    const dd = String(date.getDate()).padStart(2, "0");
    return `${yyyy}年${mm}月${dd}日（${weekdays[date.getDay()]}）`;
  }

  function formatTimeLabel(isoString) {
    const date = new Date(isoString);
    const hh = String(date.getHours()).padStart(2, "0");
    const mi = String(date.getMinutes()).padStart(2, "0");
    return `${hh}:${mi}`;
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

  function groupDates(dateValues) {
    const groups = new Map();
    unique(dateValues)
      .sort()
      .forEach((value) => {
        const dateKey = value.slice(0, 10);
        if (!groups.has(dateKey)) {
          groups.set(dateKey, []);
        }
        groups.get(dateKey).push(value);
      });
    return Array.from(groups.entries()).map(([dateKey, times]) => ({ dateKey, times }));
  }

  function isPreviewMode() {
    const params = new URLSearchParams(window.location.search);
    return params.get("preview") === "1" || ["localhost", "127.0.0.1"].includes(window.location.hostname);
  }

  function renderDates(dateValues) {
    listEl.innerHTML = "";
    groupDates(dateValues).forEach(({ dateKey, times }, index) => {
      const card = document.createElement("section");
      card.className = "date-card";
      if (times.length === 1) {
        card.dataset.singleValue = times[0];
      }

      const header = document.createElement("div");
      header.className = "date-row";

      const input = document.createElement("input");
      input.type = "checkbox";
      input.id = `date-${index}`;
      input.className = "date-toggle";
      input.dataset.dateKey = dateKey;

      const label = document.createElement("label");
      label.htmlFor = input.id;
      label.className = "date-label";
      label.textContent = `${formatDateLabel(dateKey)}をすべて選択`;

      header.appendChild(input);
      header.appendChild(label);
      card.appendChild(header);

      if (times.length > 1) {
        const picker = document.createElement("div");
        picker.className = "time-picker";

        const selectLabel = document.createElement("label");
        selectLabel.htmlFor = `time-select-${index}`;
        selectLabel.className = "time-label";
        selectLabel.textContent = "時間帯を1つ選択";

        const select = document.createElement("select");
        select.id = `time-select-${index}`;
        select.className = "time-select";
        select.dataset.dateKey = dateKey;

        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = "選択してください";
        select.appendChild(placeholder);

        times.forEach((value) => {
          const option = document.createElement("option");
          option.value = value;
          option.textContent = formatTimeLabel(value);
          select.appendChild(option);
        });

        input.addEventListener("change", () => {
          select.disabled = input.checked;
          if (input.checked) {
            select.value = "";
          }
        });

        select.addEventListener("change", () => {
          if (select.value) {
            input.checked = false;
          }
        });

        picker.appendChild(selectLabel);
        picker.appendChild(select);
        card.appendChild(picker);
      } else {
        const singleTime = document.createElement("p");
        singleTime.className = "time-hint";
        singleTime.textContent = `時間帯: ${formatTimeLabel(times[0])}`;
        card.appendChild(singleTime);
      }

      listEl.appendChild(card);
    });
  }

  function getSelectedDates() {
    const selectedDates = [];

    listEl.querySelectorAll(".date-card").forEach((card) => {
      const dateToggle = card.querySelector(".date-toggle");
      const timeSelect = card.querySelector(".time-select");
      const timeOptions = timeSelect
        ? Array.from(timeSelect.options)
            .map((option) => option.value)
            .filter(Boolean)
        : [];

      if (dateToggle && dateToggle.checked) {
        selectedDates.push(...timeOptions);
        if (timeOptions.length === 0 && card.dataset.singleValue) {
          selectedDates.push(card.dataset.singleValue);
        }
        return;
      }

      if (timeSelect && timeSelect.value) {
        selectedDates.push(timeSelect.value);
      }
    });

    return unique(selectedDates);
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
        return ["2099-12-24T10:00:00", "2099-12-24T14:30:00", "2099-12-25T18:00:00"];
      }
      return [];
    }

    if (userId === "__preview__") {
      return ["2099-12-20T11:00:00", "2099-12-20T13:30:00", "2099-12-22T15:00:00"];
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
    setStatus("日付を選ぶとその日の全時間帯、未選択ならプルダウンで個別時間を選べます。");
    showForm(true);

    formEl.addEventListener("submit", async (event) => {
      event.preventDefault();
      const selectedDates = getSelectedDates();
      if (selectedDates.length === 0) {
        setStatus("日付または時間帯を1件以上選択してください。", true);
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

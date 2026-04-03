(async function () {
  const config = window.appConfig || {};
  const statusEl = document.getElementById("status");
  const formEl = document.getElementById("selection-form");
  const listEl = document.getElementById("date-list");
  const submitButton = document.getElementById("submit-button");
  let backButtonEl = null;
  const weekdays = ["日", "月", "火", "水", "木", "金", "土"];

  function setStatus(message, isError) {
    statusEl.textContent = message;
    statusEl.classList.toggle("error", Boolean(isError));
  }

  function showForm(show) {
    formEl.classList.toggle("hidden", !show);
  }

  function showBackButton(show) {
    if (!backButtonEl) {
      backButtonEl = document.createElement("button");
      backButtonEl.type = "button";
      backButtonEl.className = "secondary form-return hidden";
      backButtonEl.textContent = config.mode === "add" ? "除外日追加画面に戻る" : "除外日解除画面に戻る";
      backButtonEl.addEventListener("click", () => {
        window.location.reload();
      });
      formEl.insertAdjacentElement("afterend", backButtonEl);
    }

    backButtonEl.classList.toggle("hidden", !show);
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

        const dropdown = document.createElement("details");
        dropdown.className = "time-dropdown";

        const summary = document.createElement("summary");
        summary.className = "time-dropdown-summary";

        const summaryText = document.createElement("span");
        summaryText.className = "time-dropdown-text";
        summaryText.textContent = "時間帯を選択";

        const summaryCount = document.createElement("span");
        summaryCount.className = "time-dropdown-count";

        summary.appendChild(summaryText);
        summary.appendChild(summaryCount);

        const menu = document.createElement("div");
        menu.className = "time-dropdown-menu";

        const optionCheckboxes = [];

        function updateDropdownState() {
          const selected = optionCheckboxes.filter((checkbox) => checkbox.checked);
          if (selected.length === 0) {
            summaryText.textContent = "時間帯を選択";
            summaryCount.textContent = "";
            return;
          }

          const labels = selected.map((checkbox) => formatTimeLabel(checkbox.value));
          summaryText.textContent = labels.slice(0, 2).join(", ");
          summaryCount.textContent = selected.length > 2 ? ` 他${selected.length - 2}件` : "";
        }

        times.forEach((value, timeIndex) => {
          const optionLabel = document.createElement("label");
          optionLabel.className = "time-option";
          optionLabel.htmlFor = `time-${index}-${timeIndex}`;

          const checkbox = document.createElement("input");
          checkbox.type = "checkbox";
          checkbox.id = `time-${index}-${timeIndex}`;
          checkbox.className = "time-option-checkbox";
          checkbox.value = value;

          const optionText = document.createElement("span");
          optionText.className = "time-option-text";
          optionText.textContent = formatTimeLabel(value);

          checkbox.addEventListener("change", () => {
            if (checkbox.checked) {
              input.checked = false;
            }
            updateDropdownState();
          });

          optionCheckboxes.push(checkbox);
          optionLabel.appendChild(checkbox);
          optionLabel.appendChild(optionText);
          menu.appendChild(optionLabel);
        });

        input.addEventListener("change", () => {
          if (input.checked) {
            optionCheckboxes.forEach((checkbox) => {
              checkbox.checked = false;
            });
            dropdown.open = false;
            dropdown.classList.add("disabled");
          } else {
            dropdown.classList.remove("disabled");
          }
          updateDropdownState();
        });

        summary.addEventListener("click", (event) => {
          if (dropdown.classList.contains("disabled")) {
            event.preventDefault();
          }
        });

        dropdown.appendChild(summary);
        dropdown.appendChild(menu);
        picker.appendChild(dropdown);
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
      const timeCheckboxes = Array.from(card.querySelectorAll(".time-option-checkbox"));

      if (dateToggle && dateToggle.checked) {
        if (timeCheckboxes.length > 0) {
          selectedDates.push(...timeCheckboxes.map((checkbox) => checkbox.value));
        } else if (card.dataset.singleValue) {
          selectedDates.push(card.dataset.singleValue);
        }
        return;
      }

      timeCheckboxes.forEach((checkbox) => {
        if (checkbox.checked) {
          selectedDates.push(checkbox.value);
        }
      });
    });

    return unique(selectedDates);
  }

  async function initLiff() {
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
      const response = await fetch("/api/registration-summary", {
        headers: {
          "X-Line-User-Id": userId,
        },
      });
      if (!response.ok) {
        throw new Error("最新の空き状況の取得に失敗しました。");
      }
      const payload = await response.json();
      const latestAvailableDates = unique(payload.latest_available_dates || []);
      const exceptionDates = new Set(unique(payload.exception_dates || []));
      return latestAvailableDates.filter((value) => !exceptionDates.has(value));
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
    if (dates.length === 0) {
      setStatus(config.mode === "add" ? "今回追加できる候補はありません。" : "現在、登録済みの除外日はありません。");
      showForm(false);
      showBackButton(false);
      return;
    }

    renderDates(dates);
    setStatus("");
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
      showBackButton(true);
    });
  } catch (error) {
    setStatus(error.message || "画面の初期化に失敗しました。", true);
    showForm(false);
    showBackButton(false);
  }
})();

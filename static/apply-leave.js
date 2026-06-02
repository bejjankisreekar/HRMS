(function () {
  "use strict";

  const cfg = window.LA_CONFIG || {};
  const form = document.getElementById("applyLeaveForm");
  if (!form) return;

  const leaveType = form.querySelector('[name="leave_type"]');
  const startDate = form.querySelector('[name="start_date"]');
  const endDate = form.querySelector('[name="end_date"]');
  const reason = form.querySelector('[name="reason"]');
  const fileInput = form.querySelector('[name="attachment"]');
  const dropzone = document.getElementById("laDropzone");
  const filePreview = document.getElementById("laFilePreview");
  const fileName = document.getElementById("laFileName");
  const fileRemove = document.getElementById("laFileRemove");

  const elTotal = document.getElementById("laTotalDays");
  const elSumType = document.getElementById("sumType");
  const elSumDates = document.getElementById("sumDates");
  const elSumDays = document.getElementById("sumDays");
  const elSumBalance = document.getElementById("sumBalance");
  const elPolicy = document.getElementById("laPolicyHint");
  const elWarnings = document.getElementById("laWarnings");
  const elTeamImpact = document.getElementById("laTeamImpact");
  const elTeamList = document.getElementById("laTeamList");
  const elCharCount = document.getElementById("laCharCount");
  const calCells = document.querySelectorAll("#laCalGrid [data-cal-day]");

  let previewTimer = null;

  function halfDayValue() {
    const checked = form.querySelector('[name="half_day"]:checked');
    return checked ? checked.value : "NONE";
  }

  function fmtDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso + "T12:00:00");
    return d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
  }

  function updateCharCount() {
    if (!reason || !elCharCount) return;
    elCharCount.textContent = String(reason.value.length);
  }

  function updatePolicyHint() {
    if (!leaveType || !elPolicy) return;
    const lt = (cfg.leaveTypes || []).find((t) => t.id === leaveType.value);
    elPolicy.textContent = lt ? lt.policy_hint : "";
    if (elSumType) elSumType.textContent = lt ? lt.name : "—";
  }

  function highlightCalendar() {
    const start = startDate?.value;
    const end = endDate?.value;
    calCells.forEach((cell) => {
      cell.classList.remove("la-cal-mini-cell--selected");
      const d = cell.dataset.calDay;
      if (start && end && d >= start && d <= end) {
        cell.classList.add("la-cal-mini-cell--selected");
      }
    });
  }

  function renderWarnings(warnings) {
    if (!elWarnings) return;
    elWarnings.innerHTML = "";
    if (!warnings || !warnings.length) {
      elWarnings.classList.remove("is-visible");
      return;
    }
    warnings.forEach((w) => {
      const div = document.createElement("div");
      div.className = "la-warning";
      div.innerHTML = `<i data-lucide="alert-triangle" class="h-4 w-4 shrink-0"></i><span>${w}</span>`;
      elWarnings.appendChild(div);
    });
    elWarnings.classList.add("is-visible");
    if (window.lucide) window.lucide.createIcons();
  }

  function renderTeam(team) {
    if (!elTeamList || !elTeamImpact) return;
    elTeamList.innerHTML = "";
    if (!team || !team.length) {
      elTeamImpact.classList.add("hidden");
      return;
    }
    elTeamImpact.textContent = `${team.length} team member(s) already on leave during selected dates.`;
    elTeamImpact.classList.remove("hidden");
    team.forEach((m) => {
      const li = document.createElement("li");
      li.textContent = `${m.name} · ${m.leave_type} (${m.status})`;
      elTeamList.appendChild(li);
    });
  }

  function fetchPreview() {
    const params = new URLSearchParams();
    if (leaveType?.value) params.set("leave_type", leaveType.value);
    if (startDate?.value) params.set("start_date", startDate.value);
    if (endDate?.value) params.set("end_date", endDate.value);
    params.set("half_day", halfDayValue());

    if (!startDate?.value || !endDate?.value) {
      if (elTotal) elTotal.textContent = "—";
      if (elSumDays) elSumDays.textContent = "—";
      if (elSumDates) elSumDates.textContent = "—";
      renderWarnings([]);
      renderTeam([]);
      highlightCalendar();
      return;
    }

    fetch(`${cfg.previewUrl}?${params}`)
      .then((r) => r.json())
      .then((data) => {
        const days = data.total_days_display || "0";
        if (elTotal) elTotal.textContent = days === "0" ? "—" : `${days} day${days === "1" ? "" : "s"}`;
        if (elSumDays) elSumDays.textContent = days === "0" ? "—" : days;
        if (elSumDates) {
          elSumDates.textContent = `${fmtDate(startDate.value)} – ${fmtDate(endDate.value)}`;
        }
        if (elSumBalance) {
          elSumBalance.textContent =
            data.remaining_after != null ? `${Math.max(data.remaining_after, 0)} left` : "—";
        }
        renderWarnings(data.warnings || []);
        renderTeam(data.team_on_leave || []);
        highlightCalendar();
      })
      .catch(() => {});
  }

  function schedulePreview() {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(fetchPreview, 280);
  }

  [leaveType, startDate, endDate].forEach((el) => {
    if (el) el.addEventListener("change", () => {
      updatePolicyHint();
      schedulePreview();
    });
  });

  form.querySelectorAll('[name="half_day"]').forEach((el) => {
    el.addEventListener("change", schedulePreview);
  });

  if (reason) {
    reason.addEventListener("input", updateCharCount);
    updateCharCount();
  }

  if (dropzone && fileInput) {
    fileInput.style.display = "none";
    dropzone.addEventListener("click", () => fileInput.click());
    dropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropzone.classList.add("is-dragover");
    });
    dropzone.addEventListener("dragleave", () => dropzone.classList.remove("is-dragover"));
    dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropzone.classList.remove("is-dragover");
      if (e.dataTransfer.files.length) {
        fileInput.files = e.dataTransfer.files;
        showFilePreview(e.dataTransfer.files[0].name);
      }
    });
    fileInput.addEventListener("change", () => {
      if (fileInput.files.length) showFilePreview(fileInput.files[0].name);
    });
  }

  function showFilePreview(name) {
    if (fileName) fileName.textContent = name;
    filePreview?.classList.add("is-visible");
  }

  fileRemove?.addEventListener("click", () => {
    if (fileInput) fileInput.value = "";
    filePreview?.classList.remove("is-visible");
  });

  function ensureHalfDayDefault() {
    if (!form.querySelector('[name="half_day"]:checked')) {
      const none = form.querySelector('[name="half_day"][value="NONE"]');
      if (none) none.checked = true;
    }
  }

  form.addEventListener("submit", () => {
    ensureHalfDayDefault();
    if (fileInput && fileInput.files.length && fileInput.files[0].size === 0) {
      fileInput.value = "";
    }
  });
  ensureHalfDayDefault();

  updatePolicyHint();
  schedulePreview();
})();

(function () {
  "use strict";

  const chartsData = window.ATTENDANCE_CHARTS;
  if (!chartsData || typeof Chart === "undefined") return;

  const gridColor = "rgba(148, 163, 184, 0.35)";
  const textColor = "#64748b";

  Chart.defaults.color = textColor;
  Chart.defaults.borderColor = gridColor;
  Chart.defaults.font.family = "system-ui, sans-serif";

  function makeChart(id, config) {
    const el = document.getElementById(id);
    if (!el) return;
    new Chart(el, config);
  }

  makeChart("chartMonthly", {
    type: "line",
    data: {
      labels: chartsData.monthly.labels,
      datasets: [
        {
          label: "Present",
          data: chartsData.monthly.present,
          borderColor: "#059669",
          backgroundColor: "rgba(5, 150, 105, 0.12)",
          fill: true,
          tension: 0.35,
        },
        {
          label: "Absent",
          data: chartsData.monthly.absent,
          borderColor: "#fb7185",
          backgroundColor: "rgba(251, 113, 133, 0.08)",
          fill: true,
          tension: 0.35,
        },
        {
          label: "Leave",
          data: chartsData.monthly.leave,
          borderColor: "#fbbf24",
          backgroundColor: "rgba(251, 191, 36, 0.08)",
          fill: true,
          tension: 0.35,
        },
      ],
    },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { position: "bottom" } },
      scales: {
        y: { beginAtZero: true, grid: { color: gridColor } },
        x: { grid: { display: false } },
      },
    },
  });

  makeChart("chartWeekly", {
    type: "bar",
    data: {
      labels: chartsData.weekly.labels,
      datasets: [
        {
          label: "Present",
          data: chartsData.weekly.present,
          backgroundColor: "rgba(14, 165, 233, 0.7)",
          borderRadius: 6,
        },
        {
          label: "Absent",
          data: chartsData.weekly.absent,
          backgroundColor: "rgba(244, 63, 94, 0.6)",
          borderRadius: 6,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { position: "bottom" } },
      scales: {
        y: { beginAtZero: true },
        x: { grid: { display: false } },
      },
    },
  });

  makeChart("chartDepartment", {
    type: "doughnut",
    data: {
      labels: chartsData.department.labels,
      datasets: [
        {
          data: chartsData.department.values,
          backgroundColor: [
            "#0ea5e9",
            "#14b8a6",
            "#2dd4bf",
            "#34d399",
            "#fbbf24",
            "#fb7185",
            "#a78bfa",
            "#818cf8",
          ],
          borderWidth: 0,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { position: "right" } },
    },
  });

  makeChart("chartLate", {
    type: "bar",
    data: {
      labels: chartsData.late.labels,
      datasets: [
        {
          label: "Late check-ins",
          data: chartsData.late.values,
          backgroundColor: "rgba(249, 115, 22, 0.75)",
          borderRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      indexAxis: "y",
      plugins: { legend: { display: false } },
      scales: { x: { beginAtZero: true } },
    },
  });

  document.querySelectorAll("[data-counter]").forEach((el) => {
    const target = parseInt(el.dataset.counter, 10) || 0;
    const duration = 800;
    const start = performance.now();
    function tick(now) {
      const p = Math.min(1, (now - start) / duration);
      el.textContent = Math.round(target * p);
      if (p < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  });

  document.querySelectorAll("[data-progress]").forEach((bar) => {
    const pct = bar.dataset.progress || "0";
    requestAnimationFrame(() => {
      bar.style.width = pct + "%";
    });
  });

  const modal = document.getElementById("employeeModal");
  const modalBody = document.getElementById("employeeModalBody");
  if (!modal || !modalBody) return;

  function closeModal() {
    modal.hidden = true;
    document.body.style.overflow = "";
  }

  document.querySelectorAll("[data-modal-close]").forEach((btn) => {
    btn.addEventListener("click", closeModal);
  });
  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();
  });
  modalBody.addEventListener("click", (e) => {
    if (e.target.closest("[data-modal-close]")) closeModal();
  });

  document.querySelectorAll("[data-employee-id]").forEach((row) => {
    row.addEventListener("click", async () => {
      const id = row.dataset.employeeId;
      const recordDate = row.dataset.recordDate || "";
      modal.hidden = false;
      document.body.style.overflow = "hidden";
      modalBody.innerHTML =
        '<div class="ar-skeleton h-48 w-full"></div><p class="mt-4 text-sm text-slate-400">Loading…</p>';
      try {
        const url = `/attendance/reports/employee/${id}/`;
        const res = await fetch(url);
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Failed");
        modalBody.innerHTML = renderEmployeeModal(data);
        if (window.lucide) lucide.createIcons();
      } catch (err) {
        modalBody.innerHTML = `<p class="text-rose-400 text-sm">${err.message}</p>`;
      }
    });
  });

  function statusClass(s) {
    const map = {
      PRESENT: "ar-cal-present",
      ABSENT: "ar-cal-absent",
      LEAVE: "ar-cal-leave",
      WFH: "ar-cal-wfh",
      HALF_DAY: "ar-cal-half",
    };
    return map[s] || "ar-cal-none";
  }

  function renderEmployeeModal(data) {
    const cal = data.calendar;
    const days = cal.days || [];
    let calHtml = '<div class="grid grid-cols-7 gap-1 mt-2">';
    days.forEach((d) => {
      calHtml += `<div class="ar-cal-day ${statusClass(d.status)}" title="${d.status}">${d.day}</div>`;
    });
    calHtml += "</div>";

    let recentHtml = "";
    (data.recent_records || []).slice(0, 10).forEach((r) => {
      recentHtml += `<tr><td class="py-2 text-slate-400">${r.date}</td><td class="py-2">${r.check_in}</td><td class="py-2">${r.check_out}</td><td class="py-2">${r.status}</td><td class="py-2">${r.hours}</td></tr>`;
    });

    return `
      <div class="flex items-start justify-between gap-4">
        <div>
          <h3 class="text-lg font-semibold text-white">${data.employee.name}</h3>
          <p class="text-sm text-slate-400">${data.employee.employee_id} · ${data.employee.department}</p>
        </div>
        <button type="button" data-modal-close class="ar-btn-ghost text-xs">Close</button>
      </div>
      <dl class="mt-4 grid grid-cols-2 gap-3 text-sm">
        <div><dt class="text-slate-500">Designation</dt><dd class="text-white">${data.employee.designation}</dd></div>
        <div><dt class="text-slate-500">Shift</dt><dd class="text-white">${data.shift.name} (${data.shift.range})</dd></div>
        <div><dt class="text-slate-500">Present this month</dt><dd class="text-emerald-400 font-semibold">${data.month_stats.present_days} days</dd></div>
        <div><dt class="text-slate-500">Biometric</dt><dd class="text-violet-300">${data.integrations.biometric}</dd></div>
      </dl>
      <h4 class="mt-6 text-xs font-semibold uppercase text-slate-500">Attendance calendar</h4>
      ${calHtml}
      <h4 class="mt-6 text-xs font-semibold uppercase text-slate-500">Recent history</h4>
      <table class="w-full text-xs mt-2"><thead><tr class="text-slate-500"><th class="text-left py-1">Date</th><th>In</th><th>Out</th><th>Status</th><th>Hours</th></tr></thead><tbody>${recentHtml}</tbody></table>
      <p class="mt-4 text-[11px] text-slate-500">GPS, facial recognition, and device logs — integration ready.</p>
    `;
  }
})();

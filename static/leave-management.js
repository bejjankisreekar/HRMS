(function () {
  "use strict";

  function initApplyLeaveModal() {
    const applyModal = document.getElementById("applyLeaveModal");
    if (!applyModal) return;

    function openModal() {
      applyModal.hidden = false;
      document.body.style.overflow = "hidden";
      if (window.lucide && typeof window.lucide.createIcons === "function") {
        window.lucide.createIcons();
      }
      const firstField = applyModal.querySelector("select, input, textarea");
      if (firstField) {
        setTimeout(() => firstField.focus(), 50);
      }
    }

    function closeModal() {
      applyModal.hidden = true;
      document.body.style.overflow = "";
    }

    document.querySelectorAll("[data-open-apply]").forEach((btn) => {
      btn.addEventListener("click", openModal);
    });

    document.querySelectorAll("[data-close-modal]").forEach((btn) => {
      btn.addEventListener("click", closeModal);
    });

    applyModal.addEventListener("click", (e) => {
      if (e.target === applyModal) closeModal();
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !applyModal.hidden) closeModal();
    });
  }

  initApplyLeaveModal();

  document.querySelectorAll("[data-counter]").forEach((el) => {
    const target = parseInt(el.dataset.counter, 10) || 0;
    const start = performance.now();
    function tick(now) {
      const p = Math.min(1, (now - start) / 800);
      el.textContent = Math.round(target * p);
      if (p < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  });

  document.querySelectorAll("[data-balance-bar]").forEach((bar) => {
    const pct = Math.min(100, parseFloat(bar.dataset.balanceBar) || 0);
    requestAnimationFrame(() => {
      bar.style.width = pct + "%";
    });
  });

  const calGrid = document.getElementById("leaveCalGrid");
  if (calGrid && window.LEAVE_CALENDAR) {
    const events = window.LEAVE_CALENDAR;
    const byDate = {};
    events.forEach((e) => {
      byDate[e.start] = e;
    });
    calGrid.querySelectorAll("[data-cal-day]").forEach((cell) => {
      const d = cell.dataset.calDay;
      const ev = byDate[d];
      if (ev) {
        cell.classList.add(
          ev.status === "APPROVED"
            ? "lm-cal-approved"
            : ev.status === "PENDING"
              ? "lm-cal-pending"
              : ev.status === "HOLIDAY"
                ? "lm-cal-holiday"
                : "lm-cal-other"
        );
        cell.title = ev.title;
      }
    });
  }

  const data = window.LEAVE_CHARTS;
  if (!data || typeof Chart === "undefined") return;

  const gridColor = "rgba(148, 163, 184, 0.35)";
  Chart.defaults.color = "#64748b";
  Chart.defaults.borderColor = gridColor;

  function chart(id, cfg) {
    const el = document.getElementById(id);
    if (el) new Chart(el, cfg);
  }

  chart("chartLeaveMonthly", {
    type: "line",
    data: {
      labels: data.monthly.labels,
      datasets: [
        {
          label: "Requests",
          data: data.monthly.values,
          borderColor: "#7c3aed",
          backgroundColor: "rgba(124, 58, 237, 0.12)",
          fill: true,
          tension: 0.35,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true } },
    },
  });

  chart("chartLeaveDept", {
    type: "bar",
    data: {
      labels: data.department.labels,
      datasets: [
        {
          label: "Leaves",
          data: data.department.values,
          backgroundColor: "rgba(14, 165, 233, 0.7)",
          borderRadius: 6,
        },
      ],
    },
    options: { responsive: true, plugins: { legend: { display: false } } },
  });

  chart("chartLeaveTypes", {
    type: "doughnut",
    data: {
      labels: data.types.labels,
      datasets: [
        {
          data: data.types.values,
          backgroundColor: ["#0ea5e9", "#14b8a6", "#2dd4bf", "#fbbf24", "#f87171", "#38bdf8"],
          borderWidth: 0,
        },
      ],
    },
    options: { responsive: true, plugins: { legend: { position: "right" } } },
  });
})();

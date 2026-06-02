(function () {
  "use strict";

  const charts = window.SHIFT_CHARTS;
  if (charts && typeof Chart !== "undefined") {
    Chart.defaults.color = "#64748b";
    Chart.defaults.borderColor = "rgba(148, 163, 184, 0.35)";

    function mk(id, cfg) {
      const el = document.getElementById(id);
      if (el) new Chart(el, cfg);
    }

    mk("chartShiftDept", {
      type: "bar",
      data: {
        labels: charts.department.labels,
        datasets: [{ data: charts.department.values, backgroundColor: "rgba(139,92,246,0.7)", borderRadius: 6 }],
      },
      options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } },
    });

    mk("chartShiftTypes", {
      type: "doughnut",
      data: {
        labels: charts.shiftTypes.labels,
        datasets: [{ data: charts.shiftTypes.values, backgroundColor: ["#fbbf24", "#fb923c", "#8b5cf6", "#22d3ee", "#6366f1", "#34d399"] }],
      },
      options: { plugins: { legend: { position: "bottom", labels: { boxWidth: 10 } } } },
    });

    mk("chartOvertime", {
      type: "line",
      data: {
        labels: charts.overtimeTrend.map((x) => x.date),
        datasets: [{ data: charts.overtimeTrend.map((x) => x.hours), borderColor: "#22d3ee", backgroundColor: "rgba(34,211,238,0.15)", fill: true, tension: 0.35 }],
      },
      options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } },
    });

    mk("chartCompliance", {
      type: "bar",
      data: {
        labels: charts.compliance.map((x) => x.date),
        datasets: [{ data: charts.compliance.map((x) => x.rate), backgroundColor: "rgba(16,185,129,0.7)", borderRadius: 6 }],
      },
      options: { plugins: { legend: { display: false } }, scales: { y: { max: 100, beginAtZero: true } } },
    });
  }

  document.querySelectorAll(".sh-counter").forEach((el) => {
    const target = parseFloat(el.dataset.counter || "0");
    const suffix = el.dataset.suffix || "";
    const isFloat = String(target).includes(".");
    let current = 0;
    const steps = 24;
    const inc = target / steps;
    const timer = setInterval(() => {
      current += inc;
      if (current >= target) {
        current = target;
        clearInterval(timer);
      }
      el.textContent = (isFloat ? current.toFixed(1) : Math.round(current)) + suffix;
    }, 30);
  });

  const grid = window.SHIFT_WEEKLY_GRID;
  if (grid && grid.rows) {
    document.querySelectorAll(".sh-shift-cell").forEach((cell) => {
      cell.addEventListener("dragstart", (e) => {
        e.dataTransfer.setData("text/plain", JSON.stringify({
          userId: cell.dataset.userId,
          date: cell.dataset.date,
          shiftId: cell.dataset.shiftId,
        }));
      });
      cell.addEventListener("dragover", (e) => e.preventDefault());
      cell.addEventListener("drop", (e) => {
        e.preventDefault();
        /* Visual feedback only — server assign via form */
      });
    });
  }
})();

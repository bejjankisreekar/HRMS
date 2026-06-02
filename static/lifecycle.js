(function () {
  "use strict";
  const charts = window.LIFECYCLE_CHARTS;
  if (!charts || typeof Chart === "undefined") return;

  Chart.defaults.color = "#64748b";
  Chart.defaults.borderColor = "rgba(148, 163, 184, 0.35)";

  function mk(id, cfg) {
    const el = document.getElementById(id);
    if (el) new Chart(el, cfg);
  }

  if (charts.joiningTrend) {
    mk("chartJoiningTrend", {
      type: "line",
      data: {
        labels: charts.joiningTrend.labels,
        datasets: [{ data: charts.joiningTrend.values, borderColor: "#8b5cf6", fill: true, backgroundColor: "rgba(139,92,246,0.15)", tension: 0.35 }],
      },
      options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } },
    });
  }

  if (charts.departmentHires) {
    mk("chartDeptHires", {
      type: "bar",
      data: {
        labels: charts.departmentHires.labels,
        datasets: [{ data: charts.departmentHires.values, backgroundColor: "rgba(109,40,217,0.75)", borderRadius: 6 }],
      },
      options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } },
    });
  }

  if (charts.documentation) {
    mk("chartDocs", {
      type: "doughnut",
      data: {
        labels: charts.documentation.labels,
        datasets: [{ data: charts.documentation.values, backgroundColor: ["#34d399", "#fbbf24"] }],
      },
      options: { plugins: { legend: { position: "bottom" } } },
    });
  }

  if (charts.exitReasons) {
    mk("chartExitReasons", {
      type: "doughnut",
      data: {
        labels: charts.exitReasons.labels,
        datasets: [{ data: charts.exitReasons.values, backgroundColor: ["#8b5cf6", "#22d3ee", "#f472b6", "#fb923c", "#94a3b8"] }],
      },
      options: { plugins: { legend: { position: "bottom" } } },
    });
  }

  if (charts.clearance) {
    mk("chartClearance", {
      type: "bar",
      data: {
        labels: charts.clearance.labels,
        datasets: [{ data: charts.clearance.values, backgroundColor: ["#34d399", "#fbbf24"], borderRadius: 6 }],
      },
      options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } },
    });
  }

  document.querySelectorAll(".lc-counter").forEach((el) => {
    const target = parseFloat(el.dataset.counter || "0");
    const suffix = el.dataset.suffix || "";
    let current = 0;
    const inc = target / 20 || 0;
    const t = setInterval(() => {
      current += inc;
      if (current >= target) {
        current = target;
        clearInterval(t);
      }
      el.textContent = (Number.isInteger(target) ? Math.round(current) : current.toFixed(1)) + suffix;
    }, 35);
  });
})();

(() => {
  const COLORS = {
    violet: "#8b5cf6",
    emerald: "#10b981",
    amber: "#f59e0b",
    rose: "#f43f5e",
    cyan: "#06b6d4",
    indigo: "#6366f1",
    slate: "#94a3b8",
  };

  const PIE_COLORS = [COLORS.emerald, COLORS.rose, COLORS.amber, COLORS.cyan];

  function readCharts() {
    const el = document.getElementById("starter-charts-data");
    if (!el) return null;
    try {
      return JSON.parse(el.textContent);
    } catch {
      return null;
    }
  }

  function isDark() {
    return document.documentElement.classList.contains("dark");
  }

  function gridColor() {
    return isDark() ? "rgba(255,255,255,0.06)" : "rgba(15,23,42,0.06)";
  }

  function textColor() {
    return isDark() ? "#94a3b8" : "#64748b";
  }

  function baseOptions() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: { color: textColor(), boxWidth: 10, font: { size: 11 } },
        },
      },
    };
  }

  function initCharts() {
    if (typeof Chart === "undefined") return;
    const data = readCharts();
    if (!data) return;

    Chart.defaults.font.family = "Inter, system-ui, sans-serif";

    const attEl = document.getElementById("chart-attendance");
    if (attEl && data.attendance?.values?.some((v) => v > 0)) {
      new Chart(attEl, {
        type: "doughnut",
        data: {
          labels: data.attendance.labels,
          datasets: [{
            data: data.attendance.values,
            backgroundColor: PIE_COLORS,
            borderWidth: 0,
            hoverOffset: 6,
          }],
        },
        options: {
          ...baseOptions(),
          cutout: "62%",
          plugins: { legend: { position: "bottom" } },
        },
      });
    }

    const deptEl = document.getElementById("chart-departments");
    if (deptEl && data.departments?.values?.length) {
      new Chart(deptEl, {
        type: "bar",
        data: {
          labels: data.departments.labels,
          datasets: [{
            label: "Employees",
            data: data.departments.values,
            backgroundColor: COLORS.violet,
            borderRadius: 6,
            maxBarThickness: 36,
          }],
        },
        options: {
          ...baseOptions(),
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { display: false }, ticks: { color: textColor(), font: { size: 10 } } },
            y: { beginAtZero: true, grid: { color: gridColor() }, ticks: { color: textColor(), precision: 0 } },
          },
        },
      });
    }

    const leaveEl = document.getElementById("chart-leave");
    if (leaveEl) {
      new Chart(leaveEl, {
        type: "line",
        data: {
          labels: data.leave.labels,
          datasets: [{
            label: "Leave requests",
            data: data.leave.values,
            borderColor: COLORS.amber,
            backgroundColor: "rgba(245,158,11,0.12)",
            fill: true,
            tension: 0.35,
            pointRadius: 3,
          }],
        },
        options: {
          ...baseOptions(),
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { display: false }, ticks: { color: textColor() } },
            y: { beginAtZero: true, grid: { color: gridColor() }, ticks: { color: textColor(), precision: 0 } },
          },
        },
      });
    }

    const growthEl = document.getElementById("chart-growth");
    if (growthEl) {
      new Chart(growthEl, {
        type: "line",
        data: {
          labels: data.growth.labels,
          datasets: [{
            label: "Employees",
            data: data.growth.values,
            borderColor: COLORS.indigo,
            backgroundColor: "rgba(99,102,241,0.1)",
            fill: true,
            tension: 0.35,
            pointRadius: 3,
          }],
        },
        options: {
          ...baseOptions(),
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { display: false }, ticks: { color: textColor() } },
            y: { beginAtZero: true, grid: { color: gridColor() }, ticks: { color: textColor(), precision: 0 } },
          },
        },
      });
    }

    const payrollEl = document.getElementById("chart-payroll");
    if (payrollEl) {
      new Chart(payrollEl, {
        type: "bar",
        data: {
          labels: data.payroll.labels,
          datasets: [{
            label: "Net payroll (₹)",
            data: data.payroll.values,
            backgroundColor: COLORS.cyan,
            borderRadius: 8,
            maxBarThickness: 48,
          }],
        },
        options: {
          ...baseOptions(),
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { display: false }, ticks: { color: textColor() } },
            y: {
              beginAtZero: true,
              grid: { color: gridColor() },
              ticks: {
                color: textColor(),
                callback: (v) => (v >= 1000 ? `₹${(v / 1000).toFixed(0)}k` : `₹${v}`),
              },
            },
          },
        },
      });
    }
  }

  function boot() {
    if (document.getElementById("starter-charts-data")) {
      if (typeof Chart !== "undefined") {
        initCharts();
      } else {
        window.addEventListener("load", initCharts, { once: true });
      }
    }
    if (typeof lucide !== "undefined" && lucide.createIcons) {
      lucide.createIcons();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();

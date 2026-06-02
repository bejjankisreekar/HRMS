(function () {
  "use strict";

  const chartsData = window.PAYROLL_CHARTS;
  if (chartsData && typeof Chart !== "undefined") {
    Chart.defaults.color = "#64748b";
    Chart.defaults.borderColor = "rgba(148, 163, 184, 0.35)";
    Chart.defaults.font.family = "system-ui, sans-serif";

    function chart(id, cfg) {
      const el = document.getElementById(id);
      if (el) new Chart(el, cfg);
    }

    chart("chartPayrollMonthly", {
      type: "line",
      data: {
        labels: chartsData.monthly.labels,
        datasets: [{
          label: "Net payroll",
          data: chartsData.monthly.values,
          borderColor: "#a78bfa",
          backgroundColor: "rgba(167, 139, 250, 0.15)",
          fill: true,
          tension: 0.35,
        }],
      },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } },
    });

    chart("chartDeptPayroll", {
      type: "bar",
      data: {
        labels: chartsData.department.labels,
        datasets: [{
          data: chartsData.department.values,
          backgroundColor: "rgba(99, 102, 241, 0.7)",
          borderRadius: 6,
        }],
      },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } },
    });

    chart("chartSalaryDist", {
      type: "doughnut",
      data: {
        labels: chartsData.distribution.labels,
        datasets: [{
          data: chartsData.distribution.values,
          backgroundColor: ["#8b5cf6", "#6366f1", "#22d3ee", "#34d399"],
        }],
      },
      options: { responsive: true, maintainAspectRatio: false },
    });

    chart("chartTax", {
      type: "bar",
      data: {
        labels: chartsData.tax.labels,
        datasets: [{ data: chartsData.tax.values, backgroundColor: "#f472b6", borderRadius: 6 }],
      },
      options: { indexAxis: "y", responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } },
    });

    chart("chartBonus", {
      type: "line",
      data: {
        labels: chartsData.bonus.labels,
        datasets: [{
          data: chartsData.bonus.values,
          borderColor: "#34d399",
          backgroundColor: "rgba(52, 211, 153, 0.12)",
          fill: true,
          tension: 0.35,
        }],
      },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } },
    });

    chart("chartForecast", {
      type: "line",
      data: {
        labels: chartsData.forecast.labels,
        datasets: [{
          data: chartsData.forecast.values,
          borderColor: "#22d3ee",
          borderDash: [4, 4],
          fill: false,
          tension: 0.35,
        }],
      },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } },
    });

    chart("chartOvertime", {
      type: "bar",
      data: {
        labels: chartsData.overtime.labels,
        datasets: [{ data: chartsData.overtime.values, backgroundColor: "#fbbf24", borderRadius: 6 }],
      },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } },
    });
  }

  document.querySelectorAll("[data-counter]").forEach((el) => {
    const target = parseFloat(el.dataset.counter) || 0;
    const isMoney = el.dataset.money === "1";
    const duration = 800;
    const start = performance.now();
    function tick(now) {
      const p = Math.min(1, (now - start) / duration);
      const val = target * p;
      el.textContent = isMoney
        ? "₹" + val.toLocaleString("en-IN", { maximumFractionDigits: 0 })
        : Math.round(val).toLocaleString();
      if (p < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  });

  const progress = document.getElementById("payrollProgress");
  if (progress) {
    const pct = parseInt(progress.dataset.progress || "0", 10);
    requestAnimationFrame(() => {
      progress.querySelector(".pr-progress-bar").style.width = pct + "%";
    });
  }

  document.querySelectorAll(".pr-table tbody tr[data-payslip]").forEach((row) => {
    row.addEventListener("click", () => {
      const id = row.dataset.payslip;
      if (!id) return;
      const params = new URLSearchParams(window.location.search);
      params.set("payslip", id);
      window.location = "?" + params.toString();
    });
  });
})();

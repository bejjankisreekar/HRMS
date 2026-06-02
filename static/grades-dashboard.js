function initGradesDashboard() {
  "use strict";

  const cfg = window.GRADES_CONFIG || {};

  function initCharts() {
    if (typeof Chart === "undefined") return;

    const catEl = document.getElementById("grd-chart-category");
    if (catEl && cfg.categoryChart) {
      new Chart(catEl, {
        type: "doughnut",
        data: {
          labels: cfg.categoryChart.labels,
          datasets: [
            {
              data: cfg.categoryChart.values,
              backgroundColor: ["#14b8a6", "#6366f1", "#f59e0b", "#ef4444", "#8b5cf6", "#64748b"],
            },
          ],
        },
        options: { responsive: true, plugins: { legend: { position: "bottom" } } },
      });
    }

    const empEl = document.getElementById("grd-chart-employees");
    if (empEl && cfg.employeeChart) {
      new Chart(empEl, {
        type: "bar",
        data: {
          labels: cfg.employeeChart.labels,
          datasets: [
            {
              label: "Employees",
              data: cfg.employeeChart.values,
              backgroundColor: "rgba(20, 184, 166, 0.65)",
              borderRadius: 6,
            },
          ],
        },
        options: { responsive: true, scales: { y: { beginAtZero: true } } },
      });
    }
  }

  async function postAction(payload) {
    const res = await fetch(cfg.apiAction, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": cfg.csrf },
      body: JSON.stringify(payload),
    });
    return res.json();
  }

  document.querySelectorAll("[data-grd-seed]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("Seed default HR and employee grades? Existing grades are kept.")) return;
      btn.disabled = true;
      try {
        await postAction({ action: "seed_defaults" });
        window.location.reload();
      } catch (e) {
        alert("Failed to seed grades.");
      } finally {
        btn.disabled = false;
      }
    });
  });

  initCharts();
  if (window.lucide) window.lucide.createIcons();
}

document.addEventListener("DOMContentLoaded", initGradesDashboard);

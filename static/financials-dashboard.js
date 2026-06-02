function initFinancialsDashboard() {
  "use strict";

  const cfg = window.FINANCIALS_CONFIG || {};
  const charts = cfg.charts || {};

  function initCharts() {
    if (typeof Chart === "undefined") return;

    const revenueEl = document.getElementById("fin-chart-revenue");
    if (revenueEl && charts.revenue) {
      new Chart(revenueEl, {
        type: "line",
        data: {
          labels: charts.revenue.labels,
          datasets: [
            {
              label: "Revenue (INR)",
              data: charts.revenue.values,
              borderColor: "#8b5cf6",
              backgroundColor: "rgba(139, 92, 246, 0.12)",
              fill: true,
              tension: 0.35,
            },
          ],
        },
        options: chartOpts(),
      });
    }

    const subsEl = document.getElementById("fin-chart-subs");
    if (subsEl && charts.subscriptions) {
      new Chart(subsEl, {
        type: "bar",
        data: {
          labels: charts.subscriptions.labels,
          datasets: [
            {
              label: "Active",
              data: charts.subscriptions.active,
              backgroundColor: "rgba(16, 185, 129, 0.7)",
            },
            {
              label: "Trial",
              data: charts.subscriptions.trial,
              backgroundColor: "rgba(245, 158, 11, 0.7)",
            },
          ],
        },
        options: chartOpts(true),
      });
    }

    const plansEl = document.getElementById("fin-chart-plans");
    if (plansEl && charts.plans) {
      new Chart(plansEl, {
        type: "doughnut",
        data: {
          labels: charts.plans.map((p) => p.name),
          datasets: [
            {
              data: charts.plans.map((p) => p.mrr),
              backgroundColor: ["#8b5cf6", "#6366f1", "#22d3ee", "#10b981", "#f59e0b"],
            },
          ],
        },
        options: { responsive: true, plugins: { legend: { position: "bottom" } } },
      });
    }

    const forecastEl = document.getElementById("fin-chart-forecast");
    if (forecastEl && charts.forecast) {
      new Chart(forecastEl, {
        type: "line",
        data: {
          labels: charts.forecast.labels,
          datasets: [
            {
              label: "Forecast MRR",
              data: charts.forecast.values,
              borderColor: "#22d3ee",
              borderDash: [4, 4],
              tension: 0.3,
            },
          ],
        },
        options: chartOpts(),
      });
    }
  }

  function chartOpts(stacked) {
    return {
      responsive: true,
      plugins: { legend: { display: !!stacked } },
      scales: stacked
        ? { x: { stacked: true }, y: { stacked: true, beginAtZero: true } }
        : { y: { beginAtZero: true } },
    };
  }

  async function postAction(payload) {
    const res = await fetch(cfg.apiAction, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": cfg.csrf,
      },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!data.ok) {
      alert(data.error || "Action failed");
      return false;
    }
    return data;
  }

  document.querySelectorAll(".fin-actions").forEach((wrap) => {
    const orgId = wrap.dataset.orgId;
    wrap.querySelectorAll("[data-action]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const action = btn.dataset.action;
        const payload = { action, organizationId: orgId };
        if (action === "extend_trial") payload.days = parseInt(btn.dataset.days || "14", 10);
        const ok = await postAction(payload);
        if (ok) {
          if (action === "generate_invoice" && ok.invoiceNumber) {
            alert(`Invoice ${ok.invoiceNumber} created.`);
          }
          window.location.reload();
        }
      });
    });
  });

  document.querySelectorAll("[data-action='toggle_plan']").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const active = btn.dataset.active === "true";
      const ok = await postAction({
        action: "toggle_plan",
        planId: btn.dataset.planId,
        active: !active,
      });
      if (ok) window.location.reload();
    });
  });

  document.querySelectorAll("[data-action='toggle_addon_catalog']").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const active = btn.dataset.active === "true";
      const ok = await postAction({
        action: "toggle_addon_catalog",
        addonId: btn.dataset.addonId,
        active: !active,
      });
      if (ok) window.location.reload();
    });
  });

  initCharts();
  if (window.lucide) window.lucide.createIcons();
}

if (document.readyState === "complete") {
  initFinancialsDashboard();
} else {
  window.addEventListener("load", initFinancialsDashboard);
}

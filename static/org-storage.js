function initOrgStorageDashboard() {
  "use strict";

  const cfg = window.STORAGE_CONFIG || {};
  const csrf = cfg.csrf;
  const api = cfg.apiAction;

  function chartOpts(stacked) {
    return {
      responsive: true,
      maintainAspectRatio: true,
      plugins: { legend: { display: stacked || false } },
      scales: stacked
        ? { x: { stacked: true }, y: { stacked: true, beginAtZero: true } }
        : { y: { beginAtZero: true } },
    };
  }

  function initCharts() {
    if (typeof Chart === "undefined") return;

    const gaugeEl = document.getElementById("sto-gauge-usage");
    if (gaugeEl && cfg.usagePercent != null) {
      new Chart(gaugeEl, {
        type: "doughnut",
        data: {
          labels: ["Used", "Free"],
          datasets: [
            {
              data: [cfg.usagePercent, Math.max(0, 100 - cfg.usagePercent)],
              backgroundColor: [
                cfg.usagePercent >= 90 ? "#ef4444" : cfg.usagePercent >= 75 ? "#f59e0b" : "#0ea5e9",
                "rgba(148, 163, 184, 0.2)",
              ],
              borderWidth: 0,
            },
          ],
        },
        options: {
          cutout: "78%",
          responsive: true,
          plugins: { legend: { display: false }, tooltip: { enabled: false } },
        },
      });
    }

    const roleEl = document.getElementById("sto-chart-role");
    if (roleEl && cfg.roleChart) {
      new Chart(roleEl, {
        type: "pie",
        data: {
          labels: cfg.roleChart.labels,
          datasets: [
            {
              data: cfg.roleChart.values,
              backgroundColor: ["#6366f1", "#0ea5e9", "#10b981", "#f59e0b"],
            },
          ],
        },
        options: { responsive: true, plugins: { legend: { position: "bottom" } } },
      });
    }

    const catEl = document.getElementById("sto-chart-category");
    if (catEl && cfg.categoryChart) {
      new Chart(catEl, {
        type: "doughnut",
        data: {
          labels: cfg.categoryChart.labels,
          datasets: [
            {
              data: cfg.categoryChart.values,
              backgroundColor: ["#8b5cf6", "#22d3ee", "#f43f5e", "#eab308", "#10b981", "#64748b"],
            },
          ],
        },
        options: { responsive: true, plugins: { legend: { position: "bottom" } } },
      });
    }

    const trendEl = document.getElementById("sto-chart-trend");
    if (trendEl && cfg.uploadTrend) {
      new Chart(trendEl, {
        type: "line",
        data: {
          labels: cfg.uploadTrend.labels,
          datasets: [
            {
              label: "Uploads",
              data: cfg.uploadTrend.uploads,
              borderColor: "#0ea5e9",
              backgroundColor: "rgba(14, 165, 233, 0.12)",
              fill: true,
              tension: 0.35,
              yAxisID: "y",
            },
            {
              label: "Bytes",
              data: cfg.uploadTrend.bytes,
              borderColor: "#6366f1",
              backgroundColor: "rgba(99, 102, 241, 0.08)",
              fill: false,
              tension: 0.35,
              yAxisID: "y1",
            },
          ],
        },
        options: {
          responsive: true,
          interaction: { mode: "index", intersect: false },
          scales: {
            y: { type: "linear", display: true, position: "left", beginAtZero: true },
            y1: { type: "linear", display: false, position: "right", beginAtZero: true },
          },
        },
      });
    }

    const deptEl = document.getElementById("sto-chart-dept");
    if (deptEl && cfg.deptChart && cfg.deptChart.labels.length) {
      new Chart(deptEl, {
        type: "bar",
        data: {
          labels: cfg.deptChart.labels,
          datasets: [
            {
              label: "Storage (bytes)",
              data: cfg.deptChart.values,
              backgroundColor: "rgba(14, 165, 233, 0.65)",
              borderRadius: 6,
            },
          ],
        },
        options: chartOpts(),
      });
    }
  }

  async function postAction(payload) {
    const res = await fetch(api, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf,
      },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Action failed");
    return data;
  }

  function bindActions() {
    document.querySelectorAll("[data-sto-sync]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        btn.disabled = true;
        try {
          await postAction({ action: "sync_org", organizationId: cfg.organizationId });
          window.location.reload();
        } catch (e) {
          alert(e.message);
        } finally {
          btn.disabled = false;
        }
      });
    });

    document.querySelectorAll("[data-sto-restrict]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const userId = btn.dataset.userId;
        const restricted = btn.dataset.restricted !== "true";
        if (!confirm(restricted ? "Restrict uploads for this user?" : "Allow uploads again?")) return;
        try {
          await postAction({ action: "restrict_uploads", userId, restricted });
          window.location.reload();
        } catch (e) {
          alert(e.message);
        }
      });
    });

    document.querySelectorAll("[data-sto-quota]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const userId = btn.dataset.userId;
        const val = prompt("Set quota in MB (0 = org default):", "512");
        if (val == null) return;
        try {
          await postAction({ action: "set_quota", userId, quotaMb: parseInt(val, 10) || 0 });
          window.location.reload();
        } catch (e) {
          alert(e.message);
        }
      });
    });

    document.querySelectorAll("[data-sto-deactivate]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const fileId = btn.dataset.fileId;
        if (!confirm("Mark this file as inactive in the storage index?")) return;
        try {
          await postAction({ action: "deactivate_file", fileId });
          window.location.reload();
        } catch (e) {
          alert(e.message);
        }
      });
    });
  }

  function bindFilters() {
    const roleFilter = document.getElementById("sto-filter-role");
    const deptFilter = document.getElementById("sto-filter-dept");
    const searchInput = document.getElementById("sto-filter-search");
    const rows = document.querySelectorAll("[data-sto-user-row]");

    function applyFilters() {
      const role = roleFilter ? roleFilter.value : "";
      const dept = deptFilter ? deptFilter.value : "";
      const q = searchInput ? searchInput.value.toLowerCase() : "";
      rows.forEach((row) => {
        const matchRole = !role || row.dataset.role === role;
        const matchDept = !dept || row.dataset.dept === dept;
        const matchQ = !q || row.textContent.toLowerCase().includes(q);
        row.hidden = !(matchRole && matchDept && matchQ);
      });
    }

    [roleFilter, deptFilter, searchInput].forEach((el) => {
      if (el) el.addEventListener("input", applyFilters);
      if (el && el.tagName === "SELECT") el.addEventListener("change", applyFilters);
    });
  }

  initCharts();
  bindActions();
  bindFilters();

  if (window.lucide) window.lucide.createIcons();
}

document.addEventListener("DOMContentLoaded", initOrgStorageDashboard);

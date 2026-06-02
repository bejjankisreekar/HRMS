(() => {
  "use strict";

  const COLORS = {
    violet: "#8b5cf6",
    emerald: "#10b981",
    amber: "#f59e0b",
    rose: "#f43f5e",
    cyan: "#06b6d4",
    indigo: "#6366f1",
    pink: "#ec4899",
    slate: "#94a3b8",
  };

  const PIE_PALETTE = [
    COLORS.emerald,
    COLORS.indigo,
    COLORS.amber,
    COLORS.cyan,
    COLORS.rose,
    COLORS.violet,
    COLORS.pink,
    COLORS.slate,
  ];

  const chartInstances = new Map();

  /* ── Utilities ── */

  function readChartsData() {
    const el = document.getElementById("pro-charts-data");
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

  function refreshLucide() {
    if (typeof lucide !== "undefined" && lucide.createIcons) {
      lucide.createIcons();
    }
  }

  function baseOptions(overrides = {}) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: { color: textColor(), boxWidth: 10, font: { size: 11 } },
        },
      },
      ...overrides,
    };
  }

  function lineScales() {
    return {
      x: { grid: { display: false }, ticks: { color: textColor(), font: { size: 10 } } },
      y: {
        beginAtZero: true,
        grid: { color: gridColor() },
        ticks: { color: textColor() },
      },
    };
  }

  function barScales(yOpts = {}) {
    return {
      x: { grid: { display: false }, ticks: { color: textColor(), font: { size: 10 } } },
      y: {
        beginAtZero: true,
        grid: { color: gridColor() },
        ticks: { color: textColor(), ...yOpts },
      },
    };
  }

  function createChart(id, config) {
    const canvas = document.getElementById(id);
    if (!canvas || typeof Chart === "undefined") return null;

    const existing = chartInstances.get(id);
    if (existing) {
      existing.destroy();
    }

    const chart = new Chart(canvas, config);
    chartInstances.set(id, chart);
    return chart;
  }

  /* ── Chart initialization ── */

  function initCharts(data) {
    if (!data || typeof Chart === "undefined") return;

    Chart.defaults.font.family = "Inter, system-ui, sans-serif";

    createChart("pro-chart-growth", {
      type: "line",
      data: {
        labels: data.workforce_growth?.labels || [],
        datasets: [{
          label: "Employees",
          data: data.workforce_growth?.values || [],
          borderColor: COLORS.indigo,
          backgroundColor: "rgba(99,102,241,0.1)",
          fill: true,
          tension: 0.35,
          pointRadius: 3,
        }],
      },
      options: {
        ...baseOptions({ plugins: { legend: { display: false } } }),
        scales: lineScales(),
      },
    });

    createChart("pro-chart-depts", {
      type: "doughnut",
      data: {
        labels: data.departments?.labels || [],
        datasets: [{
          data: data.departments?.values || [],
          backgroundColor: PIE_PALETTE,
          borderWidth: 0,
          hoverOffset: 6,
        }],
      },
      options: {
        ...baseOptions(),
        cutout: "58%",
        plugins: { legend: { position: "bottom" } },
      },
    });

    createChart("pro-chart-hiring", {
      type: "bar",
      data: {
        labels: data.hiring?.labels || [],
        datasets: [{
          label: "New hires",
          data: data.hiring?.values || [],
          backgroundColor: COLORS.violet,
          borderRadius: 6,
          maxBarThickness: 40,
        }],
      },
      options: {
        ...baseOptions({ plugins: { legend: { display: false } } }),
        scales: barScales({ precision: 0 }),
      },
    });

    createChart("pro-chart-att-trend", {
      type: "line",
      data: {
        labels: data.attendance_trend?.labels || [],
        datasets: [{
          label: "Attendance %",
          data: data.attendance_trend?.values || [],
          borderColor: COLORS.emerald,
          backgroundColor: "rgba(16,185,129,0.12)",
          fill: true,
          tension: 0.35,
          pointRadius: 3,
        }],
      },
      options: {
        ...baseOptions({ plugins: { legend: { display: false } } }),
        scales: {
          ...lineScales(),
          y: {
            ...lineScales().y,
            max: 100,
            ticks: {
              color: textColor(),
              callback: (v) => `${v}%`,
            },
          },
        },
      },
    });

    createChart("pro-chart-late", {
      type: "bar",
      data: {
        labels: data.late_arrivals?.labels || [],
        datasets: [{
          label: "Late arrivals",
          data: data.late_arrivals?.values || [],
          backgroundColor: COLORS.amber,
          borderRadius: 6,
          maxBarThickness: 36,
        }],
      },
      options: {
        ...baseOptions({ plugins: { legend: { display: false } } }),
        scales: barScales({ precision: 0 }),
      },
    });

    createChart("pro-chart-shifts", {
      type: "doughnut",
      data: {
        labels: data.shift_distribution?.labels || [],
        datasets: [{
          data: data.shift_distribution?.values || [],
          backgroundColor: PIE_PALETTE,
          borderWidth: 0,
          hoverOffset: 6,
        }],
      },
      options: {
        ...baseOptions(),
        cutout: "58%",
        plugins: { legend: { position: "bottom" } },
      },
    });

    createChart("pro-chart-pay-breakdown", {
      type: "doughnut",
      data: {
        labels: data.payroll_breakdown?.labels || [],
        datasets: [{
          data: data.payroll_breakdown?.values || [],
          backgroundColor: [COLORS.indigo, COLORS.rose, COLORS.emerald, COLORS.amber],
          borderWidth: 0,
          hoverOffset: 6,
        }],
      },
      options: {
        ...baseOptions(),
        cutout: "55%",
        plugins: { legend: { position: "bottom" } },
      },
    });

    createChart("pro-chart-salary", {
      type: "bar",
      data: {
        labels: data.salary_distribution?.labels || [],
        datasets: [{
          label: "Employees",
          data: data.salary_distribution?.values || [],
          backgroundColor: COLORS.cyan,
          borderRadius: 6,
          maxBarThickness: 48,
        }],
      },
      options: {
        ...baseOptions({ plugins: { legend: { display: false } } }),
        scales: barScales({ precision: 0 }),
      },
    });

    createChart("pro-chart-cost", {
      type: "bar",
      data: {
        labels: data.cost_centers?.labels || [],
        datasets: [{
          label: "Headcount",
          data: data.cost_centers?.values || [],
          backgroundColor: COLORS.pink,
          borderRadius: 6,
          maxBarThickness: 40,
        }],
      },
      options: {
        ...baseOptions({ plugins: { legend: { display: false } } }),
        indexAxis: "y",
        scales: {
          x: { beginAtZero: true, grid: { color: gridColor() }, ticks: { color: textColor(), precision: 0 } },
          y: { grid: { display: false }, ticks: { color: textColor(), font: { size: 10 } } },
        },
      },
    });

    createChart("pro-chart-pay-trend", {
      type: "line",
      data: {
        labels: data.payroll_trend?.labels || [],
        datasets: [{
          label: "Net payroll",
          data: data.payroll_trend?.values || [],
          borderColor: COLORS.cyan,
          backgroundColor: "rgba(6,182,212,0.12)",
          fill: true,
          tension: 0.35,
          pointRadius: 3,
        }],
      },
      options: {
        ...baseOptions({ plugins: { legend: { display: false } } }),
        scales: {
          ...lineScales(),
          y: {
            ...lineScales().y,
            ticks: {
              color: textColor(),
              callback: (v) => (v >= 1000 ? `₹${(v / 1000).toFixed(0)}k` : `₹${v}`),
            },
          },
        },
      },
    });

    createChart("pro-chart-productivity", {
      type: "line",
      data: {
        labels: data.productivity?.labels || [],
        datasets: [{
          label: "Productivity index",
          data: data.productivity?.values || [],
          borderColor: COLORS.violet,
          backgroundColor: "rgba(139,92,246,0.12)",
          fill: true,
          tension: 0.35,
          pointRadius: 3,
        }],
      },
      options: {
        ...baseOptions({ plugins: { legend: { display: false } } }),
        scales: {
          ...lineScales(),
          y: { ...lineScales().y, max: 100 },
        },
      },
    });

    createChart("pro-chart-timesheet", {
      type: "bar",
      data: {
        labels: data.timesheet?.labels || [],
        datasets: [{
          label: "Hours logged",
          data: data.timesheet?.values || [],
          backgroundColor: COLORS.indigo,
          borderRadius: 6,
          maxBarThickness: 40,
        }],
      },
      options: {
        ...baseOptions({ plugins: { legend: { display: false } } }),
        scales: barScales(),
      },
    });
  }

  /* ── Heatmap ── */

  function heatmapLevel(pct) {
    if (pct <= 0) return 0;
    if (pct < 40) return 1;
    if (pct < 60) return 2;
    if (pct < 75) return 3;
    if (pct < 90) return 4;
    return 5;
  }

  function renderHeatmap(data) {
    const container = document.getElementById("pro-heatmap");
    if (!container || !data?.heatmap) return;

    const { labels = [], values = [] } = data.heatmap;
    container.innerHTML = "";

    labels.forEach((label, i) => {
      const pct = values[i] ?? 0;
      const cell = document.createElement("div");
      cell.className = `pro-heatmap__cell pro-heatmap__cell--${heatmapLevel(pct)}`;
      cell.setAttribute("role", "gridcell");
      cell.setAttribute("title", `${label}: ${pct}% present`);

      const labelEl = document.createElement("span");
      labelEl.className = "pro-heatmap__label";
      labelEl.textContent = label;

      const valueEl = document.createElement("span");
      valueEl.className = "pro-heatmap__value";
      valueEl.textContent = `${pct}%`;

      cell.append(labelEl, valueEl);
      container.appendChild(cell);
    });
  }

  /* ── Analytics tabs ── */

  function initTabs() {
    const tabs = document.querySelectorAll(".pro-tab");
    const panels = document.querySelectorAll(".pro-tab-panel");
    if (!tabs.length) return;

    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const target = tab.dataset.tab;
        if (!target) return;

        tabs.forEach((t) => {
          t.classList.toggle("pro-tab--active", t === tab);
          t.setAttribute("aria-selected", t === tab ? "true" : "false");
        });

        panels.forEach((panel) => {
          const active = panel.dataset.panel === target;
          panel.classList.toggle("pro-tab-panel--active", active);
          panel.hidden = !active;
        });

        requestAnimationFrame(() => {
          panels.forEach((panel) => {
            if (panel.hidden) return;
            panel.querySelectorAll("canvas").forEach((canvas) => {
              const chart = chartInstances.get(canvas.id);
              if (chart) chart.resize();
            });
          });
          refreshLucide();
        });
      });
    });
  }

  /* ── Employee table ── */

  function initEmployeeTable() {
    const table = document.getElementById("pro-employee-table");
    const searchInput = document.getElementById("pro-employee-search");
    const deptSelect = document.getElementById("pro-employee-dept");
    const exportBtn = document.getElementById("pro-export-csv");
    const selectAll = document.getElementById("pro-select-all");

    if (!table) return;

    const tbody = table.querySelector("tbody");
    const rows = () => [...tbody.querySelectorAll("tr")];
    let sortKey = null;
    let sortDir = 1;

    function dedupeDeptOptions() {
      if (!deptSelect) return;
      const seen = new Set();
      [...deptSelect.options].forEach((opt) => {
        if (!opt.value) return;
        if (seen.has(opt.value)) {
          opt.remove();
        } else {
          seen.add(opt.value);
        }
      });
    }

    function getRowText(row, key) {
      if (key === "name") {
        return row.dataset.name || row.querySelector("strong")?.textContent?.toLowerCase() || "";
      }
      if (key === "department") {
        return row.dataset.dept?.toLowerCase() || "";
      }
      if (key === "designation") {
        const cells = row.querySelectorAll("td");
        return cells[3]?.textContent?.trim().toLowerCase() || "";
      }
      return "";
    }

    function applyFilters() {
      const query = (searchInput?.value || "").trim().toLowerCase();
      const dept = deptSelect?.value || "";

      rows().forEach((row) => {
        const name = row.dataset.name || "";
        const rowDept = row.dataset.dept || "";
        const matchesSearch = !query || name.includes(query) || row.textContent.toLowerCase().includes(query);
        const matchesDept = !dept || rowDept === dept;
        row.classList.toggle("pro-row-hidden", !(matchesSearch && matchesDept));
      });
    }

    function sortRows(key) {
      if (sortKey === key) {
        sortDir *= -1;
      } else {
        sortKey = key;
        sortDir = 1;
      }

      table.querySelectorAll("th[data-sort]").forEach((th) => {
        th.classList.remove("pro-sort-asc", "pro-sort-desc");
        if (th.dataset.sort === sortKey) {
          th.classList.add(sortDir === 1 ? "pro-sort-asc" : "pro-sort-desc");
        }
      });

      const sorted = rows().sort((a, b) => {
        const av = getRowText(a, key);
        const bv = getRowText(b, key);
        if (av < bv) return -1 * sortDir;
        if (av > bv) return 1 * sortDir;
        return 0;
      });

      sorted.forEach((row) => tbody.appendChild(row));
    }

    function exportCsv() {
      const visible = rows().filter((r) => !r.classList.contains("pro-row-hidden"));
      const headers = ["Name", "Email", "Department", "Designation", "Status", "Attendance"];
      const lines = [headers.join(",")];

      visible.forEach((row) => {
        const cells = row.querySelectorAll("td");
        const name = cells[1]?.querySelector("strong")?.textContent?.trim() || "";
        const email = cells[1]?.querySelector(".pro-table-email")?.textContent?.trim() || "";
        const dept = cells[2]?.textContent?.trim() || "";
        const designation = cells[3]?.textContent?.trim() || "";
        const status = cells[4]?.textContent?.trim() || "";
        const attendance = cells[5]?.textContent?.trim() || "";

        const escape = (v) => `"${String(v).replace(/"/g, '""')}"`;
        lines.push([name, email, dept, designation, status, attendance].map(escape).join(","));
      });

      const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `employees-${new Date().toISOString().slice(0, 10)}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    }

    dedupeDeptOptions();

    searchInput?.addEventListener("input", applyFilters);
    deptSelect?.addEventListener("change", applyFilters);

    table.querySelectorAll("th[data-sort]").forEach((th) => {
      th.addEventListener("click", () => sortRows(th.dataset.sort));
    });

    exportBtn?.addEventListener("click", exportCsv);

    selectAll?.addEventListener("change", () => {
      const checked = selectAll.checked;
      rows()
        .filter((r) => !r.classList.contains("pro-row-hidden"))
        .forEach((row) => {
          const cb = row.querySelector(".pro-row-check");
          if (cb) cb.checked = checked;
        });
    });
  }

  /* ── Boot ── */

  function boot() {
    const dash = document.getElementById("pro-dashboard");
    if (!dash) return;

    refreshLucide();

    const data = readChartsData();
    if (data) {
      const runCharts = () => {
        initCharts(data);
        renderHeatmap(data);
        refreshLucide();
      };

      if (typeof Chart !== "undefined") {
        runCharts();
      } else {
        window.addEventListener("load", runCharts, { once: true });
      }
    }

    initTabs();
    initEmployeeTable();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();

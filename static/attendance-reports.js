/* Attendance Reports — AJAX trend / distribution / department + KPI refresh.
   Re-renders charts on granularity change without a full page reload. */
(function () {
  "use strict";
  if (typeof Chart === "undefined") return;

  var isDark = document.documentElement.classList.contains("dark");
  var grid = isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.06)";
  var tick = isDark ? "#94a3b8" : "#64748b";

  var DIST_COLORS = [
    "rgba(16,185,129,0.85)",  // Present
    "rgba(239,68,68,0.85)",   // Absent
    "rgba(249,115,22,0.85)",  // Late
    "rgba(245,158,11,0.85)",  // Half Day
    "rgba(14,165,233,0.85)",  // Leave
    "rgba(124,58,237,0.85)",  // WFH
  ];

  var charts = {};        // id -> Chart instance
  var lastPayload = null; // cache for client-side dept sort

  function pctScale() {
    return {
      y: { beginAtZero: true, max: 100, grid: { color: grid },
           ticks: { color: tick, callback: function (v) { return v + "%"; } } },
      x: { grid: { display: false }, ticks: { color: tick, maxRotation: 45 } },
    };
  }

  function render(id, config) {
    var el = document.getElementById(id);
    if (!el) return;
    if (charts[id]) charts[id].destroy();
    charts[id] = new Chart(el, config);
  }

  function renderTrend(p) {
    render("chartTrendPct", {
      type: "line",
      data: {
        labels: p.trend.labels,
        datasets: [{
          label: "Attendance %",
          data: p.trend.values,
          borderColor: "#7c3aed",
          backgroundColor: "rgba(124,58,237,0.12)",
          fill: true, tension: 0.35, pointRadius: 2,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: { legend: { display: false } },
        scales: pctScale(),
      },
    });
  }

  function renderDistribution(p) {
    render("chartDistribution", {
      type: "bar",
      data: {
        labels: p.distribution.labels,
        datasets: [{
          label: "Records",
          data: p.distribution.values,
          backgroundColor: DIST_COLORS,
          borderRadius: 6,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          y: { beginAtZero: true, grid: { color: grid }, ticks: { color: tick } },
          x: { grid: { display: false }, ticks: { color: tick } },
        },
      },
    });
  }

  function renderDept(p, order) {
    var rows = (p.dept_rate || []).slice();
    if (order === "asc") rows.sort(function (a, b) { return a.pct - b.pct; });
    else rows.sort(function (a, b) { return b.pct - a.pct; });
    render("chartDeptRate", {
      type: "bar",
      data: {
        labels: rows.map(function (r) { return r.name; }),
        datasets: [{
          label: "Attendance %",
          data: rows.map(function (r) { return r.pct; }),
          backgroundColor: "rgba(20,184,166,0.8)",
          borderRadius: 6,
        }],
      },
      options: {
        indexAxis: "y", responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { beginAtZero: true, max: 100, grid: { color: grid },
               ticks: { color: tick, callback: function (v) { return v + "%"; } } },
          y: { grid: { display: false }, ticks: { color: tick } },
        },
      },
    });
  }

  function setText(id, val) {
    var el = document.getElementById(id);
    if (el) el.textContent = val;
  }

  function updateKpis(k) {
    if (!k) return;
    setText("kpiAttendanceRate", (k.attendance_rate || 0) + "%");
    setText("kpiPresentDays", (k.total_present_days || 0).toLocaleString());
    setText("kpiAbsences", (k.total_absences || 0).toLocaleString());
    setText("kpiLate", (k.late_arrivals || 0).toLocaleString());
    setText("kpiLeaveDays", (k.leave_days || 0).toLocaleString());
    setText("kpiEmployees", (k.total_employees || 0).toLocaleString());
  }

  function apply(p) {
    lastPayload = p;
    renderTrend(p);
    renderDistribution(p);
    renderDept(p, currentDeptOrder());
    updateKpis(p.kpis);
  }

  function currentDeptOrder() {
    var sel = document.getElementById("deptSort");
    return sel ? sel.value : "desc";
  }

  function baseQuery() {
    // Current page filters from the querystring, minus paging/granularity/export.
    var params = new URLSearchParams(window.location.search);
    params.delete("page");
    params.delete("export");
    params.delete("view");
    return params;
  }

  function load(granularity) {
    var params = baseQuery();
    if (granularity) params.set("view", granularity);
    var wrap = document.getElementById("trendSection");
    if (wrap) wrap.classList.add("ar-loading");
    fetch("/attendance/reports/data/?" + params.toString(), {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (r) { return r.json(); })
      .then(function (p) { apply(p); })
      .catch(function () { /* keep last render */ })
      .finally(function () { if (wrap) wrap.classList.remove("ar-loading"); });
  }

  document.addEventListener("DOMContentLoaded", function () {
    // Seed from the server-embedded payload to avoid a blank first paint.
    if (window.ATTENDANCE_TREND) {
      try { apply(window.ATTENDANCE_TREND); } catch (e) { /* noop */ }
    }
    var gran = document.getElementById("granularitySelect");
    if (gran) gran.addEventListener("change", function () {
      var hidden = document.getElementById("formViewInput");
      if (hidden) hidden.value = gran.value;  // keep "Apply filters" in sync
      load(gran.value);
    });

    var sort = document.getElementById("deptSort");
    if (sort) sort.addEventListener("change", function () {
      if (lastPayload) renderDept(lastPayload, sort.value);
    });
  });
})();

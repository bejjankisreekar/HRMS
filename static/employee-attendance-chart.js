/* Employee Attendance Chart — vertical bar chart + client-side search/sort + table sort.
   All data is embedded (window.EMP_ATT_ROWS); no extra requests. */
(function () {
  "use strict";
  if (typeof Chart === "undefined") return;

  var ALL = (window.EMP_ATT_ROWS || []).slice();
  var view = ALL.slice();
  var chart = null;

  var isDark = document.documentElement.classList.contains("dark");
  var tick = isDark ? "#94a3b8" : "#64748b";
  var grid = isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.06)";

  function barColor(p) {
    if (p < 75) return "rgba(244,63,94,0.85)";
    if (p > 95) return "rgba(16,185,129,0.85)";
    return "rgba(14,165,233,0.85)";
  }

  function sortRows(rows, mode) {
    var r = rows.slice();
    if (mode === "pct_asc") r.sort(function (a, b) { return a.pct - b.pct; });
    else if (mode === "name") r.sort(function (a, b) { return a.name.localeCompare(b.name); });
    else if (mode === "pct_desc") r.sort(function (a, b) { return b.pct - a.pct; });
    return r;
  }

  function renderChart() {
    var el = document.getElementById("empAttChart");
    if (!el) return;
    if (chart) chart.destroy();
    chart = new Chart(el, {
      type: "bar",
      data: {
        labels: view.map(function (r) { return r.name; }),
        datasets: [{
          label: "Attendance %",
          data: view.map(function (r) { return r.pct; }),
          backgroundColor: view.map(function (r) { return barColor(r.pct); }),
          borderRadius: 4,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: function (items) { return view[items[0].dataIndex].name; },
              label: function (item) {
                var r = view[item.dataIndex];
                return [
                  "Employee ID: " + r.employee_id,
                  "Present: " + r.present + " days",
                  "Absent: " + r.absent + " days",
                  "Leave: " + r.leave + " days",
                  "Attendance: " + r.pct + "%",
                ];
              },
            },
          },
        },
        scales: {
          y: { beginAtZero: true, max: 100, grid: { color: grid },
               ticks: { color: tick, callback: function (v) { return v + "%"; } } },
          x: { grid: { display: false }, ticks: { color: tick, maxRotation: 60, minRotation: 30 } },
        },
      },
    });
  }

  function renderTable() {
    var tb = document.getElementById("empAttTbody");
    if (!tb) return;
    if (!view.length) {
      tb.innerHTML = '<tr><td colspan="7" class="py-16 text-center text-slate-500">No matching employees.</td></tr>';
      return;
    }
    tb.innerHTML = view.map(function (r) {
      var cls = r.pct < 75 ? "text-rose-400" : (r.pct > 95 ? "text-emerald-400" : "text-sky-300");
      return "<tr><td>" + r.employee_id + '</td><td class="font-medium text-slate-900 dark:text-white">' +
        r.name + "</td><td>" + r.department + "</td><td>" + r.present + "</td><td>" + r.absent +
        "</td><td>" + r.leave + '</td><td class="font-semibold ' + cls + '">' + r.pct + "%</td></tr>";
    }).join("");
  }

  function apply() {
    var q = (document.getElementById("empSearch") || {}).value || "";
    q = q.trim().toLowerCase();
    var mode = (document.getElementById("empSort") || {}).value || "pct_desc";
    view = sortRows(ALL.filter(function (r) {
      return !q || r.name.toLowerCase().indexOf(q) >= 0 ||
        (r.employee_id || "").toLowerCase().indexOf(q) >= 0;
    }), mode);
    renderChart();
    renderTable();
  }

  var tableSortState = {};
  function tableSort(key) {
    var asc = !tableSortState[key];
    tableSortState = {}; tableSortState[key] = asc;
    view = view.slice().sort(function (a, b) {
      var x = a[key], y = b[key];
      if (typeof x === "string") { x = x.toLowerCase(); y = y.toLowerCase(); }
      if (x < y) return asc ? -1 : 1;
      if (x > y) return asc ? 1 : -1;
      return 0;
    });
    renderChart();
    renderTable();
  }

  document.addEventListener("DOMContentLoaded", function () {
    renderChart();
    var s = document.getElementById("empSearch");
    if (s) s.addEventListener("input", apply);
    var so = document.getElementById("empSort");
    if (so) so.addEventListener("change", apply);
    document.querySelectorAll("#empAttTable th[data-sort]").forEach(function (th) {
      th.addEventListener("click", function () { tableSort(th.dataset.sort); });
    });
  });
})();

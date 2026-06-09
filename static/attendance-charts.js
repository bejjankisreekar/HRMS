/* Attendance Charts — uses Chart.js (loaded externally) */
(function () {
  'use strict';

  var CHART_ENDPOINT = '/dashboard/attendance/chart-data/';

  var COLORS = {
    present:  { bg: 'rgba(16,185,129,0.85)',  border: 'rgb(16,185,129)',   label: 'Present' },
    absent:   { bg: 'rgba(239,68,68,0.85)',   border: 'rgb(239,68,68)',    label: 'Absent' },
    half_day: { bg: 'rgba(245,158,11,0.85)',  border: 'rgb(245,158,11)',   label: 'Half Day' },
    leave:    { bg: 'rgba(14,165,233,0.85)',  border: 'rgb(14,165,233)',   label: 'Leave' },
    wfh:      { bg: 'rgba(124,58,237,0.85)', border: 'rgb(124,58,237)',  label: 'WFH' },
    unmarked: { bg: 'rgba(148,163,184,0.7)', border: 'rgb(148,163,184)', label: 'Unmarked' },
    hours:    { bg: 'rgba(124,58,237,0.15)', border: 'rgb(124,58,237)',  label: 'Working hours' },
  };

  var isDark = document.documentElement.classList.contains('dark');
  var gridColor = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)';
  var tickColor = isDark ? '#94a3b8' : '#64748b';
  var tooltipBg = isDark ? '#1e293b' : '#fff';
  var tooltipBorder = isDark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.1)';

  function baseChartOptions(extra) {
    return Object.assign({
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 600, easing: 'easeInOutQuart' },
      plugins: {
        legend: {
          position: 'top',
          labels: {
            color: tickColor,
            usePointStyle: true,
            pointStyleWidth: 8,
            boxHeight: 8,
            padding: 16,
            font: { size: 11, weight: '600' },
          },
        },
        tooltip: {
          backgroundColor: tooltipBg,
          borderColor: tooltipBorder,
          borderWidth: 1,
          titleColor: isDark ? '#e2e8f0' : '#0f172a',
          bodyColor: isDark ? '#94a3b8' : '#475569',
          padding: 10,
          cornerRadius: 8,
          displayColors: true,
          boxWidth: 10,
          boxHeight: 10,
        },
      },
      scales: {
        x: {
          grid: { color: gridColor, drawBorder: false },
          ticks: { color: tickColor, font: { size: 10, weight: '500' }, maxRotation: 45 },
        },
        y: {
          grid: { color: gridColor, drawBorder: false },
          ticks: { color: tickColor, font: { size: 10 } },
          beginAtZero: true,
        },
      },
    }, extra || {});
  }

  /* ── Team Donut (day breakdown) ── */
  function renderTeamDonut(canvas, data) {
    if (!canvas || !data) return;
    var ctx = canvas.getContext('2d');
    if (canvas._chartInstance) canvas._chartInstance.destroy();
    canvas._chartInstance = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: data.labels,
        datasets: [{
          data: data.values,
          backgroundColor: [
            COLORS.present.bg, COLORS.absent.bg, COLORS.half_day.bg,
            COLORS.leave.bg, COLORS.wfh.bg, COLORS.unmarked.bg,
          ],
          borderColor: [
            COLORS.present.border, COLORS.absent.border, COLORS.half_day.border,
            COLORS.leave.border, COLORS.wfh.border, COLORS.unmarked.border,
          ],
          borderWidth: 2,
          hoverOffset: 6,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 600 },
        cutout: '68%',
        plugins: {
          legend: {
            position: 'right',
            labels: {
              color: tickColor,
              usePointStyle: true,
              pointStyleWidth: 8,
              boxHeight: 8,
              padding: 12,
              font: { size: 11, weight: '600' },
            },
          },
          tooltip: {
            backgroundColor: tooltipBg,
            borderColor: tooltipBorder,
            borderWidth: 1,
            titleColor: isDark ? '#e2e8f0' : '#0f172a',
            bodyColor: isDark ? '#94a3b8' : '#475569',
            padding: 10,
            cornerRadius: 8,
            callbacks: {
              label: function (ctx) {
                var total = data.total || ctx.dataset.data.reduce(function (a, b) { return a + b; }, 0);
                var pct = total > 0 ? Math.round(ctx.parsed / total * 100) : 0;
                return ' ' + ctx.label + ': ' + ctx.parsed + ' (' + pct + '%)';
              },
            },
          },
        },
      },
    });
  }

  /* ── Team Trend (stacked bar, 7/14/30 days) ── */
  function renderTeamTrend(canvas, data) {
    if (!canvas || !data) return;
    var ctx = canvas.getContext('2d');
    if (canvas._chartInstance) canvas._chartInstance.destroy();
    var opts = baseChartOptions({
      scales: {
        x: {
          stacked: true,
          grid: { color: gridColor, drawBorder: false },
          ticks: { color: tickColor, font: { size: 10 }, maxRotation: 45 },
        },
        y: {
          stacked: true,
          grid: { color: gridColor, drawBorder: false },
          ticks: { color: tickColor, font: { size: 10 }, stepSize: 1 },
          beginAtZero: true,
        },
      },
    });
    canvas._chartInstance = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: data.labels,
        datasets: [
          { label: 'Present',  data: data.present,  backgroundColor: COLORS.present.bg,  borderColor: COLORS.present.border,  borderWidth: 1, stack: 'att', borderRadius: 2 },
          { label: 'Absent',   data: data.absent,   backgroundColor: COLORS.absent.bg,   borderColor: COLORS.absent.border,   borderWidth: 1, stack: 'att', borderRadius: 2 },
          { label: 'Half Day', data: data.half_day, backgroundColor: COLORS.half_day.bg, borderColor: COLORS.half_day.border, borderWidth: 1, stack: 'att', borderRadius: 2 },
          { label: 'Leave',    data: data.leave,    backgroundColor: COLORS.leave.bg,    borderColor: COLORS.leave.border,    borderWidth: 1, stack: 'att', borderRadius: 2 },
          { label: 'WFH',      data: data.wfh,      backgroundColor: COLORS.wfh.bg,      borderColor: COLORS.wfh.border,      borderWidth: 1, stack: 'att', borderRadius: 2 },
        ],
      },
      options: opts,
    });
  }

  /* ── Employee hours + check-in/out (combo bar + line) ── */
  function renderEmployeeChart(canvas, data) {
    if (!canvas || !data) return;
    var ctx = canvas.getContext('2d');
    if (canvas._chartInstance) canvas._chartInstance.destroy();

    function timeToDecimal(t) {
      if (!t) return null;
      var parts = t.split(':');
      return parseFloat(parts[0]) + parseFloat(parts[1]) / 60;
    }

    var checkInDecimal  = (data.check_ins  || []).map(timeToDecimal);
    var checkOutDecimal = (data.check_outs || []).map(timeToDecimal);

    canvas._chartInstance = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: data.labels,
        datasets: [
          {
            type: 'bar',
            label: 'Working hours',
            data: data.hours,
            backgroundColor: COLORS.hours.bg,
            borderColor: COLORS.hours.border,
            borderWidth: 2,
            borderRadius: 4,
            yAxisID: 'yHours',
          },
          {
            type: 'line',
            label: 'Check-in',
            data: checkInDecimal,
            borderColor: COLORS.present.border,
            backgroundColor: 'rgba(16,185,129,0.15)',
            borderWidth: 2,
            pointRadius: 4,
            pointHoverRadius: 6,
            pointBackgroundColor: COLORS.present.border,
            tension: 0.3,
            yAxisID: 'yTime',
            spanGaps: true,
          },
          {
            type: 'line',
            label: 'Check-out',
            data: checkOutDecimal,
            borderColor: COLORS.leave.border,
            backgroundColor: 'rgba(14,165,233,0.15)',
            borderWidth: 2,
            pointRadius: 4,
            pointHoverRadius: 6,
            pointBackgroundColor: COLORS.leave.border,
            tension: 0.3,
            yAxisID: 'yTime',
            spanGaps: true,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 600 },
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: {
            position: 'top',
            labels: {
              color: tickColor,
              usePointStyle: true,
              pointStyleWidth: 8,
              boxHeight: 8,
              padding: 16,
              font: { size: 11, weight: '600' },
            },
          },
          tooltip: {
            backgroundColor: tooltipBg,
            borderColor: tooltipBorder,
            borderWidth: 1,
            titleColor: isDark ? '#e2e8f0' : '#0f172a',
            bodyColor: isDark ? '#94a3b8' : '#475569',
            padding: 10,
            cornerRadius: 8,
            callbacks: {
              label: function (ctx) {
                var v = ctx.parsed.y;
                if (v === null || v === undefined) return null;
                if (ctx.dataset.label === 'Working hours') {
                  var h = Math.floor(v);
                  var m = Math.round((v - h) * 60);
                  return ' Working hours: ' + h + 'h ' + m + 'm';
                }
                var h2 = Math.floor(v);
                var m2 = Math.round((v - h2) * 60);
                return ' ' + ctx.dataset.label + ': ' + String(h2).padStart(2, '0') + ':' + String(m2).padStart(2, '0');
              },
            },
          },
        },
        scales: {
          x: {
            grid: { color: gridColor, drawBorder: false },
            ticks: { color: tickColor, font: { size: 10 }, maxRotation: 45 },
          },
          yHours: {
            type: 'linear',
            position: 'left',
            grid: { color: gridColor, drawBorder: false },
            ticks: { color: tickColor, font: { size: 10 }, callback: function (v) { return v + 'h'; } },
            beginAtZero: true,
            max: 12,
            title: { display: false },
          },
          yTime: {
            type: 'linear',
            position: 'right',
            grid: { display: false },
            ticks: {
              color: tickColor,
              font: { size: 10 },
              callback: function (v) {
                var h = Math.floor(v);
                var m = Math.round((v - h) * 60);
                return String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0');
              },
            },
            min: 6,
            max: 22,
            title: { display: false },
          },
        },
      },
    });
  }

  /* ── Fetch helper ── */
  function fetchChartData(params, callback) {
    var qs = Object.keys(params).map(function (k) {
      return encodeURIComponent(k) + '=' + encodeURIComponent(params[k]);
    }).join('&');
    fetch(CHART_ENDPOINT + '?' + qs, {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
      .then(function (r) { return r.json(); })
      .then(callback)
      .catch(function (err) { console.error('Chart fetch error:', err); });
  }

  /* ── Initialise all charts on the page ── */
  function init() {
    if (typeof Chart === 'undefined') return;

    var selectedDate = (document.getElementById('att-chart-date') || {}).value
      || new Date().toISOString().slice(0, 10);

    /* Team view charts */
    var donutCanvas  = document.getElementById('att-donut-chart');
    var trendCanvas  = document.getElementById('att-trend-chart');
    var empCanvas    = document.getElementById('att-emp-chart');
    var empSelect    = document.getElementById('att-emp-select');
    var daysSelect   = document.getElementById('att-chart-days');
    var trendDays    = document.getElementById('att-trend-days');

    if (donutCanvas) {
      fetchChartData({ type: 'team_day', date: selectedDate }, function (d) {
        renderTeamDonut(donutCanvas, d);
      });
    }

    function loadTrend() {
      if (!trendCanvas) return;
      var days = trendDays ? trendDays.value : '30';
      fetchChartData({ type: 'team_trend', date: selectedDate, days: days }, function (d) {
        renderTeamTrend(trendCanvas, d);
      });
    }
    if (trendCanvas) {
      loadTrend();
      if (trendDays) trendDays.addEventListener('change', loadTrend);
    }

    function loadEmployeeChart() {
      if (!empCanvas) return;
      var days = daysSelect ? daysSelect.value : '30';
      var userId = empSelect ? empSelect.value : '';
      var params = { type: 'employee', date: selectedDate, days: days };
      if (userId) params.user_id = userId;
      fetchChartData(params, function (d) {
        renderEmployeeChart(empCanvas, d);
        var nameEl = document.getElementById('att-emp-chart-name');
        if (nameEl) nameEl.textContent = d.name || '';
      });
    }

    if (empCanvas) {
      loadEmployeeChart();
      if (empSelect)  empSelect.addEventListener('change', loadEmployeeChart);
      if (daysSelect) daysSelect.addEventListener('change', loadEmployeeChart);
    }

    /* Employee self-view chart */
    var selfCanvas = document.getElementById('att-self-chart');
    var selfDays   = document.getElementById('att-self-days');

    function loadSelfChart() {
      if (!selfCanvas) return;
      var days = selfDays ? selfDays.value : '30';
      fetchChartData({ type: 'employee', date: selectedDate, days: days }, function (d) {
        renderEmployeeChart(selfCanvas, d);
      });
    }

    if (selfCanvas) {
      loadSelfChart();
      if (selfDays) selfDays.addEventListener('change', loadSelfChart);
    }
  }

  /* Wait for Chart.js to load */
  if (typeof Chart !== 'undefined') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    document.addEventListener('DOMContentLoaded', function () {
      var s = document.querySelector('script[src*="chart"]');
      if (s) {
        s.addEventListener('load', init);
      }
    });
    window.addEventListener('load', init);
  }
})();

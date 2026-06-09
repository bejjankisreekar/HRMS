/* Unified Analytics Dashboard — Chart.js 4 */
(function () {
  'use strict';

  var API = '/dashboard/analytics/data/';
  var dark = document.documentElement.classList.contains('dark');

  /* ── Palette ── */
  var C = {
    violet:  { bg: 'rgba(124,58,237,0.8)',  line: 'rgb(124,58,237)',  fill: 'rgba(124,58,237,0.12)' },
    emerald: { bg: 'rgba(16,185,129,0.8)',  line: 'rgb(16,185,129)',  fill: 'rgba(16,185,129,0.12)' },
    rose:    { bg: 'rgba(239,68,68,0.8)',   line: 'rgb(239,68,68)',   fill: 'rgba(239,68,68,0.12)' },
    amber:   { bg: 'rgba(245,158,11,0.8)',  line: 'rgb(245,158,11)',  fill: 'rgba(245,158,11,0.12)' },
    sky:     { bg: 'rgba(14,165,233,0.8)',  line: 'rgb(14,165,233)',  fill: 'rgba(14,165,233,0.12)' },
    indigo:  { bg: 'rgba(99,102,241,0.8)',  line: 'rgb(99,102,241)',  fill: 'rgba(99,102,241,0.12)' },
    slate:   { bg: 'rgba(148,163,184,0.7)', line: 'rgb(148,163,184)', fill: 'rgba(148,163,184,0.08)' },
    pink:    { bg: 'rgba(236,72,153,0.8)',  line: 'rgb(236,72,153)',  fill: 'rgba(236,72,153,0.12)' },
    teal:    { bg: 'rgba(20,184,166,0.8)',  line: 'rgb(20,184,166)',  fill: 'rgba(20,184,166,0.12)' },
    orange:  { bg: 'rgba(249,115,22,0.8)',  line: 'rgb(249,115,22)',  fill: 'rgba(249,115,22,0.12)' },
  };

  var MULTI_BG = [C.emerald.bg, C.rose.bg, C.amber.bg, C.sky.bg, C.violet.bg, C.slate.bg,
                  C.pink.bg, C.teal.bg, C.orange.bg, C.indigo.bg];
  var MULTI_LINE = [C.emerald.line, C.rose.line, C.amber.line, C.sky.line, C.violet.line,
                    C.slate.line, C.pink.line, C.teal.line, C.orange.line, C.indigo.line];

  /* ── Theme tokens ── */
  var grid   = dark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.06)';
  var tick   = dark ? '#94a3b8' : '#64748b';
  var ttBg   = dark ? '#1e293b' : '#ffffff';
  var ttBdr  = dark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.08)';
  var ttTitle = dark ? '#e2e8f0' : '#0f172a';
  var ttBody  = dark ? '#94a3b8' : '#475569';

  /* ── Shared defaults ── */
  function baseOpts(extra) {
    var base = {
      responsive: true, maintainAspectRatio: false,
      animation: { duration: 500, easing: 'easeInOutQuart' },
      plugins: {
        legend: { position: 'top', labels: { color: tick, usePointStyle: true, pointStyleWidth: 8,
          boxHeight: 8, padding: 14, font: { size: 11, weight: '600' } } },
        tooltip: { backgroundColor: ttBg, borderColor: ttBdr, borderWidth: 1,
          titleColor: ttTitle, bodyColor: ttBody, padding: 10, cornerRadius: 8,
          displayColors: true, boxWidth: 10, boxHeight: 10 },
      },
    };
    return Object.assign(base, extra || {});
  }

  function axisScale(overrides) {
    return Object.assign({
      grid: { color: grid, drawBorder: false },
      ticks: { color: tick, font: { size: 10 } },
      border: { display: false },
    }, overrides || {});
  }

  /* ── Chart factory ── */
  function make(id, type, data, opts) {
    var canvas = document.getElementById(id);
    if (!canvas) return;
    if (canvas._ci) canvas._ci.destroy();
    canvas._ci = new Chart(canvas.getContext('2d'), { type, data, options: opts });
    return canvas._ci;
  }

  /* ── Stacked bar ── */
  function stackedBar(id, labels, datasets) {
    make(id, 'bar', { labels, datasets }, baseOpts({
      scales: {
        x: Object.assign(axisScale(), { stacked: true, ticks: { color: tick, font: { size: 10 }, maxRotation: 45 } }),
        y: Object.assign(axisScale({ beginAtZero: true, ticks: { color: tick, font: { size: 10 }, stepSize: 1 } }), { stacked: true }),
      },
      plugins: Object.assign(baseOpts().plugins, { legend: Object.assign(baseOpts().plugins.legend, { position: 'bottom' }) }),
    }));
  }

  /* ── Donut ── */
  function donut(id, labels, values, colors) {
    make(id, 'doughnut', {
      labels,
      datasets: [{ data: values, backgroundColor: colors || MULTI_BG,
        borderColor: '#fff', borderWidth: 2, hoverOffset: 6 }],
    }, Object.assign(baseOpts({ cutout: '65%' }), {
      plugins: Object.assign(baseOpts().plugins, {
        legend: { position: 'right', labels: { color: tick, usePointStyle: true,
          pointStyleWidth: 8, boxHeight: 8, padding: 10, font: { size: 11, weight: '600' } } },
      }),
    }));
  }

  /* ── Line ── */
  function line(id, labels, datasets) {
    make(id, 'line', { labels, datasets }, baseOpts({
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: Object.assign(axisScale(), { ticks: { color: tick, font: { size: 10 }, maxRotation: 45 } }),
        y: Object.assign(axisScale({ beginAtZero: true })),
      },
    }));
  }

  /* ── Horizontal bar ── */
  function hbar(id, labels, values, color) {
    make(id, 'bar', {
      labels,
      datasets: [{ data: values, backgroundColor: color || C.violet.bg,
        borderColor: color ? color.replace('0.8','1') : C.violet.line,
        borderWidth: 1, borderRadius: 4 }],
    }, baseOpts({
      indexAxis: 'y',
      plugins: Object.assign(baseOpts().plugins, { legend: { display: false } }),
      scales: {
        x: Object.assign(axisScale({ beginAtZero: true })),
        y: Object.assign(axisScale(), { ticks: { color: tick, font: { size: 11, weight: '500' } } }),
      },
    }));
  }

  /* ── Grouped bar ── */
  function groupedBar(id, labels, datasets) {
    make(id, 'bar', { labels, datasets }, baseOpts({
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: Object.assign(axisScale(), { ticks: { color: tick, font: { size: 10 }, maxRotation: 45 } }),
        y: Object.assign(axisScale({ beginAtZero: true })),
      },
    }));
  }

  /* ── Fetch ── */
  function load(params, cb) {
    var qs = Object.entries(params).map(([k,v]) => k+'='+encodeURIComponent(v)).join('&');
    fetch(API + '?' + qs, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(r => r.json()).then(cb)
      .catch(e => console.error('Analytics fetch error', e));
  }

  /* ────────────────────────────────────────────────────────────────────────────
     ATTENDANCE SECTION
  ──────────────────────────────────────────────────────────────────────────── */
  function loadAttendance(days) {
    load({ section: 'attendance', days: days || 30 }, function(d) {
      var t = d.trend;
      stackedBar('an-att-trend', t.labels, [
        { label:'Present',  data:t.present,  backgroundColor:C.emerald.bg, borderColor:C.emerald.line, borderWidth:1, borderRadius:3, stack:'s' },
        { label:'Absent',   data:t.absent,   backgroundColor:C.rose.bg,    borderColor:C.rose.line,    borderWidth:1, borderRadius:3, stack:'s' },
        { label:'Half Day', data:t.half_day, backgroundColor:C.amber.bg,   borderColor:C.amber.line,   borderWidth:1, borderRadius:3, stack:'s' },
        { label:'Leave',    data:t.leave,    backgroundColor:C.sky.bg,     borderColor:C.sky.line,     borderWidth:1, borderRadius:3, stack:'s' },
        { label:'WFH',      data:t.wfh,      backgroundColor:C.violet.bg,  borderColor:C.violet.line,  borderWidth:1, borderRadius:3, stack:'s' },
      ]);

      donut('an-att-donut', d.donut.labels, d.donut.values,
        [C.emerald.bg, C.rose.bg, C.amber.bg, C.sky.bg, C.violet.bg, C.slate.bg]);

      var h = d.avg_hours;
      line('an-att-hours', h.labels, [{
        label: 'Avg working hours', data: h.values,
        borderColor: C.violet.line, backgroundColor: C.violet.fill,
        borderWidth: 2, pointRadius: 3, tension: 0.4, fill: true, spanGaps: true,
      }]);

      hbar('an-att-dept', d.dept_rate.labels, d.dept_rate.values, C.emerald.bg);
    });
  }

  /* ────────────────────────────────────────────────────────────────────────────
     PAYROLL SECTION
  ──────────────────────────────────────────────────────────────────────────── */
  function loadPayroll(months) {
    load({ section: 'payroll', months: months || 12 }, function(d) {
      var t = d.trend;
      line('an-pay-trend', t.labels, [
        { label:'Gross', data:t.gross, borderColor:C.violet.line, backgroundColor:C.violet.fill,
          borderWidth:2, pointRadius:3, tension:0.4, fill:false, spanGaps:true },
        { label:'Net', data:t.net, borderColor:C.emerald.line, backgroundColor:C.emerald.fill,
          borderWidth:2, pointRadius:3, tension:0.4, fill:false, spanGaps:true },
        { label:'Deductions', data:t.deductions, borderColor:C.rose.line, backgroundColor:C.rose.fill,
          borderWidth:2, pointRadius:3, tension:0.4, fill:false, spanGaps:true },
      ]);

      make('an-pay-headcount', 'bar', { labels:t.labels, datasets:[{
        label:'Employees paid', data:t.employee_count,
        backgroundColor:C.sky.bg, borderColor:C.sky.line, borderWidth:1, borderRadius:4, spanGaps:true,
      }]}, baseOpts({
        scales: {
          x: Object.assign(axisScale(), { ticks:{color:tick,font:{size:10},maxRotation:45} }),
          y: Object.assign(axisScale({beginAtZero:true,ticks:{color:tick,font:{size:10},stepSize:1}})),
        },
        plugins: Object.assign(baseOpts().plugins, { legend:{display:false} }),
      }));

      if (d.run_status.labels.length) {
        donut('an-pay-status', d.run_status.labels, d.run_status.values);
      }

      if (d.payment_status.labels.length) {
        var el = document.getElementById('an-pay-period');
        if (el) el.textContent = d.payment_status.period;
        donut('an-pay-payment', d.payment_status.labels, d.payment_status.values,
          [C.emerald.bg, C.sky.bg, C.rose.bg, C.amber.bg]);
      }
    });
  }

  /* ────────────────────────────────────────────────────────────────────────────
     WORKFORCE SECTION
  ──────────────────────────────────────────────────────────────────────────── */
  function loadWorkforce() {
    load({ section: 'workforce' }, function(d) {
      hbar('an-wf-dept', d.dept_headcount.labels, d.dept_headcount.values, C.violet.bg);

      donut('an-wf-emptype', d.emp_type.labels, d.emp_type.values);
      donut('an-wf-gender',  d.gender.labels,   d.gender.values,
        [C.sky.bg, C.pink.bg, C.teal.bg, C.slate.bg]);
      donut('an-wf-workmode', d.work_mode.labels, d.work_mode.values,
        [C.emerald.bg, C.violet.bg, C.amber.bg]);

      line('an-wf-joiners', d.joiners.labels, [{
        label: 'New joiners', data: d.joiners.values,
        borderColor: C.indigo.line, backgroundColor: C.indigo.fill,
        borderWidth: 2, pointRadius: 4, tension: 0.3, fill: true,
      }]);

      if (d.leave_usage.labels.length) {
        groupedBar('an-wf-leave', d.leave_usage.labels, [
          { label:'Approved', data:d.leave_usage.approved, backgroundColor:C.emerald.bg, borderColor:C.emerald.line, borderWidth:1, borderRadius:4 },
          { label:'Pending',  data:d.leave_usage.pending,  backgroundColor:C.amber.bg,   borderColor:C.amber.line,   borderWidth:1, borderRadius:4 },
        ]);
      }

      donut('an-wf-empstatus', d.emp_status.labels, d.emp_status.values,
        [C.emerald.bg, C.slate.bg, C.amber.bg, C.rose.bg, C.orange.bg]);

      var t = d.totals;
      ['an-wf-total','an-wf-active','an-wf-inactive'].forEach(function(id) {
        var el = document.getElementById(id);
        if (!el) return;
        el.textContent = id==='an-wf-total' ? t.total : id==='an-wf-active' ? t.active : t.inactive;
      });
    });
  }

  /* ── Section tab switching ── */
  function initTabs() {
    var btns    = document.querySelectorAll('[data-an-tab]');
    var sections = document.querySelectorAll('[data-an-section]');
    var loaded  = {};

    function activate(name) {
      btns.forEach(function(b) {
        b.classList.toggle('an-tab--active', b.dataset.anTab === name);
      });
      sections.forEach(function(s) {
        s.style.display = s.dataset.anSection === name ? '' : 'none';
      });
      if (loaded[name]) return;
      loaded[name] = true;
      if (name === 'attendance') loadAttendance(getDays());
      if (name === 'payroll')    loadPayroll(getMonths());
      if (name === 'workforce')  loadWorkforce();
    }

    btns.forEach(function(b) {
      b.addEventListener('click', function() { activate(b.dataset.anTab); });
    });

    var daysSel   = document.getElementById('an-att-days');
    var monthsSel = document.getElementById('an-pay-months');
    if (daysSel)   daysSel.addEventListener('change',   function() { loaded['attendance']=false; loadAttendance(getDays()); });
    if (monthsSel) monthsSel.addEventListener('change', function() { loaded['payroll']=false;    loadPayroll(getMonths()); });

    // Open first tab
    var first = btns[0];
    if (first) activate(first.dataset.anTab);
  }

  function getDays()   { var s=document.getElementById('an-att-days');   return s?s.value:30; }
  function getMonths() { var s=document.getElementById('an-pay-months'); return s?s.value:12; }

  /* ── Boot ── */
  document.addEventListener('DOMContentLoaded', function() {
    if (typeof Chart === 'undefined') return;
    initTabs();
  });
})();

/* ==========================================================================
   HR Analytics — Chart.js 4 rendering + lazy per-section hydration.
   Sections are fetched on first activation and cached until Refresh/Apply.
   ========================================================================== */
(function () {
  'use strict';

  var root = document.querySelector('[data-hra]');
  if (!root) return;

  var boot = {};
  try { boot = JSON.parse(document.getElementById('hra-boot').textContent); } catch (e) { boot = {}; }
  var ENDPOINT = boot.endpoint || '/dashboard/hr-analytics/data/';
  var CURRENCY = boot.currency || 'INR';

  var dark = document.documentElement.classList.contains('dark');
  var cache = {};
  var charts = {};
  var activeSection = 'overview';
  var scorecardSort = { key: 'headcount', dir: 'desc' };

  /* ── palette ─────────────────────────────────────────────────────────── */

  var P = {
    violet: '#7c3aed', indigo: '#6366f1', sky: '#0ea5e9', teal: '#14b8a6',
    emerald: '#10b981', amber: '#f59e0b', rose: '#f43f5e', pink: '#ec4899',
    slate: '#94a3b8', orange: '#f97316', lime: '#84cc16', cyan: '#06b6d4'
  };
  var SERIES = [P.violet, P.emerald, P.amber, P.sky, P.rose, P.indigo,
                P.teal, P.pink, P.orange, P.lime, P.cyan, P.slate];

  function alpha(hex, a) {
    var n = parseInt(hex.slice(1), 16);
    return 'rgba(' + [(n >> 16) & 255, (n >> 8) & 255, n & 255].join(',') + ',' + a + ')';
  }

  var grid = dark ? 'rgba(148,163,184,0.14)' : 'rgba(15,23,42,0.07)';
  var tick = dark ? '#94a3b8' : '#64748b';
  var ttBg = dark ? '#111c33' : '#ffffff';
  var ttBorder = dark ? 'rgba(148,163,184,0.22)' : 'rgba(15,23,42,0.1)';
  var ttTitle = dark ? '#e8edf7' : '#0f172a';
  var ttBody = dark ? '#b3bfd4' : '#475569';

  /* ── formatting ──────────────────────────────────────────────────────── */

  var SYMBOL = { INR: '₹', USD: '$', EUR: '€', GBP: '£', AED: 'AED ' }[CURRENCY] || (CURRENCY + ' ');

  function num(v, digits) {
    if (v === null || v === undefined || isNaN(v)) return '—';
    return Number(v).toLocaleString(undefined, {
      minimumFractionDigits: digits || 0, maximumFractionDigits: digits || 0
    });
  }

  function money(v, compact) {
    if (v === null || v === undefined || isNaN(v)) return '—';
    var n = Number(v);
    if (compact !== false && Math.abs(n) >= 1e7) return SYMBOL + (n / 1e7).toFixed(2) + ' Cr';
    if (compact !== false && Math.abs(n) >= 1e5) return SYMBOL + (n / 1e5).toFixed(2) + ' L';
    return SYMBOL + num(Math.round(n));
  }

  function pct(v, digits) {
    if (v === null || v === undefined || isNaN(v)) return '—';
    return Number(v).toFixed(digits === undefined ? 1 : digits) + '%';
  }

  function formatValue(value, fmt) {
    if (fmt === 'currency') return money(value);
    if (fmt === 'pct') return pct(value);
    if (fmt === 'ratio') return num(value, 1);
    return num(value);
  }

  /* ── chart helpers ───────────────────────────────────────────────────── */

  function hasData(values) {
    return Array.isArray(values) && values.some(function (v) { return v !== null && v !== undefined && v !== 0; });
  }

  function baseOptions(extra) {
    return Object.assign({
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      animation: { duration: 450, easing: 'easeOutQuart' },
      plugins: {
        legend: {
          position: 'top', align: 'end',
          labels: {
            color: tick, usePointStyle: true, pointStyle: 'circle',
            boxWidth: 8, boxHeight: 8, padding: 14,
            font: { size: 11, weight: '600' }
          }
        },
        tooltip: {
          backgroundColor: ttBg, borderColor: ttBorder, borderWidth: 1,
          titleColor: ttTitle, bodyColor: ttBody, padding: 11, cornerRadius: 10,
          usePointStyle: true, boxPadding: 5,
          titleFont: { size: 12, weight: '700' }, bodyFont: { size: 11.5 }
        }
      }
    }, extra || {});
  }

  function axis(overrides) {
    return Object.assign({
      grid: { color: grid, drawTicks: false },
      border: { display: false },
      ticks: { color: tick, font: { size: 10.5 }, padding: 6 }
    }, overrides || {});
  }

  function canvasFor(key) {
    return root.querySelector('[data-hra-chart="' + key + '"]');
  }

  function draw(key, type, data, options) {
    var canvas = canvasFor(key);
    if (!canvas) return null;
    var wrap = canvas.parentElement;
    var placeholder = wrap.querySelector('.hra-empty');
    if (placeholder) placeholder.remove();
    canvas.style.display = '';
    if (charts[key]) { charts[key].destroy(); delete charts[key]; }
    charts[key] = new Chart(canvas.getContext('2d'), { type: type, data: data, options: options });
    return charts[key];
  }

  function empty(key, message, hint) {
    var canvas = canvasFor(key);
    if (!canvas) return;
    if (charts[key]) { charts[key].destroy(); delete charts[key]; }
    var wrap = canvas.parentElement;
    canvas.style.display = 'none';
    if (wrap.querySelector('.hra-empty')) return;
    var node = document.createElement('div');
    node.className = 'hra-empty';
    node.innerHTML =
      '<span class="hra-empty__icon"><i data-lucide="chart-column" class="h-4 w-4"></i></span>' +
      '<span class="hra-empty__text">' + (message || 'No data for this period') + '</span>' +
      (hint ? '<span class="hra-empty__hint">' + hint + '</span>' : '');
    wrap.appendChild(node);
    refreshIcons();
  }

  /** Draw when there is something to show, otherwise a friendly empty state. */
  function drawOrEmpty(key, values, fn, message, hint) {
    if (!hasData(values)) { empty(key, message, hint); return; }
    fn();
  }

  function barDataset(label, values, color, extra) {
    return Object.assign({
      label: label, data: values, backgroundColor: alpha(color, 0.82),
      hoverBackgroundColor: color, borderRadius: 6, borderSkipped: false,
      maxBarThickness: 34
    }, extra || {});
  }

  function lineDataset(label, values, color, extra) {
    return Object.assign({
      label: label, data: values, borderColor: color, backgroundColor: alpha(color, 0.14),
      borderWidth: 2.5, tension: 0.35, fill: true, pointRadius: 0, pointHoverRadius: 5,
      pointBackgroundColor: color, pointBorderColor: '#fff', pointBorderWidth: 2, spanGaps: true
    }, extra || {});
  }

  function doughnut(key, labels, values, colors) {
    drawOrEmpty(key, values, function () {
      draw(key, 'doughnut', {
        labels: labels,
        datasets: [{
          data: values,
          backgroundColor: (colors || SERIES).map(function (c) { return alpha(c, 0.88); }),
          borderColor: dark ? '#0f172a' : '#ffffff',
          borderWidth: 2, hoverOffset: 6
        }]
      }, baseOptions({
        cutout: '62%',
        interaction: { mode: 'nearest', intersect: true },
        plugins: {
          legend: {
            position: 'bottom',
            labels: {
              color: tick, usePointStyle: true, pointStyle: 'circle',
              boxWidth: 8, boxHeight: 8, padding: 12, font: { size: 11, weight: '600' }
            }
          },
          tooltip: {
            backgroundColor: ttBg, borderColor: ttBorder, borderWidth: 1,
            titleColor: ttTitle, bodyColor: ttBody, padding: 11, cornerRadius: 10,
            callbacks: {
              label: function (ctx) {
                var total = ctx.dataset.data.reduce(function (a, b) { return a + (b || 0); }, 0);
                return ' ' + ctx.label + ': ' + num(ctx.parsed) + ' (' + pct(total ? ctx.parsed / total * 100 : 0) + ')';
              }
            }
          }
        }
      }));
    });
  }

  function horizontalBar(key, labels, values, color, valueFormatter) {
    drawOrEmpty(key, values, function () {
      draw(key, 'bar', {
        labels: labels,
        datasets: [barDataset('', values, color, { maxBarThickness: 22 })]
      }, baseOptions({
        indexAxis: 'y',
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: ttBg, borderColor: ttBorder, borderWidth: 1,
            titleColor: ttTitle, bodyColor: ttBody, padding: 11, cornerRadius: 10,
            callbacks: {
              label: function (ctx) { return ' ' + (valueFormatter ? valueFormatter(ctx.parsed.x) : num(ctx.parsed.x)); }
            }
          }
        },
        scales: {
          x: axis({ ticks: { color: tick, font: { size: 10.5 },
            callback: function (v) { return valueFormatter ? valueFormatter(v) : num(v); } } }),
          y: axis({ grid: { display: false } })
        }
      }));
    });
  }

  function refreshIcons() {
    if (window.lucide && typeof window.lucide.createIcons === 'function') {
      window.lucide.createIcons();
    }
  }

  /* ── data fetching ───────────────────────────────────────────────────── */

  function currentQuery() {
    var form = root.querySelector('[data-hra-filters]');
    var params = new URLSearchParams(new FormData(form));
    // Drop empty values so the URL stays readable.
    var clean = new URLSearchParams();
    params.forEach(function (value, key) { if (value) clean.append(key, value); });
    return clean;
  }

  function setBusy(section, busy) {
    root.querySelectorAll('[data-hra-section="' + section + '"] .hra-card').forEach(function (card) {
      card.dataset.loading = busy ? 'true' : 'false';
      var existing = card.querySelector('.hra-loading');
      if (busy && !existing) {
        var wrap = card.querySelector('.hra-chart');
        if (wrap) {
          var node = document.createElement('div');
          node.className = 'hra-loading';
          node.innerHTML = '<span class="hra-spinner"></span>';
          wrap.appendChild(node);
        }
      } else if (!busy && existing) {
        existing.remove();
      }
    });
  }

  function load(section, force) {
    if (cache[section] && !force) return Promise.resolve(cache[section]);
    var params = currentQuery();
    params.set('section', section);
    if (force) params.set('refresh', '1');
    setBusy(section, true);
    return fetch(ENDPOINT + '?' + params.toString(), {
      headers: { 'X-Requested-With': 'XMLHttpRequest' }, credentials: 'same-origin'
    })
      .then(function (r) {
        if (!r.ok) throw new Error('Request failed with status ' + r.status);
        return r.json();
      })
      .then(function (payload) {
        cache[section] = payload.data;
        return payload.data;
      })
      .finally(function () { setBusy(section, false); });
  }

  function showError(section, message) {
    var host = root.querySelector('[data-hra-section="' + section + '"]');
    if (!host) return;
    var existing = host.querySelector('.hra-error');
    if (existing) existing.remove();
    var node = document.createElement('div');
    node.className = 'hra-error';
    node.textContent = 'Could not load this section — ' + message;
    host.prepend(node);
  }

  function render(section, force) {
    var host = root.querySelector('[data-hra-section="' + section + '"]');
    if (host) {
      var stale = host.querySelector('.hra-error');
      if (stale) stale.remove();
    }
    return load(section, force)
      .then(function (data) {
        (RENDERERS[section] || function () {})(data);
        refreshIcons();
      })
      .catch(function (err) { showError(section, err.message || 'unknown error'); });
  }

  /* ── small DOM helpers ───────────────────────────────────────────────── */

  function stat(key, value) {
    root.querySelectorAll('[data-hra-stat="' + key + '"]').forEach(function (el) { el.textContent = value; });
  }

  function badge(key, value) {
    var el = root.querySelector('[data-hra-badge="' + key + '"]');
    if (el) el.textContent = value;
  }

  function legend(key, labels, values, colors) {
    var host = root.querySelector('[data-hra-legend="' + key + '"]');
    if (!host) return;
    var total = values.reduce(function (a, b) { return a + (b || 0); }, 0);
    host.innerHTML = labels.map(function (label, i) {
      return '<div class="hra-legend__row">' +
        '<span class="hra-legend__dot" style="background:' + (colors || SERIES)[i % SERIES.length] + '"></span>' +
        '<span class="hra-legend__label">' + escapeHtml(label) + '</span>' +
        '<span class="hra-legend__value">' + num(values[i]) + ' · ' + pct(total ? values[i] / total * 100 : 0, 0) + '</span>' +
        '</div>';
    }).join('');
  }

  function escapeHtml(value) {
    return String(value === null || value === undefined ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function heat(value, goodAbove, badBelow, formatter) {
    var cls = 'hra-heat--warn';
    if (value >= goodAbove) cls = 'hra-heat--good';
    else if (value < badBelow) cls = 'hra-heat--bad';
    return '<span class="hra-heat ' + cls + '">' + (formatter ? formatter(value) : pct(value)) + '</span>';
  }

  function heatInverse(value, goodBelow, badAbove, formatter) {
    var cls = 'hra-heat--warn';
    if (value <= goodBelow) cls = 'hra-heat--good';
    else if (value > badAbove) cls = 'hra-heat--bad';
    return '<span class="hra-heat ' + cls + '">' + (formatter ? formatter(value) : pct(value)) + '</span>';
  }

  /* ── section renderers ───────────────────────────────────────────────── */

  function renderKpis(kpis) {
    var host = root.querySelector('[data-hra-kpis]');
    if (!host) return;
    var tones = {
      violet: P.violet, rose: P.rose, emerald: P.emerald, sky: P.sky,
      amber: P.amber, indigo: P.indigo, pink: P.pink, teal: P.teal
    };
    host.innerHTML = kpis.map(function (k) {
      var deltaHtml = '';
      if (k.delta !== null && k.delta !== undefined) {
        var rising = k.delta > 0;
        var good = k.invert ? !rising : rising;
        var cls = k.delta === 0 ? 'flat' : (good ? 'up' : 'down');
        var arrow = k.delta === 0 ? '→' : (rising ? '▲' : '▼');
        deltaHtml = '<span class="hra-delta hra-delta--' + cls + '">' + arrow + ' ' +
          Math.abs(k.delta).toFixed(1) + '%</span>';
      }
      return '<article class="hra-kpi" style="--kpi-accent:' + (tones[k.tone] || P.violet) + '">' +
        '<div class="hra-kpi__top">' +
          '<span class="hra-kpi__label">' + escapeHtml(k.label) + '</span>' +
          '<span class="hra-kpi__icon"><i data-lucide="' + escapeHtml(k.icon || 'activity') + '" class="h-4 w-4"></i></span>' +
        '</div>' +
        '<div class="hra-kpi__value">' + formatValue(k.value, k.format) + '</div>' +
        '<div class="hra-kpi__foot">' + deltaHtml +
          '<span class="hra-kpi__hint">' + escapeHtml(k.hint || '') + '</span>' +
        '</div>' +
      '</article>';
    }).join('');
    refreshIcons();
  }

  function renderInsights(items) {
    var host = root.querySelector('[data-hra-insights]');
    if (!host) return;
    host.innerHTML = (items || []).map(function (item) {
      return '<article class="hra-insight" data-tone="' + escapeHtml(item.tone) + '">' +
        '<span class="hra-insight__icon"><i data-lucide="' + escapeHtml(item.icon) + '" class="h-4 w-4"></i></span>' +
        '<div><p class="hra-insight__title">' + escapeHtml(item.title) + '</p>' +
        '<p class="hra-insight__body">' + escapeHtml(item.body) + '</p></div>' +
      '</article>';
    }).join('');
  }

  var RENDERERS = {

    overview: function (d) {
      renderKpis(d.kpis || []);
      renderInsights(d.insights || []);

      var t = d.headcount_trend || {};
      var totals = d.totals || {};
      var el = root.querySelector('[data-hra-hero-headcount]');
      if (el) el.textContent = num(totals.headcount);
      var el2 = root.querySelector('[data-hra-hero-depts]');
      if (el2) el2.textContent = num(totals.departments);
      badge('ov-net', (totals.joiners - totals.leavers >= 0 ? '+' : '') + (totals.joiners - totals.leavers) + ' net');

      drawOrEmpty('ov-headcount', (t.headcount || []).concat(t.joiners || []), function () {
        draw('ov-headcount', 'bar', {
          labels: t.labels,
          datasets: [
            barDataset('Joiners', t.joiners, P.emerald, { stack: 'flow', order: 2 }),
            barDataset('Exits', t.leavers, P.rose, { stack: 'flow', order: 2 }),
            Object.assign(lineDataset('Headcount', t.headcount, P.violet, { fill: false, order: 1 }),
              { type: 'line', yAxisID: 'y1', borderWidth: 3 })
          ]
        }, baseOptions({
          scales: {
            x: axis({ stacked: true, grid: { display: false } }),
            y: axis({ stacked: true, title: { display: true, text: 'Joiners / exits', color: tick, font: { size: 10 } } }),
            y1: axis({
              position: 'right', grid: { display: false }, beginAtZero: true,
              title: { display: true, text: 'Headcount', color: tick, font: { size: 10 } }
            })
          },
          plugins: {
            legend: baseOptions().plugins.legend,
            tooltip: Object.assign({}, baseOptions().plugins.tooltip, {
              callbacks: {
                label: function (ctx) { return ' ' + ctx.dataset.label + ': ' + num(Math.abs(ctx.parsed.y)); }
              }
            })
          }
        }));
      });

      var tenure = d.tenure || {};
      stat('ov-avg-tenure', (tenure.average_years || 0).toFixed(1) + ' yrs');
      stat('ov-med-tenure', (tenure.median_years || 0).toFixed(1) + ' yrs');
      stat('ov-notice', num(totals.on_notice));
      drawOrEmpty('ov-tenure', tenure.values, function () {
        draw('ov-tenure', 'bar', {
          labels: tenure.labels,
          datasets: [barDataset('Employees', tenure.values, P.indigo)]
        }, baseOptions({
          plugins: { legend: { display: false }, tooltip: baseOptions().plugins.tooltip },
          scales: { x: axis({ grid: { display: false } }), y: axis({ beginAtZero: true, ticks: { precision: 0, color: tick } }) }
        }));
      });

      var at = d.attrition_trend || {};
      drawOrEmpty('ov-attrition', at.rate, function () {
        draw('ov-attrition', 'line', {
          labels: at.labels,
          datasets: [lineDataset('Attrition rate', at.rate, P.rose)]
        }, baseOptions({
          plugins: {
            legend: { display: false },
            tooltip: Object.assign({}, baseOptions().plugins.tooltip, {
              callbacks: { label: function (ctx) { return ' Attrition: ' + pct(ctx.parsed.y, 2); } }
            })
          },
          scales: {
            x: axis({ grid: { display: false } }),
            y: axis({ beginAtZero: true, ticks: { color: tick, callback: function (v) { return v + '%'; } } })
          }
        }), 'No separations recorded');
      }, 'No separations recorded', 'Attrition appears once offboarding records exist for the period.');

      var mix = d.department_mix || {};
      doughnut('ov-dept', mix.labels || [], mix.values || []);
    },

    workforce: function (d) {
      var t = d.trend || {};
      drawOrEmpty('wf-trend', (t.headcount || []).concat(t.joiners || []), function () {
        draw('wf-trend', 'bar', {
          labels: t.labels,
          datasets: [
            barDataset('Joiners', t.joiners, P.emerald, { stack: 'flow' }),
            barDataset('Exits', t.leavers, P.rose, { stack: 'flow' }),
            Object.assign(lineDataset('Closing headcount', t.headcount, P.violet, { fill: true }),
              { type: 'line', yAxisID: 'y1', borderWidth: 3 })
          ]
        }, baseOptions({
          scales: {
            x: axis({ stacked: true, grid: { display: false } }),
            y: axis({ stacked: true }),
            y1: axis({ position: 'right', grid: { display: false }, beginAtZero: true })
          },
          plugins: {
            legend: baseOptions().plugins.legend,
            tooltip: Object.assign({}, baseOptions().plugins.tooltip, {
              callbacks: { label: function (ctx) { return ' ' + ctx.dataset.label + ': ' + num(Math.abs(ctx.parsed.y)); } }
            })
          }
        }));
      });

      var dept = d.departments || {};
      horizontalBar('wf-dept', dept.labels || [], dept.values || [], P.violet);

      var span = d.span || {};
      stat('wf-managers', num(span.managers));
      stat('wf-span', (span.average || 0).toFixed(1));
      stat('wf-widest', num(span.widest));
      stat('wf-ic', num(span.individual_contributors));

      var grades = d.grades || {};
      horizontalBar('wf-grades', grades.labels || [], grades.values || [], P.teal);

      doughnut('wf-type', (d.employment_type || {}).labels || [], (d.employment_type || {}).values || [],
        [P.violet, P.sky, P.amber, P.emerald, P.rose]);
      doughnut('wf-mode', (d.work_mode || {}).labels || [], (d.work_mode || {}).values || [],
        [P.indigo, P.teal, P.pink, P.slate]);
      doughnut('wf-status', (d.employment_status || {}).labels || [], (d.employment_status || {}).values || [],
        [P.emerald, P.amber, P.rose, P.slate, P.sky]);

      var tenure = d.tenure || {};
      drawOrEmpty('wf-tenure', tenure.values, function () {
        draw('wf-tenure', 'bar', {
          labels: tenure.labels,
          datasets: [barDataset('Employees', tenure.values, P.indigo)]
        }, baseOptions({
          plugins: { legend: { display: false }, tooltip: baseOptions().plugins.tooltip },
          scales: { x: axis({ grid: { display: false } }), y: axis({ beginAtZero: true, ticks: { precision: 0, color: tick } }) }
        }));
      });

      var loc = d.locations || {};
      horizontalBar('wf-locations', loc.labels || [], loc.values || [], P.sky);
    },

    attrition: function (d) {
      var k = d.kpis || {};
      badge('at-annual', pct(k.annualised) + ' annualised');

      var t = d.trend || {};
      drawOrEmpty('at-trend', (t.rate || []).concat(t.voluntary || []), function () {
        draw('at-trend', 'bar', {
          labels: t.labels,
          datasets: [
            barDataset('Voluntary', t.voluntary, P.amber, { stack: 'exits' }),
            barDataset('Involuntary', t.involuntary, P.rose, { stack: 'exits' }),
            Object.assign(lineDataset('Attrition rate', t.rate, P.violet, { fill: false }),
              { type: 'line', yAxisID: 'y1', borderWidth: 3 })
          ]
        }, baseOptions({
          scales: {
            x: axis({ stacked: true, grid: { display: false } }),
            y: axis({ stacked: true, beginAtZero: true, ticks: { precision: 0, color: tick } }),
            y1: axis({
              position: 'right', grid: { display: false }, beginAtZero: true,
              ticks: { color: tick, callback: function (v) { return v + '%'; } }
            })
          }
        }));
      }, 'No separations in this period', 'Exits are read from completed offboarding workflows.');

      doughnut('at-split', (d.split || {}).labels || [], (d.split || {}).values || [],
        [P.amber, P.rose, P.sky, P.slate]);
      doughnut('at-reasons', (d.reasons || {}).labels || [], (d.reasons || {}).values || []);

      var byTenure = d.by_tenure || {};
      drawOrEmpty('at-tenure', byTenure.values, function () {
        draw('at-tenure', 'bar', {
          labels: byTenure.labels,
          datasets: [barDataset('Exits', byTenure.values, P.rose)]
        }, baseOptions({
          plugins: { legend: { display: false }, tooltip: baseOptions().plugins.tooltip },
          scales: { x: axis({ grid: { display: false } }), y: axis({ beginAtZero: true, ticks: { precision: 0, color: tick } }) }
        }));
      });

      var byDept = d.by_department || {};
      horizontalBar('at-dept', byDept.labels || [], byDept.values || [], P.rose, function (v) { return pct(v); });

      var body = root.querySelector('[data-hra-table="at-recent"]');
      if (body) {
        var rows = d.recent || [];
        body.innerHTML = rows.length ? rows.map(function (r) {
          return '<tr>' +
            '<td>' + escapeHtml(r.name) + '</td>' +
            '<td>' + escapeHtml(r.department) + '</td>' +
            '<td>' + escapeHtml(r.exit_date_display) + '</td>' +
            '<td>' + escapeHtml(r.reason) + '</td>' +
            '<td>' + r.tenure.toFixed(1) + ' yrs</td>' +
          '</tr>';
        }).join('') : '<tr><td colspan="5" style="text-align:center;padding:1.5rem">No separations in this period.</td></tr>';
      }
    },

    attendance: function (d) {
      var k = d.kpis || {};
      stat('att-workdays', num(k.working_days));
      stat('att-ot', num(k.overtime_hours, 1));

      var t = d.trend || {};
      drawOrEmpty('att-trend', (t.attendance || []).concat(t.absence || []), function () {
        draw('att-trend', 'line', {
          labels: t.labels,
          datasets: [
            lineDataset('Attendance %', t.attendance, P.emerald),
            lineDataset('Absenteeism %', t.absence, P.rose, { fill: false }),
            Object.assign(lineDataset('Avg hours', t.avg_hours, P.sky, { fill: false, borderDash: [5, 4] }),
              { yAxisID: 'y1' })
          ]
        }, baseOptions({
          scales: {
            x: axis({ grid: { display: false } }),
            y: axis({ beginAtZero: true, ticks: { color: tick, callback: function (v) { return v + '%'; } } }),
            y1: axis({
              position: 'right', grid: { display: false }, beginAtZero: true,
              ticks: { color: tick, callback: function (v) { return v + 'h'; } }
            })
          }
        }));
      }, 'No attendance records yet', 'Attendance rates appear once daily records are marked.');

      var mix = d.status_mix || {};
      doughnut('att-mix', mix.labels || [], mix.values || [], [P.emerald, P.sky, P.violet, P.amber, P.rose]);

      var dept = d.by_department || {};
      drawOrEmpty('att-dept', dept.attendance, function () {
        draw('att-dept', 'bar', {
          labels: dept.labels,
          datasets: [
            barDataset('Attendance %', dept.attendance, P.emerald),
            barDataset('Absence %', dept.absence, P.rose),
            barDataset('Late %', dept.late, P.amber)
          ]
        }, baseOptions({
          scales: {
            x: axis({ grid: { display: false } }),
            y: axis({ beginAtZero: true, ticks: { color: tick, callback: function (v) { return v + '%'; } } })
          }
        }));
      });

      var leave = d.leave || {};
      drawOrEmpty('att-leave', leave.allocated, function () {
        draw('att-leave', 'bar', {
          labels: leave.labels,
          datasets: [
            barDataset('Allocated', leave.allocated, P.slate),
            barDataset('Consumed', leave.used, P.violet)
          ]
        }, baseOptions({
          scales: { x: axis({ grid: { display: false } }), y: axis({ beginAtZero: true }) }
        }));
      }, 'No leave balances for this year', 'Allocate leave types to see utilisation here.');

      stat('lv-util', pct(leave.utilisation_rate));
      stat('lv-unused', num(leave.unused_days, 1));
      stat('lv-liability', money(leave.liability));
      stat('lv-turnaround', (leave.avg_approval_hours || 0).toFixed(1) + ' h');
      stat('lv-pending', num(leave.pending_requests));
    },

    compensation: function (d) {
      var k = d.kpis || {};
      badge('cp-runrate', money(k.monthly_run_rate) + ' / month');
      badge('cp-median', 'Median ' + money(k.median_ctc));
      stat('cp-gross', money(k.total_gross));
      stat('cp-net', money(k.total_net));
      stat('cp-deductions', money(k.total_deductions));
      stat('cp-employer', money(k.employer_contribution));
      stat('cp-annual', money(k.annualised_cost));
      stat('cp-ot', money(k.overtime_cost));

      var t = d.trend || {};
      drawOrEmpty('cp-trend', t.gross, function () {
        draw('cp-trend', 'bar', {
          labels: t.labels,
          datasets: [
            barDataset('Net paid', t.net, P.emerald, { stack: 'cost' }),
            barDataset('Deductions', t.deductions, P.amber, { stack: 'cost' }),
            Object.assign(lineDataset('Cost per employee', t.cost_per_employee, P.violet, { fill: false }),
              { type: 'line', yAxisID: 'y1', borderWidth: 3 })
          ]
        }, baseOptions({
          scales: {
            x: axis({ stacked: true, grid: { display: false } }),
            y: axis({ stacked: true, ticks: { color: tick, callback: function (v) { return money(v); } } }),
            y1: axis({
              position: 'right', grid: { display: false },
              ticks: { color: tick, callback: function (v) { return money(v); } }
            })
          },
          plugins: {
            legend: baseOptions().plugins.legend,
            tooltip: Object.assign({}, baseOptions().plugins.tooltip, {
              callbacks: { label: function (ctx) { return ' ' + ctx.dataset.label + ': ' + money(ctx.parsed.y, false); } }
            })
          }
        }));
      }, 'No processed payroll runs', 'Process a payroll run to populate cost analytics.');

      var bands = d.bands || {};
      drawOrEmpty('cp-bands', bands.values, function () {
        draw('cp-bands', 'bar', {
          labels: bands.labels,
          datasets: [barDataset('Employees', bands.values, P.indigo)]
        }, baseOptions({
          plugins: { legend: { display: false }, tooltip: baseOptions().plugins.tooltip },
          scales: { x: axis({ grid: { display: false } }), y: axis({ beginAtZero: true, ticks: { precision: 0, color: tick } }) }
        }));
      }, 'No salary records', 'Assign salary structures to see the band distribution.');

      horizontalBar('cp-dept', (d.by_department || {}).labels || [], (d.by_department || {}).values || [],
        P.teal, function (v) { return money(v); });
      horizontalBar('cp-grade', (d.by_grade || {}).labels || [], (d.by_grade || {}).values || [],
        P.violet, function (v) { return money(v); });
      doughnut('cp-payment', (d.payment_status || {}).labels || [], (d.payment_status || {}).values || [],
        [P.emerald, P.amber, P.rose, P.slate]);
    },

    diversity: function (d) {
      var k = d.kpis || {};
      stat('dv-female', pct(k.female_share));
      stat('dv-lead', pct(k.leadership_female_share));
      stat('dv-leaders', num(k.leaders));
      stat('dv-gap', pct(k.pay_gap));
      stat('dv-avgage', (k.average_age || 0).toFixed(1) + ' yrs');
      stat('dv-under35', pct(k.under_35_share, 0));
      badge('dv-age', 'Avg ' + (k.average_age || 0).toFixed(0) + ' yrs');

      var gender = d.gender || {};
      doughnut('dv-gender', gender.labels || [], gender.values || [], [P.sky, P.pink, P.teal, P.slate]);
      legend('dv-gender', gender.labels || [], gender.values || [], [P.sky, P.pink, P.teal, P.slate]);

      var dept = d.gender_by_department || {};
      drawOrEmpty('dv-dept', (dept.female || []).concat(dept.male || []), function () {
        draw('dv-dept', 'bar', {
          labels: dept.labels,
          datasets: [
            barDataset('Male', dept.male, P.sky, { stack: 'g' }),
            barDataset('Female', dept.female, P.pink, { stack: 'g' }),
            barDataset('Other / undisclosed', dept.other, P.slate, { stack: 'g' })
          ]
        }, baseOptions({
          scales: {
            x: axis({ stacked: true, grid: { display: false } }),
            y: axis({ stacked: true, beginAtZero: true, ticks: { precision: 0, color: tick } })
          }
        }));
      });

      var age = d.age || {};
      drawOrEmpty('dv-age', age.values, function () {
        draw('dv-age', 'bar', {
          labels: age.labels,
          datasets: [barDataset('Employees', age.values, P.teal)]
        }, baseOptions({
          plugins: { legend: { display: false }, tooltip: baseOptions().plugins.tooltip },
          scales: { x: axis({ grid: { display: false } }), y: axis({ beginAtZero: true, ticks: { precision: 0, color: tick } }) }
        }));
      }, 'No dates of birth on record', 'Add dates of birth to staff profiles to see the age profile.');

      var hiring = d.hiring || {};
      drawOrEmpty('dv-hiring', (hiring.female || []).concat(hiring.male || []), function () {
        draw('dv-hiring', 'bar', {
          labels: hiring.labels,
          datasets: [
            barDataset('Male hires', hiring.male, P.sky, { stack: 'h' }),
            barDataset('Female hires', hiring.female, P.pink, { stack: 'h' })
          ]
        }, baseOptions({
          scales: {
            x: axis({ stacked: true, grid: { display: false } }),
            y: axis({ stacked: true, beginAtZero: true, ticks: { precision: 0, color: tick } })
          }
        }));
      }, 'No hires in this window');

      var gap = d.pay_gap_by_department || {};
      drawOrEmpty('dv-gap', gap.values, function () {
        draw('dv-gap', 'bar', {
          labels: gap.labels,
          datasets: [{
            label: 'Mean pay gap',
            data: gap.values,
            backgroundColor: gap.values.map(function (v) { return alpha(v > 0 ? P.rose : P.emerald, 0.82); }),
            borderRadius: 6, borderSkipped: false, maxBarThickness: 24
          }]
        }, baseOptions({
          indexAxis: 'y',
          plugins: {
            legend: { display: false },
            tooltip: Object.assign({}, baseOptions().plugins.tooltip, {
              callbacks: { label: function (ctx) { return ' Gap: ' + pct(ctx.parsed.x); } }
            })
          },
          scales: {
            x: axis({ ticks: { color: tick, callback: function (v) { return v + '%'; } } }),
            y: axis({ grid: { display: false } })
          }
        }));
      }, 'Not enough data for a pay-gap read',
         'A department needs both male and female salary records to compare.');
    },

    scorecard: function (d) {
      badge('sc-days', num(d.working_days) + ' working days');
      renderScorecard(d);
    }
  };

  /* ── scorecard table ─────────────────────────────────────────────────── */

  function renderScorecard(d) {
    var body = root.querySelector('[data-hra-table="scorecard"]');
    var foot = root.querySelector('[data-hra-table="scorecard-total"]');
    if (!body) return;
    var rows = (d.rows || []).slice();

    rows.sort(function (a, b) {
      var x = a[scorecardSort.key], y = b[scorecardSort.key];
      if (typeof x === 'string') return scorecardSort.dir === 'asc' ? x.localeCompare(y) : y.localeCompare(x);
      return scorecardSort.dir === 'asc' ? x - y : y - x;
    });

    body.innerHTML = rows.length ? rows.map(function (r) {
      var netCls = r.net_change > 0 ? 'pos' : (r.net_change < 0 ? 'neg' : 'zero');
      return '<tr>' +
        '<td>' + escapeHtml(r.department) + '</td>' +
        '<td>' + num(r.opening) + '</td>' +
        '<td>' + num(r.headcount) + '</td>' +
        '<td>' + num(r.joiners) + '</td>' +
        '<td>' + num(r.leavers) + '</td>' +
        '<td><span class="hra-chip hra-chip--' + netCls + '">' +
          (r.net_change > 0 ? '+' : '') + r.net_change + '</span></td>' +
        '<td>' + heatInverse(r.attrition_rate, 10, 20) + '</td>' +
        '<td>' + r.avg_tenure.toFixed(1) + ' yrs</td>' +
        '<td>' + heat(r.attendance_rate, 90, 75) + '</td>' +
        '<td>' + heatInverse(r.absenteeism_rate, 3, 8) + '</td>' +
        '<td>' + money(r.avg_ctc) + '</td>' +
        '<td>' + money(r.monthly_cost) + '</td>' +
        '<td>' + pct(r.female_share, 0) + '</td>' +
        '<td>' + num(r.on_notice) + '</td>' +
      '</tr>';
    }).join('') : '<tr><td colspan="14" style="text-align:center;padding:2rem">No departments match these filters.</td></tr>';

    if (foot) {
      var t = d.totals || {};
      foot.innerHTML = rows.length ? '<tr>' +
        '<td>All departments</td><td>—</td>' +
        '<td>' + num(t.headcount) + '</td>' +
        '<td>' + num(t.joiners) + '</td>' +
        '<td>' + num(t.leavers) + '</td>' +
        '<td>' + (t.net_change > 0 ? '+' : '') + num(t.net_change) + '</td>' +
        '<td>—</td><td>—</td><td>—</td><td>—</td><td>—</td>' +
        '<td>' + money(t.monthly_cost) + '</td>' +
        '<td>—</td><td>' + num(t.on_notice) + '</td>' +
      '</tr>' : '';
    }

    root.querySelectorAll('[data-hra-scorecard] th[data-sort-key]').forEach(function (th) {
      if (th.dataset.sortKey === scorecardSort.key) th.dataset.sorted = scorecardSort.dir;
      else delete th.dataset.sorted;
    });
  }

  /* ── interactions ────────────────────────────────────────────────────── */

  function activate(section) {
    activeSection = section;
    root.querySelectorAll('[data-hra-tab]').forEach(function (tab) {
      tab.classList.toggle('hra-tab--active', tab.dataset.hraTab === section);
    });
    root.querySelectorAll('[data-hra-section]').forEach(function (panel) {
      panel.dataset.active = panel.dataset.hraSection === section ? 'true' : 'false';
    });
    try { history.replaceState(null, '', '#' + section); } catch (e) {}
    render(section);
  }

  root.querySelectorAll('[data-hra-tab]').forEach(function (tab) {
    tab.addEventListener('click', function () { activate(tab.dataset.hraTab); });
  });

  // Period select toggles the custom date inputs.
  var periodSelect = root.querySelector('[data-hra-period]');
  if (periodSelect) {
    periodSelect.addEventListener('change', function () {
      var custom = periodSelect.value === 'custom';
      root.querySelectorAll('[data-hra-custom]').forEach(function (node) { node.hidden = !custom; });
      if (!custom) root.querySelector('[data-hra-filters]').submit();
    });
  }

  var refreshBtn = root.querySelector('[data-hra-refresh]');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', function () {
      cache = {};
      var icon = refreshBtn.querySelector('i');
      if (icon) icon.style.animation = 'hra-spin .7s linear 2';
      render(activeSection, true).then(function () {
        var el = root.querySelector('[data-hra-updated]');
        if (el) el.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        if (icon) icon.style.animation = '';
      });
    });
  }

  // Export menu.
  var menu = root.querySelector('[data-hra-menu]');
  if (menu) {
    var list = menu.querySelector('[data-hra-menu-list]');
    menu.querySelector('[data-hra-menu-toggle]').addEventListener('click', function (e) {
      e.stopPropagation();
      list.dataset.open = list.dataset.open === 'true' ? 'false' : 'true';
    });
    document.addEventListener('click', function () { list.dataset.open = 'false'; });
    menu.querySelectorAll('[data-hra-export]').forEach(function (link) {
      link.addEventListener('click', function () {
        var params = currentQuery();
        params.set('export', link.dataset.hraExport);
        link.setAttribute('href', '?' + params.toString());
      });
    });
    var printBtn = menu.querySelector('[data-hra-print]');
    if (printBtn) {
      printBtn.addEventListener('click', function () {
        // Print every section, not just the visible one.
        root.querySelectorAll('[data-hra-section]').forEach(function (p) { p.dataset.active = 'true'; });
        Promise.all(['overview', 'workforce', 'attrition', 'attendance', 'compensation',
                     'diversity', 'scorecard'].map(function (s) { return render(s); }))
          .then(function () { setTimeout(function () { window.print(); activate(activeSection); }, 350); });
      });
    }
  }

  // Scorecard sorting.
  root.querySelectorAll('[data-hra-scorecard] th[data-sort-key]').forEach(function (th) {
    th.addEventListener('click', function () {
      var key = th.dataset.sortKey;
      if (scorecardSort.key === key) {
        scorecardSort.dir = scorecardSort.dir === 'asc' ? 'desc' : 'asc';
      } else {
        scorecardSort.key = key;
        scorecardSort.dir = key === 'department' ? 'asc' : 'desc';
      }
      if (cache.scorecard) renderScorecard(cache.scorecard);
    });
  });

  /* ── boot ────────────────────────────────────────────────────────────── */

  var initial = (window.location.hash || '').replace('#', '');
  var valid = ['overview', 'workforce', 'attrition', 'attendance', 'compensation', 'diversity', 'scorecard'];
  activate(valid.indexOf(initial) >= 0 ? initial : 'overview');

  // activate() rewrites the hash, so the URL can change without a page load — e.g.
  // clicking "HR Analytics" in the left nav while already here navigates from
  // "…/#compensation" to "…/", which the browser treats as a same-document jump.
  // Without this the section shown and the URL drift apart and the nav link looks dead.
  window.addEventListener('hashchange', function () {
    var next = (window.location.hash || '').replace('#', '');
    if (valid.indexOf(next) < 0) next = 'overview';
    if (next !== activeSection) activate(next);
  });

  // The overview KPI band and hero counters come from the overview payload,
  // so make sure it is fetched even when another tab was deep-linked.
  if (activeSection !== 'overview') {
    load('overview').then(function (d) {
      renderKpis(d.kpis || []);
      renderInsights(d.insights || []);
      var totals = d.totals || {};
      var el = root.querySelector('[data-hra-hero-headcount]');
      if (el) el.textContent = num(totals.headcount);
      var el2 = root.querySelector('[data-hra-hero-depts]');
      if (el2) el2.textContent = num(totals.departments);
      refreshIcons();
    }).catch(function () {});
  }

  var updated = root.querySelector('[data-hra-updated]');
  if (updated) updated.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
})();

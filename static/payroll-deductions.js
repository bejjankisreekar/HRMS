/* Payroll Deductions dashboard — modal drill-downs + analytics chart (AJAX). */
(function () {
  "use strict";

  function fmt(v) {
    return "₹" + (Number(v) || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });
  }

  function baseQuery() {
    var p = new URLSearchParams(window.location.search);
    p.delete("page");
    return p;
  }

  var modal = document.getElementById("deductionModal");
  var body = document.getElementById("deductionModalBody");

  function openModal(html) {
    if (!modal || !body) return;
    body.innerHTML = html;
    modal.hidden = false;
    document.body.style.overflow = "hidden";
    if (window.lucide) lucide.createIcons();
  }
  function closeModal() {
    if (!modal) return;
    modal.hidden = true;
    document.body.style.overflow = "";
  }
  if (modal) {
    modal.addEventListener("click", function (e) {
      if (e.target === modal || (e.target.closest && e.target.closest("[data-close]"))) closeModal();
    });
  }

  function row(label, value) {
    return '<div class="flex justify-between py-1 text-sm"><span class="text-slate-500">' +
      label + '</span><span class="font-semibold">' + fmt(value) + "</span></div>";
  }

  // ── Employee breakdown modal ──
  function loadEmployee(id) {
    var q = baseQuery();
    openModal('<p class="text-sm text-slate-400">Loading…</p>');
    fetch("/api/payroll/deductions/employee/" + id + "/?" + q.toString(), {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) { openModal('<p class="text-rose-400 text-sm">' + (res.d.error || "Error") + "</p>"); return; }
        var d = res.d, e = d.employee, ded = d.deductions, ern = d.earnings;
        openModal(
          '<div class="flex items-start justify-between gap-4">' +
            '<div><h3 class="text-lg font-semibold text-slate-900 dark:text-white">' + e.name + "</h3>" +
            '<p class="text-sm text-slate-400">' + e.employee_id + " · " + e.department + " · " + e.designation + "</p>" +
            '<p class="text-xs text-slate-500">' + d.period + "</p></div>" +
            '<button type="button" data-close class="pr-btn-ghost text-xs">Close</button></div>' +
          '<div class="mt-4 grid gap-4 sm:grid-cols-2">' +
            '<div><h4 class="text-xs font-semibold uppercase text-emerald-500">Earnings</h4>' +
              row("Basic", ern.basic) + row("HRA", ern.hra) + row("Special", ern.special) +
              row("Bonus", ern.bonus) + row("Other", ern.other) + "</div>" +
            '<div><h4 class="text-xs font-semibold uppercase text-rose-500">Deductions</h4>' +
              row("TDS", ded.tds) + row("Employee PF", ded.employee_pf) + row("Employer PF", ded.employer_pf) +
              row("ESI", ded.esi) + row("PT", ded.pt) + row("LOP", ded.lop) +
              row("Loan", ded.loan) + row("Advance", ded.advance) + row("Notice", ded.notice) +
              row("Other", ded.other) + "</div></div>" +
          '<div class="mt-4 grid grid-cols-3 gap-3 rounded-xl bg-violet-600/10 p-3 text-center">' +
            '<div><p class="text-xs text-slate-500">Gross</p><p class="font-bold">' + fmt(d.gross) + "</p></div>" +
            '<div><p class="text-xs text-slate-500">Total Deductions</p><p class="font-bold text-rose-400">' + fmt(d.total_deductions) + "</p></div>" +
            '<div><p class="text-xs text-slate-500">Net</p><p class="font-bold text-emerald-400">' + fmt(d.net) + "</p></div></div>"
        );
      })
      .catch(function () { openModal('<p class="text-rose-400 text-sm">Failed to load.</p>'); });
  }

  // ── Deduction-type drill-down modal ──
  var DED_PATH = { tax: "tax", pf: "pf", esi: "esi", pt: "pt" };
  function loadDrilldown(type) {
    var q = baseQuery();
    openModal('<p class="text-sm text-slate-400">Loading…</p>');
    fetch("/api/payroll/deductions/" + DED_PATH[type] + "/?" + q.toString(), {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var head = '<div class="flex items-center justify-between"><h3 class="text-lg font-semibold text-slate-900 dark:text-white">' +
          type.toUpperCase() + ' details</h3><button type="button" data-close class="pr-btn-ghost text-xs">Close</button></div>';
        var rows = (d.rows || []).map(function (r) {
          return "<tr><td class='py-1'>" + r.employee_name + "</td><td>" + r.period + "</td>" +
            (r.taxable_income != null ? "<td>" + fmt(r.taxable_income) + "</td>" : "") +
            "<td class='font-semibold'>" + fmt(r.amount) + "</td><td>" + r.status_display + "</td></tr>";
        }).join("");
        var taxCol = type === "tax" ? "<th>Taxable Income</th>" : "";
        openModal(head +
          '<p class="mt-1 text-xs text-slate-500">Total: ' + fmt(d.total) + "</p>" +
          '<div class="mt-3 max-h-96 overflow-auto"><table class="pr-table w-full text-sm"><thead><tr>' +
          "<th>Employee</th><th>Month</th>" + taxCol + "<th>Amount</th><th>Status</th></tr></thead><tbody>" +
          (rows || '<tr><td colspan="5" class="py-6 text-center text-slate-500">No records.</td></tr>') +
          "</tbody></table></div>");
      })
      .catch(function () { openModal('<p class="text-rose-400 text-sm">Failed to load.</p>'); });
  }

  // ── Analytics chart ──
  var chart = null;
  function loadAnalytics(period) {
    var section = document.getElementById("analyticsSection");
    if (!section || typeof Chart === "undefined") return;
    var year = section.dataset.year;
    fetch("/api/payroll/deductions/summary/?view=" + period + "&year=" + year, {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var el = document.getElementById("chartDeductions");
        if (!el) return;
        if (chart) chart.destroy();
        var s = d.series || {};
        chart = new Chart(el, {
          type: "bar",
          data: {
            labels: d.labels || [],
            datasets: [
              { label: "TDS", data: s.tds || [], backgroundColor: "rgba(245,158,11,0.8)" },
              { label: "PF", data: s.pf || [], backgroundColor: "rgba(14,165,233,0.8)" },
              { label: "PT", data: s.pt || [], backgroundColor: "rgba(236,72,153,0.8)" },
              { label: "ESI", data: s.esi || [], backgroundColor: "rgba(34,211,238,0.8)" },
            ],
          },
          options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { position: "bottom" } },
            scales: { y: { beginAtZero: true } },
          },
        });
      });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-employee]").forEach(function (tr) {
      tr.addEventListener("click", function () { loadEmployee(tr.dataset.employee); });
    });
    document.querySelectorAll("[data-deduction]").forEach(function (c) {
      c.addEventListener("click", function () { loadDrilldown(c.dataset.deduction); });
    });
    var per = document.getElementById("analyticsPeriod");
    if (per) {
      per.addEventListener("change", function () { loadAnalytics(per.value); });
      loadAnalytics(per.value);
    }
  });
})();

/* Digital Attendance Register — tooltips, search, interactions */
(function () {
  "use strict";

  function initTooltip() {
    var tip = document.getElementById("dr-tooltip");
    if (!tip) return;
    var table = document.getElementById("dr-table");
    if (!table) return;

    function show(cell, ev) {
      var name = cell.getAttribute("data-tip-name");
      if (!name) return;
      tip.innerHTML =
        '<div class="dr-tooltip__name">' + name + "</div>" +
        '<div class="dr-tooltip__row"><span class="dr-tooltip__k">Date</span><span class="dr-tooltip__v">' + fmtDate(cell.getAttribute("data-tip-date")) + "</span></div>" +
        '<div class="dr-tooltip__row"><span class="dr-tooltip__k">Status</span><span class="dr-tooltip__v">' + cell.getAttribute("data-tip-status") + "</span></div>" +
        '<div class="dr-tooltip__row"><span class="dr-tooltip__k">Check-in</span><span class="dr-tooltip__v">' + cell.getAttribute("data-tip-in") + "</span></div>" +
        '<div class="dr-tooltip__row"><span class="dr-tooltip__k">Check-out</span><span class="dr-tooltip__v">' + cell.getAttribute("data-tip-out") + "</span></div>" +
        '<div class="dr-tooltip__row"><span class="dr-tooltip__k">Working</span><span class="dr-tooltip__v">' + cell.getAttribute("data-tip-hours") + "</span></div>";
      tip.classList.add("is-visible");
      tip.setAttribute("aria-hidden", "false");
      position(ev);
    }
    function position(ev) {
      var pad = 14;
      var w = tip.offsetWidth, h = tip.offsetHeight;
      var x = ev.clientX + pad, y = ev.clientY + pad;
      if (x + w > window.innerWidth) x = ev.clientX - w - pad;
      if (y + h > window.innerHeight) y = ev.clientY - h - pad;
      tip.style.left = x + "px";
      tip.style.top = y + "px";
    }
    function hide() {
      tip.classList.remove("is-visible");
      tip.setAttribute("aria-hidden", "true");
    }

    table.addEventListener("mouseover", function (e) {
      var cell = e.target.closest("[data-tip-name]");
      if (cell) show(cell, e);
    });
    table.addEventListener("mousemove", function (e) {
      if (tip.classList.contains("is-visible")) position(e);
    });
    table.addEventListener("mouseout", function (e) {
      if (e.target.closest("[data-tip-name]")) hide();
    });
    document.getElementById("dr-scroll").addEventListener("scroll", hide);
  }

  function fmtDate(iso) {
    if (!iso) return "—";
    var p = iso.split("-");
    if (p.length !== 3) return iso;
    var months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    return p[2] + "-" + months[parseInt(p[1], 10) - 1] + "-" + p[0];
  }

  function initSearch() {
    var input = document.getElementById("dr-search-input");
    if (!input) return;
    var rows = document.querySelectorAll(".dr-tr[data-search]");
    var cards = document.querySelectorAll(".dr-mcard[data-search]");
    function filter() {
      var q = input.value.trim().toLowerCase();
      [].forEach.call(rows, function (r) {
        r.style.display = !q || r.dataset.search.indexOf(q) !== -1 ? "" : "none";
      });
      [].forEach.call(cards, function (c) {
        c.style.display = !q || c.dataset.search.indexOf(q) !== -1 ? "" : "none";
      });
    }
    input.addEventListener("input", filter);
    // Don't submit the form on Enter (keep client-side filter snappy)
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") e.preventDefault();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initTooltip();
    initSearch();
    if (window.lucide) window.lucide.createIcons();
  });
})();

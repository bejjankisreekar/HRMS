/* Staff create / edit — vanilla JS, no CDN dependencies */
(function () {
  "use strict";

  /* ────────────────────────────────────────────────────────
     Tab system
     Uses data-tab-btn="<name>" on buttons
     and data-tab-panel="<name>" on sections.
     Active state: .se-tab-btn--active on button,
                   .se-tab-active on panel.
  ──────────────────────────────────────────────────────── */
  function initTabs(root) {
    var panels = Array.from(root.querySelectorAll("[data-tab-panel]"));
    var btns   = Array.from(root.querySelectorAll("[data-tab-btn]"));

    if (!btns.length || !panels.length) return;

    function activate(name) {
      panels.forEach(function (p) {
        p.classList.toggle("se-tab-active", p.dataset.tabPanel === name);
      });
      btns.forEach(function (b) {
        b.classList.toggle("se-tab-btn--active", b.dataset.tabBtn === name);
        b.setAttribute("aria-selected", b.dataset.tabBtn === name ? "true" : "false");
      });
    }

    btns.forEach(function (b) {
      b.addEventListener("click", function () {
        activate(b.dataset.tabBtn);
        // scroll tab into view on mobile
        b.scrollIntoView({ block: "nearest", inline: "nearest" });
      });
    });

    // listen for programmatic tab changes (e.g. sidebar quick-jump)
    window.addEventListener("se-set-tab", function (e) {
      activate(e.detail);
      var btn = root.querySelector('[data-tab-btn="' + e.detail + '"]');
      if (btn) btn.scrollIntoView({ block: "nearest", inline: "nearest" });
    });

    // activate the first tab immediately (panel is already marked se-tab-btn--active in HTML)
    var firstActive = root.querySelector(".se-tab-btn--active");
    if (firstActive) {
      activate(firstActive.dataset.tabBtn);
    } else {
      activate(btns[0].dataset.tabBtn);
    }
  }

  /* ────────────────────────────────────────────────────────
     Role toggle
     Reads input[name="role"] radios or hidden input.
     Updates data-role-label, data-role-badge, data-role-show.
  ──────────────────────────────────────────────────────── */
  function initRoleToggle(root) {
    var radios      = Array.from(root.querySelectorAll("input[name='role']"));
    var roleLabels  = Array.from(root.querySelectorAll("[data-role-label]"));
    var hrBadge     = root.querySelector("[data-role-badge='HR']");
    var empBadge    = root.querySelector("[data-role-badge='EMPLOYEE']");
    var roleShowEls = Array.from(root.querySelectorAll("[data-role-show]"));

    var ROLE_TEXT = { HR: "HR", EMPLOYEE: "Employee" };

    function applyRole(val) {
      roleLabels.forEach(function (el) {
        el.textContent = ROLE_TEXT[val] || "Employee";
      });
      if (hrBadge)  hrBadge.style.display  = val === "HR"       ? "" : "none";
      if (empBadge) empBadge.style.display = val === "EMPLOYEE" ? "" : "none";
      roleShowEls.forEach(function (el) {
        // data-role-show may be a comma-separated list of roles.
        var roles = el.dataset.roleShow.split(",");
        el.style.display = roles.indexOf(val) !== -1 ? "" : "none";
      });
    }

    if (radios.length) {
      radios.forEach(function (r) {
        r.addEventListener("change", function () { applyRole(r.value); });
      });
      var checked = radios.find(function (r) { return r.checked; });
      applyRole(checked ? checked.value : (radios[0] ? radios[0].value : "EMPLOYEE"));
    } else {
      // hidden input (HR-creator mode)
      var hidden = root.querySelector("input[type='hidden'][name='role']");
      if (hidden) applyRole(hidden.value);
    }
  }

  /* ────────────────────────────────────────────────────────
     Name / initial preview
     Updates ALL [data-preview="name"] and [data-preview="initial"]
  ──────────────────────────────────────────────────────── */
  function initNamePreview(root) {
    var fnEl      = document.getElementById("id_first_name");
    var lnEl      = document.getElementById("id_last_name");
    var nameEls   = Array.from(root.querySelectorAll("[data-preview='name']"));
    var initEls   = Array.from(root.querySelectorAll("[data-preview='initial']"));

    function update() {
      var fn   = fnEl ? fnEl.value.trim() : "";
      var ln   = lnEl ? lnEl.value.trim() : "";
      var full = (fn + " " + ln).trim() || "New team member";
      var init = (fn || ln || "N").charAt(0).toUpperCase();
      nameEls.forEach(function (el) { el.textContent = full; });
      initEls.forEach(function (el) { el.textContent = init; });
    }

    if (fnEl) fnEl.addEventListener("input", update);
    if (lnEl) lnEl.addEventListener("input", update);
    update();
  }

  /* ────────────────────────────────────────────────────────
     Reporting manager preview
     Updates ALL [data-preview="manager"] elements.
     Shows/hides [data-manager-row].
  ──────────────────────────────────────────────────────── */
  function initManagerPreview(root) {
    var sel        = document.getElementById("id_reporting_manager");
    var managerEls = Array.from(root.querySelectorAll("[data-preview='manager']"));
    var managerRow = root.querySelector("[data-manager-row]");

    function update() {
      if (!sel) return;
      var opt = sel.options[sel.selectedIndex];
      var txt = opt ? opt.text.trim().replace(/^[-–\s]+/, "") : "";
      // treat placeholder options as empty
      if (sel.value === "" || sel.value === "0") txt = "";
      managerEls.forEach(function (el) { el.textContent = txt || "—"; });
      if (managerRow) managerRow.style.display = txt ? "" : "none";
    }

    if (sel) {
      sel.addEventListener("change", update);
      update();
    }
  }

  /* ────────────────────────────────────────────────────────
     Password show / hide toggle
  ──────────────────────────────────────────────────────── */
  function initPasswordToggle(root) {
    var btn = root.querySelector("[data-pwd-toggle]");
    var inp = document.getElementById("id_password");
    if (!btn || !inp) return;
    btn.addEventListener("click", function () {
      var show = inp.type === "text";
      inp.type = show ? "password" : "text";
      btn.textContent = show ? "Show" : "Hide";
    });
  }

  /* ────────────────────────────────────────────────────────
     Dirty-state unsaved-changes warning
  ──────────────────────────────────────────────────────── */
  function initDirtyState(form) {
    var dirty    = false;
    var statusEl = document.getElementById("se-save-status");
    var isCreate = form.id === "staff-create-form";

    function markDirty() {
      if (dirty) return;
      dirty = true;
      if (statusEl) {
        statusEl.textContent = isCreate ? "Unsaved draft" : "Unsaved changes";
        statusEl.classList.remove("hidden");
      }
    }

    form.querySelectorAll("input, select, textarea").forEach(function (el) {
      el.addEventListener("change", markDirty);
      el.addEventListener("input", markDirty);
    });

    form.addEventListener("submit", function () { dirty = false; });

    window.addEventListener("beforeunload", function (e) {
      if (!dirty) return;
      e.preventDefault();
      e.returnValue = "";
    });
  }

  /* ────────────────────────────────────────────────────────
     Sidebar quick-jump buttons (data-se-tab-jump)
  ──────────────────────────────────────────────────────── */
  function initTabJumps(root) {
    root.querySelectorAll("[data-se-tab-jump]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        window.dispatchEvent(
          new CustomEvent("se-set-tab", { detail: btn.dataset.seTabJump })
        );
        // scroll main content to top
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
    });
  }

  /* ────────────────────────────────────────────────────────
     Lucide icons
  ──────────────────────────────────────────────────────── */
  function renderIcons() {
    if (window.lucide && typeof window.lucide.createIcons === "function") {
      window.lucide.createIcons();
    }
  }

  /* ────────────────────────────────────────────────────────
     Bootstrap
  ──────────────────────────────────────────────────────── */
  document.addEventListener("DOMContentLoaded", function () {
    var form = document.getElementById("staff-edit-form") ||
               document.getElementById("staff-create-form");
    if (!form) return;

    // root is the [data-se-root] ancestor or document
    var root = form.closest("[data-se-root]") || document.body;

    initTabs(root);
    initRoleToggle(root);
    initNamePreview(root);
    initManagerPreview(root);
    initPasswordToggle(root);
    initDirtyState(form);
    initTabJumps(root);
    renderIcons();
  });
})();

function initGradesDashboard() {
  "use strict";

  const cfg = window.GRADES_CONFIG || {};

  async function postAction(payload) {
    const res = await fetch(cfg.apiAction, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": cfg.csrf },
      body: JSON.stringify(payload),
    });
    return res.json();
  }

  document.querySelectorAll("[data-grd-seed]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("Seed default HR and employee grades? Existing grades are kept.")) return;
      btn.disabled = true;
      try {
        await postAction({ action: "seed_defaults" });
        window.location.reload();
      } catch (e) {
        alert("Failed to seed grades.");
      } finally {
        btn.disabled = false;
      }
    });
  });


  /* ---------------- Modals ---------------- */

  let openModal = null;

  function showModal(modal) {
    if (!modal) return;
    // The dashboard shell wraps page content in .hrms-dashboard-main, which is
    // position:relative + z-index:1 — a stacking context the modal cannot escape with
    // z-index alone, leaving the sticky topnav painted over its header. Reparenting to
    // <body> puts the modal back in the root stacking context.
    if (modal.parentElement !== document.body) {
      document.body.appendChild(modal);
    }
    modal.hidden = false;
    document.body.classList.add("grd-modal-open");
    openModal = modal;
    const focusable = modal.querySelector(
      "input:not([type=hidden]):not([disabled]), select, textarea, button"
    );
    if (focusable) focusable.focus({ preventScroll: true });
    modal.querySelectorAll("[data-grd-picker]").forEach(syncPicker);
  }

  function hideModal(modal) {
    if (!modal) return;
    const url = modal.getAttribute("data-grd-close-url");
    if (url) {
      window.location.href = url;
      return;
    }
    modal.hidden = true;
    document.body.classList.remove("grd-modal-open");
    if (openModal === modal) openModal = null;
  }

  function initModals() {
    document.querySelectorAll("[data-grd-open]").forEach((btn) => {
      btn.addEventListener("click", () => {
        showModal(document.getElementById(btn.getAttribute("data-grd-open")));
      });
    });

    document.querySelectorAll(".grd-modal [data-grd-close]").forEach((el) => {
      el.addEventListener("click", () => hideModal(el.closest(".grd-modal")));
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && openModal) hideModal(openModal);
    });

    document.querySelectorAll(".grd-modal[data-grd-autoopen]").forEach(showModal);
  }

  /* ------------- Department picker ------------- */

  function pickerBoxes(picker) {
    return Array.from(picker.querySelectorAll('input[type="checkbox"]'));
  }

  function syncPicker(picker) {
    const boxes = pickerBoxes(picker);
    const selected = boxes.filter((b) => b.checked).length;
    const counter = picker.querySelector("[data-grd-picker-count]");
    if (counter) {
      counter.textContent = selected + " of " + boxes.length + " selected";
      counter.classList.toggle("is-on", selected > 0);
    }
  }

  function filterPicker(picker, term) {
    const q = term.trim().toLowerCase();
    let visible = 0;
    pickerBoxes(picker).forEach((box) => {
      const row = box.closest("div");
      if (!row) return;
      const match = row.textContent.toLowerCase().includes(q);
      row.hidden = !match;
      if (match) visible += 1;
    });
    const empty = picker.querySelector("[data-grd-picker-empty]");
    if (empty) empty.hidden = visible !== 0;
  }

  function initPickers() {
    document.querySelectorAll("[data-grd-picker]").forEach((picker) => {
      picker.addEventListener("change", (e) => {
        if (e.target.matches('input[type="checkbox"]')) syncPicker(picker);
      });

      const search = picker.querySelector("[data-grd-picker-search]");
      if (search) {
        search.addEventListener("input", () => filterPicker(picker, search.value));
      }

      const setAll = (state) => {
        pickerBoxes(picker).forEach((box) => {
          const row = box.closest("div");
          if (row && row.hidden) return; // respect the active search filter
          box.checked = state;
        });
        syncPicker(picker);
      };
      const all = picker.querySelector("[data-grd-picker-all]");
      if (all) all.addEventListener("click", () => setAll(true));
      const none = picker.querySelector("[data-grd-picker-none]");
      if (none) none.addEventListener("click", () => setAll(false));

      syncPicker(picker);
    });
  }

  /* ------------- Destructive confirms ------------- */

  function initConfirms() {
    document.querySelectorAll("[data-grd-confirm]").forEach((form) => {
      form.addEventListener("submit", (e) => {
        if (!confirm(form.getAttribute("data-grd-confirm"))) e.preventDefault();
      });
    });
  }

  initPickers();
  initModals();
  initConfirms();
  if (window.lucide) window.lucide.createIcons();
}

document.addEventListener("DOMContentLoaded", initGradesDashboard);

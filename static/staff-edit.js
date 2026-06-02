(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    var form = document.getElementById("staff-edit-form") || document.getElementById("staff-create-form");
    if (!form) return;

    var dirty = false;
    var statusEl = document.getElementById("se-save-status");
    var isCreate = form.id === "staff-create-form";

    function markDirty() {
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

    form.addEventListener("submit", function () {
      dirty = false;
    });

    window.addEventListener("beforeunload", function (e) {
      if (!dirty) return;
      e.preventDefault();
      e.returnValue = "";
    });

    document.querySelectorAll("[data-se-tab-jump]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var tab = btn.getAttribute("data-se-tab-jump");
        window.dispatchEvent(new CustomEvent("se-set-tab", { detail: tab }));
      });
    });

    if (window.lucide) window.lucide.createIcons();
  });
})();

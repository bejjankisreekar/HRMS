(() => {
  "use strict";

  const AUTO_DISMISS_MS = 5000;
  const LEAVE_MS = 280;

  function dismissToast(toast) {
    if (!toast || toast.classList.contains("hrms-toast--leaving")) return;
    toast.classList.add("hrms-toast--leaving");
    window.setTimeout(() => toast.remove(), LEAVE_MS);
  }

  function initToasts() {
    document.querySelectorAll("[data-toast]").forEach((toast) => {
      const closeBtn = toast.querySelector("[data-toast-close]");
      closeBtn?.addEventListener("click", (e) => {
        e.preventDefault();
        dismissToast(toast);
      });

      const delay = Number(toast.getAttribute("data-toast-duration")) || AUTO_DISMISS_MS;
      window.setTimeout(() => dismissToast(toast), delay);
    });

    if (window.lucide?.createIcons) {
      window.lucide.createIcons();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initToasts);
  } else {
    initToasts();
  }
})();

function initStaffManagement() {
  "use strict";

  const root = document.getElementById("staff-management");
  if (!root) return;

  let openMenu = null;
  let openBtn = null;

  function closeMenu(menu, btn) {
    if (!menu) return;
    menu.hidden = true;
    menu.classList.remove("is-open");
    menu.style.top = "";
    menu.style.left = "";
    menu.style.right = "";
    if (menu._stfHost && menu.parentElement !== menu._stfHost) {
      menu._stfHost.appendChild(menu);
    }
    if (btn) btn.setAttribute("aria-expanded", "false");
  }

  function closeAllMenus() {
    document.querySelectorAll(".stf-actions-menu").forEach((menu) => {
      const host = menu.closest(".stf-actions");
      const btn = host ? host.querySelector("[data-stf-actions-toggle]") : null;
      closeMenu(menu, btn);
    });
    openMenu = null;
    openBtn = null;
  }

  function positionMenu(btn, menu) {
    const host = btn.closest(".stf-actions");
    if (!menu._stfHost && host) {
      menu._stfHost = host;
    }

    menu.hidden = false;
    menu.classList.add("is-open");

    if (menu.parentElement !== document.body) {
      document.body.appendChild(menu);
    }

    menu.style.visibility = "hidden";
    menu.style.top = "0";
    menu.style.left = "0";

    const btnRect = btn.getBoundingClientRect();
    const menuRect = menu.getBoundingClientRect();
    const gap = 6;
    const pad = 8;

    let top = btnRect.bottom + gap;
    let left = btnRect.right - menuRect.width;

    if (top + menuRect.height > window.innerHeight - pad) {
      top = btnRect.top - menuRect.height - gap;
    }
    if (top < pad) {
      top = pad;
    }
    if (left < pad) {
      left = pad;
    }
    if (left + menuRect.width > window.innerWidth - pad) {
      left = window.innerWidth - menuRect.width - pad;
    }

    menu.style.top = `${Math.round(top)}px`;
    menu.style.left = `${Math.round(left)}px`;
    menu.style.visibility = "";
  }

  function openActionsMenu(btn) {
    const menu = btn.nextElementSibling;
    if (!menu || !menu.classList.contains("stf-actions-menu")) return;

    const isSame = openMenu === menu && !menu.hidden;
    closeAllMenus();
    if (isSame) return;

    positionMenu(btn, menu);
    btn.setAttribute("aria-expanded", "true");
    openMenu = menu;
    openBtn = btn;
  }

  root.querySelectorAll("[data-stf-actions-toggle]").forEach((btn) => {
    btn.setAttribute("aria-expanded", "false");
    btn.setAttribute("aria-haspopup", "true");

    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      openActionsMenu(btn);
    });
  });

  root.addEventListener("click", (e) => {
    if (e.target.closest(".stf-actions-menu")) return;
    closeAllMenus();
  });

  document.addEventListener("click", (e) => {
    if (root.contains(e.target)) return;
    closeAllMenus();
  });

  root.querySelector(".stf-table-scroll")?.addEventListener("scroll", closeAllMenus, { passive: true });
  window.addEventListener("resize", closeAllMenus);
  window.addEventListener("scroll", closeAllMenus, true);

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeAllMenus();
  });

  if (window.lucide) window.lucide.createIcons();
}

document.addEventListener("DOMContentLoaded", initStaffManagement);

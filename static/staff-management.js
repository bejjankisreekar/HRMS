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

// ── Employee Directory: view toggle, bulk actions, columns, saved filters, print ──
function initStaffDirectory() {
  "use strict";
  const root = document.getElementById("staff-management");
  if (!root) return;

  const bulkUrl = root.dataset.bulkUrl;
  const savedUrl = root.dataset.savedUrl;

  function cookie(name) {
    const m = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
    return m ? m.pop() : "";
  }
  function postJSON(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": cookie("csrftoken"), "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify(body || {}),
    });
  }
  function toast(msg, kind) {
    let host = document.getElementById("stf-toasts");
    if (!host) { host = document.createElement("div"); host.id = "stf-toasts"; document.body.appendChild(host); }
    const t = document.createElement("div");
    t.className = "stf-toast stf-toast--" + (kind || "info");
    t.textContent = msg;
    host.appendChild(t);
    requestAnimationFrame(() => t.classList.add("is-in"));
    setTimeout(() => { t.classList.remove("is-in"); setTimeout(() => t.remove(), 300); }, kind === "error" ? 6000 : 4000);
  }

  // ── View toggle ──
  const tableEl = root.querySelector("[data-staff-table]");
  const cardsEl = root.querySelector("[data-staff-cards]");
  function setView(view) {
    const cards = view === "cards";
    if (tableEl) tableEl.hidden = cards;
    if (cardsEl) cardsEl.hidden = !cards;
    root.querySelectorAll("[data-view-toggle]").forEach((b) =>
      b.classList.toggle("is-active", b.dataset.viewToggle === view));
    try { localStorage.setItem("stfView", view); } catch (e) {}
  }
  root.querySelectorAll("[data-view-toggle]").forEach((b) =>
    b.addEventListener("click", () => setView(b.dataset.viewToggle)));
  setView((function () { try { return localStorage.getItem("stfView"); } catch (e) { return null; } })() || "table");

  // ── Dropdowns (saved / columns / export) ──
  root.querySelectorAll("[data-dd-toggle]").forEach((btn) => {
    const menu = btn.nextElementSibling;
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const wasOpen = !menu.hidden;
      root.querySelectorAll(".stf-dd-menu").forEach((m) => (m.hidden = true));
      menu.hidden = wasOpen;
    });
  });
  document.addEventListener("click", () => root.querySelectorAll(".stf-dd-menu").forEach((m) => (m.hidden = true)));
  root.querySelectorAll(".stf-dd-menu").forEach((m) => m.addEventListener("click", (e) => e.stopPropagation()));

  // ── Column visibility ──
  function applyCol(key, visible) {
    root.querySelectorAll('[data-col="' + key + '"]').forEach((c) => c.classList.toggle("stf-col-hidden", !visible));
  }
  let hiddenCols = [];
  try { hiddenCols = JSON.parse(localStorage.getItem("stfCols") || "[]"); } catch (e) {}
  root.querySelectorAll("[data-col-toggle]").forEach((cb) => {
    const key = cb.dataset.colToggle;
    if (hiddenCols.includes(key)) { cb.checked = false; applyCol(key, false); }
    cb.addEventListener("change", () => {
      applyCol(key, cb.checked);
      const set = new Set(hiddenCols);
      cb.checked ? set.delete(key) : set.add(key);
      hiddenCols = [...set];
      try { localStorage.setItem("stfCols", JSON.stringify(hiddenCols)); } catch (e) {}
    });
  });

  // ── Selection + bulk bar ──
  const bar = root.querySelector("[data-bulk-bar]");
  const countEl = root.querySelector("[data-bulk-count]");
  function selectedIds() {
    return [...new Set([...root.querySelectorAll("[data-staff-check]:checked")].map((c) => c.value))];
  }
  function refreshBar() {
    const ids = selectedIds();
    if (countEl) countEl.textContent = ids.length;
    if (bar) bar.hidden = ids.length === 0;
  }
  root.addEventListener("change", (e) => {
    if (e.target.matches("[data-staff-check]")) refreshBar();
    if (e.target.matches("[data-staff-check-all]")) {
      const on = e.target.checked;
      (tableEl || root).querySelectorAll("[data-staff-check]").forEach((c) => (c.checked = on));
      refreshBar();
    }
  });
  root.querySelector("[data-bulk-clear]")?.addEventListener("click", () => {
    root.querySelectorAll("[data-staff-check]").forEach((c) => (c.checked = false));
    const all = root.querySelector("[data-staff-check-all]");
    if (all) all.checked = false;
    refreshBar();
  });

  // ── Run an action (single or bulk) with optimistic UI ──
  function rowsFor(ids) {
    const sel = ids.map((id) => '[data-staff-row][data-staff-id="' + id + '"]').join(",");
    return sel ? [...root.querySelectorAll(sel)] : [];
  }
  function runAction(action, ids, payload) {
    if (!ids.length) { toast("Select at least one employee.", "error"); return; }
    if (action === "delete" && !window.confirm("Delete " + ids.length + " employee(s)? This cannot be undone.")) return;
    const rows = rowsFor(ids);
    rows.forEach((r) => r.classList.add("stf-row-busy"));
    postJSON(bulkUrl, { action: action, userIds: ids, payload: payload || {} })
      .then((r) => r.json().then((d) => ({ ok: r.ok, d })))
      .then(({ ok, d }) => {
        if (!ok) throw new Error(d.error || "Action failed");
        if (action === "reset_password" && d.tempPassword) {
          toast("Temp password: " + d.tempPassword + " (copy it now)", "info");
        } else {
          toast((d.affected || ids.length) + " employee(s) updated.", "success");
          setTimeout(() => window.location.reload(), 700);  // reflect status/removal from source of truth
        }
        rows.forEach((r) => r.classList.remove("stf-row-busy"));
      })
      .catch((err) => {
        rows.forEach((r) => r.classList.remove("stf-row-busy"));
        toast(err.message || "Action failed.", "error");
      });
  }

  root.querySelectorAll("[data-bulk-action]").forEach((b) =>
    b.addEventListener("click", () => runAction(b.dataset.bulkAction, selectedIds())));
  root.querySelector("[data-bulk-status]")?.addEventListener("change", (e) => {
    const val = e.target.value;
    if (val) { runAction("change_status", selectedIds(), { status: val }); e.target.value = ""; }
  });
  // Per-row / per-card single actions (menu buttons relocate to <body>, so delegate on document).
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-staff-action]");
    if (btn) runAction(btn.dataset.staffAction, [btn.dataset.staffId]);
  });

  // ── Print ──
  root.querySelector("[data-print]")?.addEventListener("click", () => window.print());

  // ── Saved filters ──
  const sf = root.querySelector("[data-saved-filters]");
  if (sf && savedUrl) {
    const listEl = sf.querySelector("[data-saved-list]");
    const nameEl = sf.querySelector("[data-saved-name]");
    function renderSaved(filters) {
      if (!filters.length) { listEl.innerHTML = '<p class="stf-dd-empty">No saved filters.</p>'; return; }
      listEl.innerHTML = filters.map((f) =>
        '<div class="stf-saved-row"><a href="?' + (f.query || "") + '">' + f.name +
        '</a><button type="button" class="stf-saved-del" data-del="' + f.id + '" aria-label="Delete">&times;</button></div>').join("");
    }
    fetch(savedUrl, { headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then((r) => r.json()).then((d) => renderSaved(d.filters || [])).catch(() => {});
    sf.querySelector("[data-saved-create]")?.addEventListener("click", () => {
      const name = (nameEl.value || "").trim();
      if (!name) { toast("Name the filter first.", "error"); return; }
      postJSON(savedUrl, { name: name, query: sf.dataset.currentQuery || "" })
        .then((r) => r.json().then((d) => ({ ok: r.ok, d })))
        .then(({ ok, d }) => {
          if (!ok) throw new Error(d.error || "Could not save");
          nameEl.value = "";
          return fetch(savedUrl, { headers: { "X-Requested-With": "XMLHttpRequest" } }).then((r) => r.json());
        })
        .then((d) => { if (d) renderSaved(d.filters || []); toast("Filter saved.", "success"); })
        .catch((err) => toast(err.message, "error"));
    });
    listEl.addEventListener("click", (e) => {
      const del = e.target.closest("[data-del]");
      if (!del) return;
      e.preventDefault();
      postJSON(savedUrl + del.dataset.del + "/delete/", {})
        .then(() => del.closest(".stf-saved-row").remove());
    });
  }

  if (window.lucide) window.lucide.createIcons();
}

document.addEventListener("DOMContentLoaded", initStaffDirectory);

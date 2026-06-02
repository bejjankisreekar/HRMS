function initOrgTreeApp() {
  "use strict";

  const cfg = window.ORG_TREE_CONFIG;
  if (!cfg || typeof d3 === "undefined" || typeof d3.OrgChart === "undefined") return;

  let chart = null;
  let chartData = (cfg.chart && cfg.chart.nodes) || [];
  let highlightId = null;

  const container = document.getElementById("ot-chart-container");
  const canvasWrap = document.getElementById("ot-canvas-wrap");
  const searchInput = document.getElementById("ot-search-input");
  const searchResults = document.getElementById("ot-search-results");
  const panel = document.getElementById("ot-employee-panel");
  const panelBackdrop = document.getElementById("ot-panel-backdrop");
  const moveModal = document.getElementById("ot-move-modal");

  function csrfHeaders() {
    return {
      "Content-Type": "application/json",
      "X-CSRFToken": cfg.csrf,
    };
  }

  function employeeApiUrl(id) {
    return cfg.api.employeeTemplate.replace("__ID__", id);
  }

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s || "";
    return d.innerHTML;
  }

  function statusBadge(n) {
    if (n.isDepartment || n.isTeam || n.isBranch) return "";
    const st = n.status || "active";
    const label = n.statusLabel || "Active";
    return `<span class="ot-status ot-status--${escapeHtml(st)}">${escapeHtml(label)}</span>`;
  }

  function nodeCard(d) {
    const n = d.data;
    const isGroup = n.isDepartment || n.isTeam || n.isBranch;
    const hl = highlightId === n.id ? " is-highlight" : "";
    const groupCls = isGroup ? " ot-node--group" : "";
    const deptBorder = n.departmentColor ? `--dept-accent:${n.departmentColor};` : "";
    const avatarStyle = n.roleColor ? `background:linear-gradient(135deg,${n.roleColor},#4f46e5)` : "";
    const onlineCls = n.online ? "" : " is-offline";
    const avatarInner = n.avatar
      ? `<img src="${escapeHtml(n.avatar)}" alt="">`
      : escapeHtml(n.initials || "?");

    const contactActions =
      !isGroup && (n.email || n.phone)
        ? `<div class="ot-node-actions">
            ${n.email ? `<a href="mailto:${escapeHtml(n.email)}" class="ot-node-action" title="Email" onclick="event.stopPropagation()"><i data-lucide="mail" class="h-3 w-3"></i></a>` : ""}
            ${n.phone ? `<a href="tel:${escapeHtml(n.phone)}" class="ot-node-action" title="Call" onclick="event.stopPropagation()"><i data-lucide="phone" class="h-3 w-3"></i></a>` : ""}
          </div>`
        : "";

    return `
      <div class="ot-node${hl}${groupCls}" data-node-id="${escapeHtml(n.id)}" style="${deptBorder}">
        <div class="ot-node-head">
          <div class="ot-avatar" style="${avatarStyle}">
            ${avatarInner}
            ${!isGroup ? `<span class="ot-online${onlineCls}"></span>` : ""}
          </div>
          <div class="ot-node-head-text">
            <div class="ot-node-name-row">
              <div class="ot-node-name">${escapeHtml(n.name)}</div>
              ${statusBadge(n)}
            </div>
            <div class="ot-node-role">${escapeHtml(n.designation)}</div>
          </div>
          ${contactActions}
        </div>
        <div class="ot-node-meta">
          ${n.department ? `<span>${escapeHtml(n.department)}</span>` : ""}
          ${n.managerName && !isGroup ? `<span>Reports to · ${escapeHtml(n.managerName)}</span>` : ""}
          ${n.employeeId && n.employeeId !== "—" ? `<span>ID · ${escapeHtml(n.employeeId)}</span>` : ""}
          ${n.directReports && !isGroup ? `<span>${n.directReports} direct report(s)</span>` : ""}
        </div>
      </div>`;
  }

  function initChart() {
    if (!container) return;
    container.innerHTML = "";

    chart = new d3.OrgChart()
      .container("#ot-chart-container")
      .data(chartData)
      .nodeWidth(() => 280)
      .nodeHeight(() => 132)
      .childrenMargin(() => 70)
      .compact(false)
      .neighbourMargin(() => 40)
      .siblingsMargin(() => 30)
      .buttonContent(() => "")
      .linkUpdate(function (d, i, arr) {
        d3.select(this)
          .attr("stroke", "url(#ot-link-gradient)")
          .attr("stroke-width", 2)
          .attr("fill", "none")
          .style("filter", "drop-shadow(0 0 4px rgba(139,92,246,0.4))");
      })
      .nodeContent(nodeCard)
      .onNodeClick((d) => {
        const id = d.data.id;
        if (id.startsWith("dept-") || id.startsWith("team-") || id.startsWith("branch-")) return;
        openEmployeePanel(id);
      });

    if (cfg.canEdit) {
      chart
        .draggable(true)
        .dropCriteria((drag, drop) => {
          const dragId = drag.data.id;
          const dropId = drop.data.id;
          if (dragId.startsWith("dept-") || dragId.startsWith("team-") || dragId.startsWith("branch-")) {
            return false;
          }
          if (dropId.startsWith("dept-") || dropId.startsWith("team-") || dropId.startsWith("branch-")) {
            return false;
          }
          return dragId !== dropId;
        })
        .onNodeDrop((drag, drop) => {
          pendingMove = { employeeId: drag.data.id, managerId: drop.data.id };
          showMoveModal(drag.data.name, drop.data.name);
        });
    }

    chart.render();
    ensureLinkGradient();
    if (window.lucide) window.lucide.createIcons();
    updateMinimap();
  }

  function ensureLinkGradient() {
    const svg = container.querySelector("svg");
    if (!svg) return;
    let defs = svg.querySelector("defs");
    if (!defs) {
      defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
      svg.prepend(defs);
    }
    if (!svg.querySelector("#ot-link-gradient")) {
      const grad = document.createElementNS("http://www.w3.org/2000/svg", "linearGradient");
      grad.id = "ot-link-gradient";
      grad.setAttribute("x1", "0%");
      grad.setAttribute("y1", "0%");
      grad.setAttribute("x2", "100%");
      grad.setAttribute("y2", "0%");
      grad.innerHTML =
        '<stop offset="0%" stop-color="#8b5cf6"/><stop offset="100%" stop-color="#22d3ee"/>';
      defs.appendChild(grad);
    }
  }

  let pendingMove = null;

  function showMoveModal(empName, mgrName) {
    if (!moveModal) return;
    moveModal.querySelector("[data-move-text]").textContent =
      `Move “${empName}” to report to “${mgrName}”?`;
    moveModal.hidden = false;
  }

  function hideMoveModal() {
    if (moveModal) moveModal.hidden = true;
    pendingMove = null;
    if (chart) chart.render();
  }

  async function confirmMove() {
    if (!pendingMove) return;
    const res = await fetch(cfg.api.move, {
      method: "POST",
      headers: csrfHeaders(),
      body: JSON.stringify(pendingMove),
    });
    const data = await res.json();
    hideMoveModal();
    if (data.ok) {
      await refreshChart();
    } else {
      alert(data.error || "Could not update hierarchy.");
    }
  }

  async function refreshChart() {
    const params = new URLSearchParams(window.location.search);
    const res = await fetch(`${cfg.api.data}?${params.toString()}`);
    const data = await res.json();
    chartData = data.chart.nodes;
    if (chart) {
      chart.data(chartData).render();
      ensureLinkGradient();
      updateMinimap();
    }
  }

  async function openEmployeePanel(id) {
    if (!panel) return;
    panel.classList.add("is-open");
    panelBackdrop.classList.add("is-open");
    panel.querySelector("[data-panel-body]").innerHTML =
      '<p class="text-sm text-slate-400 p-4">Loading…</p>';

    const res = await fetch(employeeApiUrl(id));
    const emp = await res.json();
    panel.querySelector("[data-panel-title]").textContent = emp.name;
    panel.querySelector("[data-panel-body]").innerHTML = renderPanel(emp);
    if (window.lucide) window.lucide.createIcons();
  }

  function closePanel() {
    panel.classList.remove("is-open");
    panelBackdrop.classList.remove("is-open");
  }

  function renderPanel(emp) {
    const leaveHtml = (emp.leaveBalances || [])
      .map(
        (b) =>
          `<li class="flex justify-between text-xs text-slate-400"><span>${escapeHtml(b.type)}</span><span>${b.used}/${b.total} days</span></li>`
      )
      .join("");
    const reportsHtml = (emp.directReports || [])
      .map((r) => `<li class="text-xs text-slate-300">${escapeHtml(r.name)} · ${escapeHtml(r.designation || "")}</li>`)
      .join("");
    const peersHtml = (emp.peers || [])
      .map((p) => `<li class="text-xs text-slate-300">${escapeHtml(p.name)} · ${escapeHtml(p.designation || "")}</li>`)
      .join("");
    const chainHtml = (emp.reportingChain || [])
      .map((c) => `<li class="text-xs text-violet-300">${escapeHtml(c.name)}</li>`)
      .join("");
    const actionsHtml = (emp.quickActions || [])
      .map(
        (a) =>
          `<a href="${escapeHtml(a.url)}" class="ot-btn-ghost text-xs"><i data-lucide="${escapeHtml(a.icon)}" class="inline h-3 w-3"></i> ${escapeHtml(a.label)}</a>`
      )
      .join("");

    const statusCls = emp.status ? ` ot-status--${emp.status}` : "";

    return `
      <div class="p-5 space-y-4">
        <div class="flex items-center gap-3">
          <div class="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-600 to-indigo-600 text-lg font-bold text-white overflow-hidden">
            ${emp.avatar ? `<img src="${escapeHtml(emp.avatar)}" class="h-full w-full object-cover">` : escapeHtml(emp.initials)}
          </div>
          <div>
            <p class="text-xs text-slate-500">${escapeHtml(emp.employeeId)}</p>
            <p class="text-sm text-violet-300">${escapeHtml(emp.designation)}</p>
            <p class="text-xs text-slate-500">${escapeHtml(emp.department)}</p>
            ${emp.statusLabel ? `<span class="ot-status${statusCls} mt-1 inline-block">${escapeHtml(emp.statusLabel)}</span>` : ""}
          </div>
        </div>
        <div class="flex flex-wrap gap-2">${actionsHtml}</div>
        <div class="grid grid-cols-2 gap-2 text-xs">
          <div class="rounded-lg bg-white/5 p-2"><span class="text-slate-500">Email</span><p class="text-slate-200 truncate"><a href="mailto:${escapeHtml(emp.email)}" class="hover:text-violet-300">${escapeHtml(emp.email)}</a></p></div>
          <div class="rounded-lg bg-white/5 p-2"><span class="text-slate-500">Phone</span><p class="text-slate-200">${emp.phone ? `<a href="tel:${escapeHtml(emp.phone)}" class="hover:text-violet-300">${escapeHtml(emp.phone)}</a>` : "—"}</p></div>
          <div class="rounded-lg bg-white/5 p-2"><span class="text-slate-500">Branch</span><p class="text-slate-200">${escapeHtml(emp.branch)}</p></div>
          <div class="rounded-lg bg-white/5 p-2"><span class="text-slate-500">Shift</span><p class="text-slate-200">${escapeHtml(emp.shift)}</p></div>
        </div>
        <div>
          <h4 class="text-xs font-semibold uppercase text-slate-500">Attendance (${escapeHtml(emp.attendanceSummary.period)})</h4>
          <div class="mt-1 flex gap-3 text-xs">
            <span class="text-emerald-400">Present ${emp.attendanceSummary.present}</span>
            <span class="text-rose-400">Absent ${emp.attendanceSummary.absent}</span>
            <span class="text-amber-400">Half ${emp.attendanceSummary.late}</span>
          </div>
        </div>
        <div>
          <h4 class="text-xs font-semibold uppercase text-slate-500">Leave balance</h4>
          <ul class="mt-1 space-y-1">${leaveHtml || '<li class="text-xs text-slate-500">No balances</li>'}</ul>
        </div>
        <div>
          <h4 class="text-xs font-semibold uppercase text-slate-500">Reporting chain</h4>
          <ol class="mt-1 list-decimal list-inside">${chainHtml || '<li class="text-xs text-slate-500">—</li>'}</ol>
        </div>
        <div>
          <h4 class="text-xs font-semibold uppercase text-slate-500">Peers</h4>
          <ul class="mt-1 space-y-1">${peersHtml || '<li class="text-xs text-slate-500">None</li>'}</ul>
        </div>
        <div>
          <h4 class="text-xs font-semibold uppercase text-slate-500">Direct reports</h4>
          <ul class="mt-1 space-y-1">${reportsHtml || '<li class="text-xs text-slate-500">None</li>'}</ul>
        </div>
        <div class="flex flex-wrap gap-2 pt-2">
          <button type="button" class="ot-btn-ghost text-xs" data-panel-close>Close</button>
        </div>
      </div>`;
  }

  function updateMinimap() {
    const mini = document.getElementById("ot-minimap");
    const svg = container?.querySelector("svg");
    if (!mini || !svg) return;
    mini.innerHTML = "";
    const clone = svg.cloneNode(true);
    clone.removeAttribute("width");
    clone.removeAttribute("height");
    clone.style.width = "100%";
    clone.style.height = "100%";
    clone.style.pointerEvents = "none";
    mini.appendChild(clone);
  }

  function focusNode(id) {
    highlightId = id;
    if (chart) {
      chart.data(chartData).render();
      ensureLinkGradient();
      try {
        chart.setCentered(id).render();
      } catch (e) {
        chart.fit();
      }
    }
  }

  let searchTimer;
  if (searchInput) {
    searchInput.addEventListener("input", () => {
      clearTimeout(searchTimer);
      const q = searchInput.value.trim();
      if (q.length < 2) {
        searchResults.classList.remove("is-open");
        return;
      }
      searchTimer = setTimeout(async () => {
        const res = await fetch(`${cfg.api.search}?q=${encodeURIComponent(q)}`);
        const data = await res.json();
        searchResults.innerHTML = (data.results || [])
          .map(
            (r) =>
              `<button type="button" class="ot-search-item" data-id="${escapeHtml(r.id)}">
                <span class="font-semibold text-white">${escapeHtml(r.name)}</span>
                <span class="block text-[10px] text-slate-500">${escapeHtml(r.designation)} · ${escapeHtml(r.department)}</span>
              </button>`
          )
          .join("");
        searchResults.classList.add("is-open");
        searchResults.querySelectorAll(".ot-search-item").forEach((btn) => {
          btn.addEventListener("click", () => {
            focusNode(btn.dataset.id);
            openEmployeePanel(btn.dataset.id);
            searchResults.classList.remove("is-open");
          });
        });
        if (data.results.length === 1) {
          focusNode(data.results[0].id);
        }
      }, 280);
    });
  }

  document.querySelectorAll("[data-focus-id]").forEach((btn) => {
    btn.addEventListener("click", () => {
      focusNode(btn.dataset.focusId);
      openEmployeePanel(btn.dataset.focusId);
    });
  });

  document.getElementById("ot-focus-me")?.addEventListener("click", () => {
    if (cfg.currentUserId) {
      focusNode(cfg.currentUserId);
      openEmployeePanel(cfg.currentUserId);
    }
  });

  document.getElementById("ot-print")?.addEventListener("click", () => window.print());

  document.getElementById("ot-expand-all")?.addEventListener("click", () => chart && chart.expandAll().fit());
  document.getElementById("ot-collapse-all")?.addEventListener("click", () => chart && chart.collapseAll().fit());
  document.getElementById("ot-fit")?.addEventListener("click", () => chart && chart.fit());
  document.getElementById("ot-zoom-in")?.addEventListener("click", () => chart && chart.zoomIn && chart.zoomIn());
  document.getElementById("ot-zoom-out")?.addEventListener("click", () => chart && chart.zoomOut && chart.zoomOut());

  document.getElementById("ot-fullscreen")?.addEventListener("click", () => {
    canvasWrap.classList.toggle("is-fullscreen");
    setTimeout(() => chart && chart.fit(), 200);
  });

  document.getElementById("ot-export-png")?.addEventListener("click", () => {
    if (chart && chart.exportImg) {
      chart.exportImg({ full: true, save: true, filename: "organization-chart" });
    } else {
      window.print();
    }
  });

  document.getElementById("ot-export-link")?.addEventListener("click", (e) => {
    e.preventDefault();
    const params = new URLSearchParams(window.location.search);
    window.location.href = `${cfg.api.export}?${params.toString()}`;
  });

  panelBackdrop?.addEventListener("click", closePanel);
  document.addEventListener("click", (e) => {
    if (e.target.matches("[data-panel-close]")) closePanel();
    if (e.target.matches("[data-move-cancel]")) hideMoveModal();
    if (e.target.matches("[data-move-confirm]")) confirmMove();
  });

  document.getElementById("ot-team-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    const fd = new FormData(form);
    const res = await fetch(cfg.api.team, {
      method: "POST",
      headers: { "X-CSRFToken": cfg.csrf },
      body: fd,
    });
    const data = await res.json();
    if (data.ok) window.location.reload();
    else alert("Could not create team.");
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closePanel();
      hideMoveModal();
      canvasWrap.classList.remove("is-fullscreen");
    }
    if (e.key === "+" && chart && chart.zoomIn) chart.zoomIn();
    if (e.key === "-" && chart && chart.zoomOut) chart.zoomOut();
    if (e.key === "0" && chart) chart.fit();
  });

  initChart();
  if (cfg.focusNodeId) {
    setTimeout(() => {
      focusNode(cfg.focusNodeId);
    }, 600);
  }
  setTimeout(() => chart && chart.fit(), 400);
}

if (document.readyState === "complete") {
  initOrgTreeApp();
} else {
  window.addEventListener("load", initOrgTreeApp);
}

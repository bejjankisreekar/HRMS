(function () {
  function csrf() {
    var m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : "";
  }
  function post(action, data) {
    var fd = new FormData();
    fd.append("action", action);
    Object.keys(data).forEach(function (k) { fd.append(k, data[k]); });
    return fetch(window.FCC_CONFIG.apiUrl, {
      method: "POST",
      headers: { "X-CSRFToken": csrf(), "X-Requested-With": "XMLHttpRequest" },
      body: fd,
    }).then(function (r) { return r.json(); });
  }

  document.querySelectorAll(".fcc-global-toggle").forEach(function (el) {
    el.addEventListener("change", function () {
      post("global_toggle", { feature_id: el.dataset.featureId, enabled: el.checked ? "true" : "false" })
        .then(function (res) {
          if (!res.ok && res.error) { alert(res.error); el.checked = !el.checked; }
        });
    });
  });

  document.querySelectorAll(".fcc-plan-toggle").forEach(function (el) {
    el.addEventListener("change", function () {
      post("plan_toggle", { plan_id: el.dataset.planId, feature_id: el.dataset.featureId, enabled: el.checked ? "true" : "false" });
    });
  });

  document.querySelectorAll(".fcc-module-toggle").forEach(function (el) {
    el.addEventListener("change", function () {
      post("module_toggle", { module_id: el.dataset.moduleId, enabled: el.checked ? "true" : "false" });
    });
  });

  document.querySelectorAll(".fcc-page-toggle").forEach(function (el) {
    el.addEventListener("change", function () {
      post("page_toggle", { page_id: el.dataset.pageId, enabled: el.checked ? "true" : "false" });
    });
  });

  document.querySelectorAll(".fcc-nav-toggle").forEach(function (el) {
    el.addEventListener("change", function () {
      post("nav_toggle", { item_id: el.dataset.itemId, visible: el.checked ? "true" : "false" });
    });
  });

  document.querySelectorAll(".fcc-role-toggle").forEach(function (el) {
    el.addEventListener("change", function () {
      post("role_toggle", { feature_id: el.dataset.featureId, role: el.dataset.role, allowed: el.checked ? "true" : "false" });
    });
  });

  document.querySelectorAll(".fcc-field-toggle").forEach(function (el) {
    el.addEventListener("change", function () {
      post("field_toggle", { field_id: el.dataset.fieldId, visible: el.checked ? "true" : "false" });
    });
  });

  document.querySelectorAll(".fcc-addon-toggle").forEach(function (el) {
    el.addEventListener("change", function () {
      post("addon_toggle", { addon_id: el.dataset.addonId, active: el.checked ? "true" : "false" });
    });
  });

  document.querySelectorAll(".fcc-org-toggle").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var row = btn.closest(".fcc-org-row");
      post("org_toggle", {
        org_id: row.dataset.orgId,
        feature_id: row.dataset.featureId,
        mode: btn.dataset.mode,
      }).then(function () { window.location.reload(); });
    });
  });

  document.querySelectorAll(".fcc-nav-list").forEach(function (list) {
    var dragEl = null;
    list.querySelectorAll(".fcc-nav-item").forEach(function (item) {
      item.addEventListener("dragstart", function () { dragEl = item; });
      item.addEventListener("dragend", function () {
        dragEl = null;
        var ids = Array.from(list.querySelectorAll(".fcc-nav-item")).map(function (el) { return el.dataset.itemId; });
        fetch(window.FCC_CONFIG.apiUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
          body: JSON.stringify({ action: "nav_reorder", item_ids: ids }),
        });
      });
      item.addEventListener("dragover", function (e) {
        e.preventDefault();
        if (!dragEl || dragEl === item) return;
        var rect = item.getBoundingClientRect();
        list.insertBefore(dragEl, e.clientY > rect.top + rect.height / 2 ? item.nextSibling : item);
      });
    });
  });
})();

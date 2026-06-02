(function () {
  "use strict";

  function csrf() {
    var m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : "";
  }

  function api(data) {
    return fetch(window.PLAN_MATRIX.apiUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify(data),
    }).then(function (r) {
      return r.json().then(function (body) {
        if (!r.ok && body && !body.error) {
          body.error = "Request failed (" + r.status + ")";
        }
        return body;
      }).catch(function () {
        return { ok: false, error: "Request failed (" + r.status + ")" };
      });
    });
  }

  /* ── Toast ─────────────────────────────────────────────────── */
  var toastRoot = document.getElementById("pmx-toast-root");
  var toastTimer = null;

  function showToast(message, type) {
    if (!toastRoot) return;
    if (toastTimer) clearTimeout(toastTimer);
    toastRoot.innerHTML = "";
    var toast = document.createElement("div");
    toast.className = "pmx-toast pmx-toast--" + (type || "success");
    toast.innerHTML =
      '<svg class="pmx-toast__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">' +
      (type === "error"
        ? '<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>'
        : '<path d="M20 6 9 17l-5-5"/>') +
      "</svg><span>" + message + "</span>";
    toastRoot.appendChild(toast);
    requestAnimationFrame(function () { toast.classList.add("is-visible"); });
    toastTimer = setTimeout(function () {
      toast.classList.remove("is-visible");
      setTimeout(function () { if (toast.parentNode) toast.remove(); }, 280);
    }, 2200);
  }

  function switchEl(input) { return input.closest(".pmx-switch"); }

  function setSwitchLoading(input, loading) {
    var sw = switchEl(input);
    if (sw) sw.classList.toggle("is-loading", loading);
    input.disabled = loading;
  }

  function flashSwitchSuccess(input) {
    var sw = switchEl(input);
    if (!sw) return;
    sw.classList.add("is-success");
    setTimeout(function () { sw.classList.remove("is-success"); }, 600);
  }

  /* ── Feature toggles ─────────────────────────────────────── */
  function syncSwitchDisabled(input, disabled) {
    input.disabled = disabled;
    var row = input.closest(".pmx-feat-row");
    if (row) row.classList.toggle("is-disabled", disabled);
  }

  function setChildren(parentKey, planId, enabled) {
    document.querySelectorAll('.pmx-feat-row[data-parent-key="' + parentKey + '"]').forEach(function (row) {
      var cb = row.querySelector('.pmx-toggle[data-plan-id="' + planId + '"]');
      if (cb) {
        cb.checked = enabled;
        syncSwitchDisabled(cb, !enabled);
      }
    });
  }

  document.querySelectorAll(".pmx-toggle").forEach(function (el) {
    var row = el.closest(".pmx-feat-row");
    var parentKey = row && row.dataset.parentKey;
    if (parentKey) {
      var parentRow = document.querySelector('.pmx-feat-row[data-feature-key="' + parentKey + '"]');
      if (parentRow) {
        var parentCb = parentRow.querySelector('.pmx-toggle[data-plan-id="' + el.dataset.planId + '"]');
        if (parentCb && !parentCb.checked) syncSwitchDisabled(el, true);
      }
    }

    el.addEventListener("change", function () {
      var enabled = el.checked;
      var featLabel = row && row.querySelector(".pmx-feat-name")
        ? row.querySelector(".pmx-feat-name").textContent.trim()
        : "Feature";

      setSwitchLoading(el, true);
      api({
        action: "toggle",
        plan_id: el.dataset.planId,
        feature_id: el.dataset.featureId,
        enabled: enabled,
      }).then(function (res) {
        setSwitchLoading(el, false);
        if (!res.ok) {
          el.checked = !enabled;
          showToast(res.error || "Failed to save", "error");
          return;
        }
        flashSwitchSuccess(el);
        showToast(featLabel + " " + (enabled ? "enabled" : "disabled"), "success");
        if (res.feature_key) setChildren(res.feature_key, el.dataset.planId, enabled);
      }).catch(function () {
        setSwitchLoading(el, false);
        el.checked = !enabled;
        showToast("Network error — please retry", "error");
      });
    });
  });

  document.querySelectorAll(".pmx-bulk-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var enabled = btn.dataset.enableAll === "1";
      if (!confirm((enabled ? "Enable" : "Disable") + " all features for this plan?")) return;
      api({ action: "bulk_column", plan_id: btn.dataset.planId, enabled: enabled }).then(function () {
        location.reload();
      });
    });
  });

  /* ── Plan card edit / save ───────────────────────────────── */
  function planFieldControls(planId) {
    var map = {};
    document.querySelectorAll('.pmx-plan-setting[data-plan-id="' + planId + '"]').forEach(function (input) {
      map[input.dataset.field] = input;
    });
    return map;
  }

  function showCardView(planId) {
    var view = document.querySelector('[data-card-view="' + planId + '"]');
    var edit = document.querySelector('[data-card-edit="' + planId + '"]');
    if (view) view.classList.remove("is-hidden");
    if (edit) edit.classList.add("is-hidden");
  }

  function showCardEdit(planId) {
    var view = document.querySelector('[data-card-view="' + planId + '"]');
    var edit = document.querySelector('[data-card-edit="' + planId + '"]');
    if (view) view.classList.add("is-hidden");
    if (edit) edit.classList.remove("is-hidden");
  }

  function markDirty(planId) {
    document.querySelectorAll('.pmx-plan-setting[data-plan-id="' + planId + '"]').forEach(function (input) {
      input.classList.add("is-dirty");
    });
    var btn = document.querySelector('.pmx-save-btn[data-plan-id="' + planId + '"]');
    if (btn) btn.disabled = false;
  }

  function updateCardDisplay(planId, res) {
    var priceEl = document.querySelector('[data-display-price="' + planId + '"]');
    if (priceEl && res.monthly_price_inr != null) {
      priceEl.innerHTML = "₹" + Math.round(res.monthly_price_inr).toLocaleString("en-IN") + "<small>/mo</small>";
    }
    var empEl = document.querySelector('[data-display-employees="' + planId + '"]');
    if (empEl && res.employee_label) empEl.textContent = res.employee_label;
    var storEl = document.querySelector('[data-display-storage="' + planId + '"]');
    if (storEl && res.storage_label) storEl.textContent = res.storage_label;
  }

  document.querySelectorAll(".pmx-card-edit").forEach(function (btn) {
    btn.addEventListener("click", function () { showCardEdit(btn.dataset.planId); });
  });

  document.querySelectorAll(".pmx-card-cancel").forEach(function (btn) {
    btn.addEventListener("click", function () { showCardView(btn.dataset.planId); });
  });

  document.querySelectorAll(".pmx-plan-setting").forEach(function (input) {
    input.addEventListener("input", function () { markDirty(input.dataset.planId); });
  });

  document.querySelectorAll(".pmx-save-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var planId = btn.dataset.planId;
      var fields = planFieldControls(planId);
      btn.disabled = true;
      btn.classList.add("is-saving");
      var orig = btn.textContent;

      api({
        action: "update_plan_settings",
        plan_id: planId,
        monthly_price_inr: fields.monthly_price_inr ? fields.monthly_price_inr.value : "",
        employee_limit: fields.employee_limit ? fields.employee_limit.value : "",
        storage_limit_mb: fields.storage_limit_mb ? fields.storage_limit_mb.value : "",
      }).then(function (res) {
        btn.classList.remove("is-saving");
        if (!res.ok) {
          btn.disabled = false;
          showToast(res.error || "Save failed", "error");
          return;
        }
        document.querySelectorAll('.pmx-plan-setting[data-plan-id="' + planId + '"]').forEach(function (i) {
          i.classList.remove("is-dirty");
        });
        updateCardDisplay(planId, res);
        btn.classList.add("is-saved");
        btn.textContent = "Saved";
        showToast("Plan settings updated", "success");
        setTimeout(function () {
          btn.classList.remove("is-saved");
          btn.textContent = orig;
          btn.disabled = true;
          showCardView(planId);
        }, 1000);
      }).catch(function () {
        btn.classList.remove("is-saving");
        btn.disabled = false;
        showToast("Save failed", "error");
      });
    });
  });

  /* ── Category collapse ───────────────────────────────────── */
  function setCategoryExpanded(catId, expanded) {
    var toggle = document.querySelector('.pmx-cat-toggle[data-category="' + catId + '"]');
    if (toggle) toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
    document.querySelectorAll('.pmx-feat-row[data-category="' + catId + '"]').forEach(function (row) {
      if (expanded && !row.classList.contains("is-filtered")) {
        row.classList.remove("is-hidden");
      } else if (!expanded) {
        row.classList.add("is-hidden");
      }
    });
  }

  document.querySelectorAll(".pmx-cat-toggle").forEach(function (btn) {
    btn.addEventListener("click", function () {
      setCategoryExpanded(btn.dataset.category, btn.getAttribute("aria-expanded") !== "true");
    });
  });

  /* ── Category sidebar navigation ─────────────────────────── */
  var matrixScroll = document.getElementById("pmx-matrix-scroll");

  document.querySelectorAll(".pmx-cat-nav__item").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var catId = btn.dataset.jump;
      document.querySelectorAll(".pmx-cat-nav__item").forEach(function (b) {
        b.classList.toggle("is-active", b === btn);
      });
      setCategoryExpanded(catId, true);
      var el = document.getElementById(catId);
      if (el && matrixScroll) {
        matrixScroll.scrollTo({ top: el.offsetTop - 8, behavior: "smooth" });
      }
    });
  });

  /* ── Feature search ──────────────────────────────────────── */
  var searchInput = document.getElementById("pmx-feature-search");

  if (searchInput) {
    searchInput.addEventListener("input", function () {
      var q = searchInput.value.toLowerCase().trim();
      document.querySelectorAll(".pmx-feat-row").forEach(function (row) {
        var match = !q || (row.dataset.featureName || "").indexOf(q) !== -1;
        row.classList.toggle("is-filtered", !match);
        if (!match) {
          row.classList.add("is-hidden");
        } else {
          var catId = row.dataset.category;
          var toggle = document.querySelector('.pmx-cat-toggle[data-category="' + catId + '"]');
          if (q || (toggle && toggle.getAttribute("aria-expanded") === "true")) {
            row.classList.remove("is-hidden");
          }
        }
      });
    });
  }
})();

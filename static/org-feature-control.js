(function () {

  function csrf() {

    var m = document.cookie.match(/csrftoken=([^;]+)/);

    return m ? m[1] : "";

  }



  function api(data) {

    return fetch(window.ORG_FC.apiUrl, {

      method: "POST",

      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },

      body: JSON.stringify(Object.assign({ org_id: window.ORG_FC.orgId }, data)),

    }).then(function (r) { return r.json(); });

  }



  function updateMatrixBadges(row, enabled) {

    var badges = row.querySelector(".org-fc-matrix__status-badges");

    if (!badges) return;

    var inPlan = row.querySelector(".org-fc-matrix__plan-cell.is-included") !== null;

    var html = "";

    if (!enabled) {

      html = '<span class="org-fc-matrix__badge org-fc-matrix__badge--off">Off</span>';

      html += '<span class="org-fc-matrix__badge org-fc-matrix__badge--override">Override</span>';

    } else if (!inPlan) {

      html = '<span class="org-fc-matrix__badge org-fc-matrix__badge--compl">Complimentary</span>';

      html += '<span class="org-fc-matrix__badge org-fc-matrix__badge--override">Override</span>';

    } else {

      html = '<span class="org-fc-matrix__badge org-fc-matrix__badge--override">Override</span>';

    }

    badges.innerHTML = html;

  }



  function applyChildState(parentKey, parentEnabled) {

    document.querySelectorAll('[data-parent-key="' + parentKey + '"]').forEach(function (childRow) {

      var toggle = childRow.querySelector(".ofc-feature-toggle");

      if (!toggle) return;

      if (!parentEnabled) {

        toggle.checked = false;

        toggle.disabled = true;

        childRow.classList.add("is-disabled-parent");

        updateMatrixBadges(childRow, false);

      } else {

        toggle.disabled = false;

        childRow.classList.remove("is-disabled-parent");

      }

    });

  }



  document.querySelectorAll(".ofc-feature-toggle").forEach(function (el) {

    el.addEventListener("change", function () {

      var listRow = el.closest(".ofc-feature-row");

      var matrixRow = el.closest(".org-fc-matrix__row");

      var row = listRow || matrixRow;

      api({ action: "toggle", feature_id: el.dataset.featureId, enabled: el.checked }).then(function (res) {

        if (!res.ok) { el.checked = !el.checked; alert(res.error || "Failed"); return; }

        if (listRow) {

          var status = listRow.querySelector(".ofc-feature-row__status");

          if (status) {

            status.textContent = el.checked ? "Enabled" : "Disabled";

            status.classList.toggle("is-on", el.checked);

            status.classList.toggle("is-off", !el.checked);

          }

        }

        if (matrixRow) {

          updateMatrixBadges(matrixRow, el.checked);

        }

        if (!el.checked) {

          document.querySelectorAll('.ofc-feature-row[data-parent-key="' + res.feature_key + '"] .ofc-feature-toggle, .org-fc-matrix__row[data-parent-key="' + res.feature_key + '"] .ofc-feature-toggle').forEach(function (child) {

            child.checked = false;

            child.disabled = true;

            var s = child.closest(".ofc-feature-row, .org-fc-matrix__row");

            if (s) s.classList.add("is-disabled-parent");

            if (s && s.classList.contains("org-fc-matrix__row")) updateMatrixBadges(s, false);

          });

        } else {

          document.querySelectorAll('.ofc-feature-row[data-parent-key="' + res.feature_key + '"] .ofc-feature-toggle, .org-fc-matrix__row[data-parent-key="' + res.feature_key + '"] .ofc-feature-toggle').forEach(function (child) {

            child.disabled = false;

            var s = child.closest(".ofc-feature-row, .org-fc-matrix__row");

            if (s) s.classList.remove("is-disabled-parent");

          });

        }

      });

    });

  });



  document.querySelectorAll("[data-bulk]").forEach(function (btn) {

    btn.addEventListener("click", function () {

      var bulk = btn.dataset.bulk;

      if (bulk === "reset_plan" && !confirm("Clear all organization overrides and revert to plan defaults?")) return;

      if (bulk === "disable_all" && !confirm("Disable all features for this organization?")) return;

      if (bulk === "enable_all" && !confirm("Enable all features for this organization?")) return;

      var payload = { action: bulk === "reset_plan" ? "reset_plan" : "bulk_all", enabled: bulk === "enable_all" };

      if (bulk === "reset_plan" && window.ORG_FC.redirectOnReset) payload.redirect = true;

      api(payload).then(function (res) {

        if (res.ok) location.reload();

        else alert(res.error || "Failed");

      });

    });

  });



  document.querySelectorAll("[data-category-enable], [data-category-disable]").forEach(function (btn) {

    btn.addEventListener("click", function () {

      var enabled = btn.hasAttribute("data-category-enable");

      var catId = btn.getAttribute("data-category-enable") || btn.getAttribute("data-category-disable");

      api({ action: "bulk_category", category_id: catId, enabled: enabled }).then(function () { location.reload(); });

    });

  });



  function formatLimit(val) {

    return val === null || val === undefined || val === "" ? "Unlimited" : String(val);

  }



  document.querySelectorAll(".ofc-limit-input").forEach(function (input) {

    function saveLimit() {

      api({

        action: "update_limit",

        field: input.dataset.limitField,

        value: input.value,

      }).then(function (res) {

        if (!res.ok) { alert(res.error || "Save failed"); return; }

        input.classList.add("is-saved");

        var eff = document.querySelector('[data-effective-for="' + input.dataset.limitField + '"]');

        if (eff) eff.textContent = "Active: " + formatLimit(res.effective);

        setTimeout(function () { input.classList.remove("is-saved"); }, 1200);

      });

    }

    input.addEventListener("change", saveLimit);

    input.addEventListener("blur", saveLimit);

  });



  var resetLimitsBtn = document.querySelector("[data-limits-reset]");

  if (resetLimitsBtn) {

    resetLimitsBtn.addEventListener("click", function () {

      if (!confirm("Clear all limit overrides and revert to plan defaults?")) return;

      api({ action: "reset_limits" }).then(function (res) {

        if (res.ok) location.reload();

        else alert(res.error || "Failed");

      });

    });

  }

})();


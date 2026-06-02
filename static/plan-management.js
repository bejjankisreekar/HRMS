(function () {
  function csrf() {
    var m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : "";
  }

  document.querySelectorAll(".pm-feature-grid").forEach(function (grid) {
    var planId = grid.dataset.planId;
    grid.querySelectorAll("input[type=checkbox]").forEach(function (cb) {
      cb.addEventListener("change", function () {
        var fd = new FormData();
        fd.append("feature_id", cb.dataset.featureId);
        fd.append("enabled", cb.checked ? "true" : "false");
        fetch("/dashboard/super/plans/" + planId + "/features/toggle/", {
          method: "POST",
          headers: { "X-CSRFToken": csrf(), "X-Requested-With": "XMLHttpRequest" },
          body: fd,
        });
      });
    });
  });

  document.querySelectorAll(".pm-menu-list").forEach(function (list) {
    var planId = list.dataset.planId;
    var dragEl = null;

    list.querySelectorAll(".pm-menu-item").forEach(function (item) {
      item.addEventListener("dragstart", function () {
        dragEl = item;
        item.classList.add("is-dragging");
      });
      item.addEventListener("dragend", function () {
        item.classList.remove("is-dragging");
        dragEl = null;
        var ids = Array.from(list.querySelectorAll(".pm-menu-item")).map(function (el) {
          return el.dataset.itemId;
        });
        fetch("/dashboard/super/plans/" + planId + "/menu/reorder/", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrf(),
          },
          body: JSON.stringify({ item_ids: ids }),
        });
      });
      item.addEventListener("dragover", function (e) {
        e.preventDefault();
        if (!dragEl || dragEl === item) return;
        var rect = item.getBoundingClientRect();
        var after = e.clientY > rect.top + rect.height / 2;
        list.insertBefore(dragEl, after ? item.nextSibling : item);
      });
    });
  });
})();

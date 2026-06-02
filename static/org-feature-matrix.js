(function () {
  var search = document.getElementById("org-fc-search");
  if (search) {
    search.addEventListener("input", function () {
      var q = search.value.trim().toLowerCase();
      document.querySelectorAll(".org-fc-matrix__row[data-search]").forEach(function (row) {
        var match = !q || row.dataset.search.indexOf(q) !== -1;
        row.classList.toggle("is-hidden", !match);
      });
      document.querySelectorAll(".org-fc-matrix__cat-row").forEach(function (catRow) {
        var cat = catRow.id.replace("org-fc-cat-", "");
        var visible = document.querySelector(
          '.org-fc-matrix__row[data-cat="' + cat + '"]:not(.is-hidden)'
        );
        catRow.classList.toggle("is-hidden", !visible);
      });
    });
  }

  document.querySelectorAll("[data-cat-toggle]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var cat = btn.dataset.catToggle;
      var expanded = btn.getAttribute("aria-expanded") !== "false";
      btn.setAttribute("aria-expanded", expanded ? "false" : "true");
      document.querySelectorAll('.org-fc-matrix__row[data-cat="' + cat + '"]').forEach(function (row) {
        row.classList.toggle("is-hidden", expanded);
      });
    });
  });
})();

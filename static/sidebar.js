(() => {
  "use strict";

  function getSearchData() {
    const el = document.getElementById("hrms-sidebar-search-data");
    if (!el) return [];
    try {
      return JSON.parse(el.textContent);
    } catch {
      return [];
    }
  }

  const searchData = getSearchData();

  function filterSearch(q) {
    const query = (q || "").trim().toLowerCase();
    if (!query) return searchData.slice(0, 8);
    return searchData
      .filter(
        (item) =>
          item.label.toLowerCase().includes(query) ||
          item.group.toLowerCase().includes(query) ||
          (item.keywords && item.keywords.includes(query))
      )
      .slice(0, 12);
  }

  function renderSearchResults(container, items) {
    if (!container) return;
    if (!items.length) {
      container.innerHTML = '<p class="px-3 py-2 text-xs text-white/50">No results</p>';
      container.classList.remove("hidden");
      return;
    }
    container.innerHTML = items
      .map(
        (item) =>
          `<a href="${item.url}" class="hrms-sidebar-search__result" role="option">
            <i data-lucide="${item.icon}" class="inline h-3.5 w-3.5 mr-2"></i>
            ${item.label}
            <span class="float-right text-[10px] opacity-50">${item.group}</span>
          </a>`
      )
      .join("");
    container.classList.remove("hidden");
    if (window.lucide?.createIcons) window.lucide.createIcons();
  }

  const searchInput = document.getElementById("hrms-sidebar-search-input");
  const searchResults = document.getElementById("hrms-sidebar-search-results");

  if (searchInput) {
    searchInput.addEventListener("input", () => {
      renderSearchResults(searchResults, filterSearch(searchInput.value));
    });
    searchInput.addEventListener("focus", () => {
      renderSearchResults(searchResults, filterSearch(searchInput.value));
    });
    document.addEventListener("click", (e) => {
      if (!e.target.closest(".hrms-sidebar-search")) {
        searchResults?.classList.add("hidden");
      }
    });

    document.addEventListener("keydown", (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        searchInput.focus();
        renderSearchResults(searchResults, filterSearch(searchInput.value));
      }
    });
  }

  /* Sidebar profile toggle */
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-sidebar-profile-toggle]");
    if (btn) {
      e.preventDefault();
      document.querySelector("[data-sidebar-profile-menu]")?.classList.toggle("hidden");
    }
  });

  /* Collapsible nav groups (e.g. Payroll section) */
  function navGroupStorageKey(groupId) {
    return `hrms-nav-group-expanded:${groupId}`;
  }

  document.querySelectorAll("[data-nav-group-toggle]").forEach((btn) => {
    const group = btn.closest("[data-nav-group]");
    if (!group) return;
    const groupId = group.getAttribute("data-nav-group");
    const stored = window.localStorage.getItem(navGroupStorageKey(groupId));
    const expanded = stored !== null ? stored === "1" : group.hasAttribute("data-expanded");
    if (expanded) {
      group.setAttribute("data-expanded", "true");
    } else {
      group.removeAttribute("data-expanded");
    }
    btn.setAttribute("aria-expanded", expanded ? "true" : "false");
  });

  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-nav-group-toggle]");
    if (!btn) return;
    e.preventDefault();
    const group = btn.closest("[data-nav-group]");
    if (!group) return;
    const groupId = group.getAttribute("data-nav-group");
    const isExpanded = group.getAttribute("data-expanded") === "true";
    if (isExpanded) {
      group.removeAttribute("data-expanded");
    } else {
      group.setAttribute("data-expanded", "true");
    }
    btn.setAttribute("aria-expanded", isExpanded ? "false" : "true");
    window.localStorage.setItem(navGroupStorageKey(groupId), isExpanded ? "0" : "1");
  });

})();

(() => {
  const root = document.documentElement;
  const body = document.body;

  const SIDEBAR_KEY = "hrms.sidebar.collapsed";
  const THEME_KEY = "hrms.theme";

  function setCollapsed(collapsed) {
    body.classList.toggle("sidebar-collapsed", collapsed);
    document.querySelectorAll("[data-sidebar-toggle] i[data-lucide]").forEach((icon) => {
      icon.setAttribute("data-lucide", collapsed ? "panel-left" : "panel-left-close");
    });
    if (window.lucide?.createIcons) window.lucide.createIcons();
    try { localStorage.setItem(SIDEBAR_KEY, collapsed ? "1" : "0"); } catch (_) {}
  }

  function getCollapsed() {
    try { return localStorage.getItem(SIDEBAR_KEY) === "1"; } catch (_) { return false; }
  }

  function setTheme(theme) {
    root.classList.toggle("dark", theme === "dark");
    try { localStorage.setItem(THEME_KEY, theme); } catch (_) {}
  }

  function getTheme() {
    try { return localStorage.getItem(THEME_KEY); } catch (_) { return null; }
  }

  // Sidebar collapse
  document.addEventListener("click", (e) => {
    const toggle = e.target.closest("[data-sidebar-toggle]");
    if (!toggle) return;
    e.preventDefault();
    setCollapsed(!body.classList.contains("sidebar-collapsed"));
  });

  // Mobile sidebar
  document.addEventListener("click", (e) => {
    const openBtn = e.target.closest("[data-mobile-sidebar-open]");
    const closeBtn = e.target.closest("[data-mobile-sidebar-close]");
    const overlay = e.target.closest("[data-mobile-overlay]");

    if (openBtn) {
      e.preventDefault();
      body.classList.add("mobile-sidebar-open");
    }
    if (closeBtn || overlay) {
      e.preventDefault();
      body.classList.remove("mobile-sidebar-open");
    }
  });

  // Profile dropdown
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-profile-toggle]");
    const menu = document.querySelector("[data-profile-menu]");

    if (btn) {
      e.preventDefault();
      menu?.classList.toggle("hidden");
      return;
    }

    if (menu && !menu.classList.contains("hidden")) {
      const inside = e.target.closest("[data-profile-menu]") || e.target.closest("[data-profile-toggle]");
      if (!inside) menu.classList.add("hidden");
    }
  });

  // Theme toggle
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-theme-toggle]");
    if (!btn) return;
    e.preventDefault();
    const isDark = root.classList.contains("dark");
    setTheme(isDark ? "light" : "dark");
  });

  // Init persisted states
  setCollapsed(getCollapsed());
  const theme = getTheme();
  if (theme === "dark" || theme === "light") setTheme(theme);

  // Lucide icons (if loaded)
  window.addEventListener("DOMContentLoaded", () => {
    if (window.lucide?.createIcons) window.lucide.createIcons();
  });
})();


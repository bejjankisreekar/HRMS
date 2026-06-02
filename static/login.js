(() => {
  function readPortals() {
    const el = document.getElementById("login-portals-data");
    if (!el) return [];
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      console.warn("HRMS login: could not parse portal data", e);
      return [];
    }
  }

  function refreshLucide(root) {
    if (typeof lucide === "undefined" || !lucide.createIcons) return;
    lucide.createIcons({ attrs: { "stroke-width": 1.75 } });
  }

  window.loginPortalApp = function () {
    const portals = readPortals();
    const root = document.querySelector(".login-page");
    const initialPortal = root?.dataset.initialPortal || "admin";

    return {
      portals,
      portal: initialPortal,
      showPwd: false,
      loading: false,

      get activePortal() {
        return this.portals.find((p) => p.id === this.portal) || this.portals[0] || {
          id: "admin",
          title: "Organization Admin Portal",
          subtitle: "Sign in to your organization workspace",
          icon: "building-2",
          accent: "violet",
          features: [],
          preview_stats: [],
        };
      },

      init() {
        document.body.classList.add("login-body");
        const params = new URLSearchParams(window.location.search);
        const queryPortal = params.get("portal");
        if (queryPortal && this.portals.some((p) => p.id === queryPortal)) {
          this.portal = queryPortal;
        }
        this.$nextTick(() => refreshLucide(root));
      },

      setPortal(id) {
        if (id === this.portal) return;
        this.portal = id;
        this.$nextTick(() => {
          refreshLucide(root);
          const iconEl = root?.querySelector(".login-auth__portal-icon [data-lucide]");
          if (iconEl && this.activePortal.icon) {
            iconEl.setAttribute("data-lucide", this.activePortal.icon);
            refreshLucide(root);
          }
        });
        const url = new URL(window.location.href);
        url.searchParams.set("portal", id);
        window.history.replaceState({}, "", url);
      },

      onSubmit() {
        this.loading = true;
      },
    };
  };

  document.addEventListener("DOMContentLoaded", () => {
    refreshLucide(document.querySelector(".login-page"));
  });
})();

(function () {
  "use strict";

  var topnav = document.querySelector("[data-topnav]");
  if (!topnav) return;

  var notifWrap = topnav.querySelector('[data-topnav-dropdown="notifications"]');
  var notifList = notifWrap?.querySelector("[data-notif-list]");
  var notifBadge = notifWrap?.querySelector("[data-notif-badge]");
  var notifMeta = notifWrap?.querySelector("[data-notif-meta]");
  var markAllBtn = notifWrap?.querySelector("[data-notif-mark-all]");
  var readAllUrl = notifWrap?.dataset.notificationsReadAll || "";
  var notifApiBase = notifWrap?.dataset.notificationsApi || "/dashboard/api/notifications/";

  function csrf() {
    var m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : "";
  }

  function closeAllDropdowns(except) {
    document.querySelectorAll("[data-topnav-dropdown]").forEach(function (wrap) {
      if (except && wrap === except) return;
      var menu = wrap.querySelector("[data-topnav-dropdown-menu]");
      var toggle = wrap.querySelector("[data-topnav-dropdown-toggle]");
      menu?.classList.add("hidden");
      toggle?.setAttribute("aria-expanded", "false");
    });
  }

  function setUnreadCount(count) {
    if (!notifBadge) return;
    var n = Math.max(0, count);
    notifBadge.textContent = String(n);
    notifBadge.classList.toggle("hidden", n === 0);
    if (notifMeta) {
      notifMeta.textContent = n ? n + " unread" : "All caught up";
    }
    if (markAllBtn) {
      markAllBtn.classList.toggle("hidden", n === 0);
    }
  }

  function markItemRead(link) {
    link.classList.remove("is-unread");
    link.dataset.notifRead = "true";
  }

  function markItemUnread(link) {
    link.classList.add("is-unread");
    link.dataset.notifRead = "false";
  }

  function patchRead(id) {
    return fetch(notifApiBase + id + "/read/", {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf(),
      },
    }).then(function (r) { return r.json(); });
  }

  function patchReadAll() {
    return fetch(readAllUrl, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf(),
      },
    }).then(function (r) { return r.json(); });
  }

  if (notifList) {
    notifList.addEventListener("click", function (e) {
      var link = e.target.closest("[data-notification-id]");
      if (!link || link.dataset.notifRead === "true") return;

      e.preventDefault();
      var id = link.dataset.notificationId;
      var url = link.getAttribute("href");
      var prevCount = parseInt(notifBadge?.textContent || "0", 10) || 0;

      markItemRead(link);
      setUnreadCount(prevCount - 1);

      patchRead(id).then(function (res) {
        if (res.ok) {
          setUnreadCount(res.unread_count);
          window.location.href = url;
          return;
        }
        markItemUnread(link);
        setUnreadCount(prevCount);
        window.location.href = url;
      }).catch(function () {
        markItemUnread(link);
        setUnreadCount(prevCount);
        window.location.href = url;
      });
    });
  }

  if (markAllBtn) {
    markAllBtn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      var prevCount = parseInt(notifBadge?.textContent || "0", 10) || 0;
      notifList?.querySelectorAll("[data-notification-id]").forEach(markItemRead);
      setUnreadCount(0);

      patchReadAll().then(function (res) {
        if (!res.ok) {
          window.location.reload();
          return;
        }
        setUnreadCount(0);
        if (res.notifications) {
          res.notifications.forEach(function (n) {
            var link = notifList?.querySelector('[data-notification-id="' + n.id + '"]');
            if (link) markItemRead(link);
          });
        }
      }).catch(function () {
        setUnreadCount(prevCount);
        window.location.reload();
      });
    });
  }

  document.addEventListener("click", function (e) {
    var toggle = e.target.closest("[data-topnav-dropdown-toggle]");
    if (toggle) {
      e.preventDefault();
      e.stopPropagation();
      var wrap = toggle.closest("[data-topnav-dropdown]");
      var menu = wrap?.querySelector("[data-topnav-dropdown-menu]");
      var isOpen = menu && !menu.classList.contains("hidden");
      closeAllDropdowns();
      if (!isOpen && menu) {
        menu.classList.remove("hidden");
        toggle.setAttribute("aria-expanded", "true");
      }
      return;
    }

    if (!e.target.closest("[data-topnav-dropdown]")) {
      closeAllDropdowns();
    }
  });

  window.addEventListener("scroll", function () {
    topnav.classList.toggle("is-scrolled", window.scrollY > 4);
  }, { passive: true });
  topnav.classList.toggle("is-scrolled", window.scrollY > 4);

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      closeAllDropdowns();
    }
  });
})();

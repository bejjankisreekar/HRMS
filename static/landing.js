(() => {
  "use strict";

  const landing = document.querySelector(".hrms-landing");
  if (!landing) return;

  /* Page ready */
  landing.classList.add("is-loading");
  window.addEventListener("load", () => {
    landing.classList.remove("is-loading");
    landing.classList.add("is-ready");
  });

  /* Sticky nav scroll state */
  const nav = document.getElementById("site-nav");
  const onScroll = () => {
    nav?.classList.toggle("is-scrolled", window.scrollY > 24);
  };
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  /* Mobile menu */
  const menuToggle = document.querySelector("[data-mobile-menu-toggle]");
  const mobileMenu = document.getElementById("mobile-menu");

  function closeMobileMenu() {
    if (!mobileMenu || !menuToggle) return;
    mobileMenu.classList.add("hidden");
    mobileMenu.hidden = true;
    menuToggle.setAttribute("aria-expanded", "false");
    menuToggle.innerHTML = '<i data-lucide="menu" class="h-5 w-5"></i>';
    if (window.lucide?.createIcons) window.lucide.createIcons();
  }

  menuToggle?.addEventListener("click", () => {
    if (!mobileMenu) return;
    const open = mobileMenu.classList.toggle("hidden");
    mobileMenu.hidden = open;
    menuToggle.setAttribute("aria-expanded", open ? "false" : "true");
    menuToggle.innerHTML = open
      ? '<i data-lucide="menu" class="h-5 w-5"></i>'
      : '<i data-lucide="x" class="h-5 w-5"></i>';
    if (window.lucide?.createIcons) window.lucide.createIcons();
  });

  document.querySelectorAll("[data-mobile-menu-close]").forEach((el) => {
    el.addEventListener("click", closeMobileMenu);
  });

  /* Demo modal */
  const demoModal = document.getElementById("demo-modal");

  function openDemo() {
    demoModal?.classList.remove("hidden");
    demoModal?.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
  }

  function closeDemo() {
    demoModal?.classList.add("hidden");
    demoModal?.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
  }

  document.querySelectorAll("[data-demo-open]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      openDemo();
    });
  });
  document.querySelectorAll("[data-demo-close]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      closeDemo();
    });
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeDemo();
  });

  /* Scroll reveal */
  const revealEls = document.querySelectorAll(".hrms-reveal");
  if ("IntersectionObserver" in window && revealEls.length) {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
    );
    revealEls.forEach((el) => observer.observe(el));
  } else {
    revealEls.forEach((el) => el.classList.add("is-visible"));
  }

  /* Testimonial carousel */
  const carousel = document.querySelector("[data-testimonial-carousel]");
  const track = carousel?.querySelector("[data-testimonial-track]");
  const dotsContainer = carousel?.querySelector("[data-testimonial-dots]");
  const cards = track ? Array.from(track.children) : [];
  let slideIndex = 0;
  let carouselTimer;

  function slidesPerView() {
    return window.innerWidth >= 768 ? 2 : 1;
  }

  function buildDots() {
    if (!dotsContainer || !cards.length) return;
    dotsContainer.innerHTML = "";
    const count = Math.ceil(cards.length / slidesPerView());
    for (let i = 0; i < count; i++) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.setAttribute("aria-label", `Go to slide ${i + 1}`);
      if (i === slideIndex) btn.classList.add("is-active");
      btn.addEventListener("click", () => {
        slideIndex = i;
        updateCarousel();
        resetCarouselTimer();
      });
      dotsContainer.appendChild(btn);
    }
  }

  function updateCarousel() {
    if (!track) return;
    const perView = slidesPerView();
    const maxIndex = Math.max(0, Math.ceil(cards.length / perView) - 1);
    if (slideIndex > maxIndex) slideIndex = 0;
    const offset = (slideIndex * 100) / perView;
    track.style.transform = `translateX(-${offset}%)`;
    dotsContainer?.querySelectorAll("button").forEach((dot, i) => {
      dot.classList.toggle("is-active", i === slideIndex);
    });
  }

  function resetCarouselTimer() {
    clearInterval(carouselTimer);
    carouselTimer = window.setInterval(() => {
      const maxIndex = Math.max(0, Math.ceil(cards.length / slidesPerView()) - 1);
      slideIndex = slideIndex >= maxIndex ? 0 : slideIndex + 1;
      updateCarousel();
    }, 6000);
  }

  if (cards.length > 1) {
    buildDots();
    updateCarousel();
    resetCarouselTimer();
    window.addEventListener("resize", () => {
      buildDots();
      updateCarousel();
    });
  }

  /* Smooth anchor scroll */
  document.querySelectorAll('a[href*="#"]').forEach((link) => {
    link.addEventListener("click", (e) => {
      const href = link.getAttribute("href");
      if (!href || !href.includes("#")) return;
      const hash = href.split("#")[1];
      if (!hash || hash === "top") {
        if (href.startsWith("#") || href.endsWith("#top")) {
          e.preventDefault();
          window.scrollTo({ top: 0, behavior: "smooth" });
          closeMobileMenu();
        }
        return;
      }
      const target = document.getElementById(hash);
      if (target) {
        e.preventDefault();
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        closeMobileMenu();
      }
    });
  });

  /* Lucide icons */
  if (window.lucide?.createIcons) window.lucide.createIcons();
})();

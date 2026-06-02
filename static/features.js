(() => {
  "use strict";

  /* Sticky category nav — highlight active section */
  const navLinks = document.querySelectorAll("[data-feat-nav-link]");
  const sections = [];

  navLinks.forEach((link) => {
    const id = link.getAttribute("data-feat-nav-link");
    const section = document.getElementById(id);
    if (section) sections.push({ id, el: section, link });
  });

  function setActiveNav(id) {
    navLinks.forEach((link) => {
      link.classList.toggle("is-active", link.getAttribute("data-feat-nav-link") === id);
    });
  }

  if ("IntersectionObserver" in window && sections.length) {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setActiveNav(entry.target.id);
          }
        });
      },
      { rootMargin: "-30% 0px -55% 0px", threshold: 0 }
    );
    sections.forEach(({ el }) => observer.observe(el));
  }

  /* Smooth scroll for category nav */
  navLinks.forEach((link) => {
    link.addEventListener("click", (e) => {
      const id = link.getAttribute("data-feat-nav-link");
      const target = document.getElementById(id);
      if (target) {
        e.preventDefault();
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        setActiveNav(id);
      }
    });
  });

  /* Workflow step animation */
  const workflowSteps = document.querySelectorAll(".hrms-feat-workflow__step");
  if (workflowSteps.length) {
    let stepIndex = 2;
    setInterval(() => {
      workflowSteps.forEach((s) => s.classList.remove("is-active"));
      workflowSteps[stepIndex]?.classList.add("is-active");
      stepIndex = (stepIndex + 1) % workflowSteps.length;
    }, 2500);
  }

  if (window.lucide?.createIcons) window.lucide.createIcons();
})();

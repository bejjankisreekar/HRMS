(() => {
  "use strict";

  const toggleBtns = document.querySelectorAll("[data-billing]");
  const yearlyHint = document.querySelector("[data-yearly-hint]");
  const stickyBar = document.querySelector("[data-price-sticky]");
  let billing = "monthly";

  function formatINR(amount) {
    return Number(amount).toLocaleString("en-IN", { maximumFractionDigits: 0 });
  }

  function updatePrices() {
    const isYearly = billing === "yearly";

    document.querySelectorAll("[data-price-monthly]").forEach((el) => {
      const monthly = Number(el.getAttribute("data-price-monthly"));
      const yearly = Number(el.getAttribute("data-price-yearly"));
      el.classList.add("is-updating");
      window.requestAnimationFrame(() => {
        el.textContent = formatINR(isYearly ? yearly : monthly);
        el.classList.remove("is-updating");
      });

      const card = el.closest(".hrms-price-card");
      const period = card?.querySelector("[data-period-label]");
      const savings = card?.querySelector("[data-savings]");
      const savingsAmount = card?.querySelector("[data-savings-amount]");

      if (period) {
        period.textContent = isYearly ? "/year" : "/month";
      }
      if (savings && savingsAmount) {
        const saved = monthly * 12 - yearly;
        if (isYearly && saved > 0) {
          savingsAmount.textContent = formatINR(saved);
          savings.hidden = false;
        } else {
          savings.hidden = true;
        }
      }
    });

    if (yearlyHint) yearlyHint.hidden = !isYearly;
  }

  toggleBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      billing = btn.getAttribute("data-billing") || "monthly";
      toggleBtns.forEach((b) => {
        const active = b === btn;
        b.classList.toggle("is-active", active);
        b.setAttribute("aria-pressed", active ? "true" : "false");
      });
      updatePrices();
    });
  });

  updatePrices();

  /* Sticky CTA — show after scrolling past hero */
  const hero = document.querySelector(".hrms-price-hero");
  if (stickyBar && hero) {
    const observer = new IntersectionObserver(
      ([entry]) => {
        stickyBar.classList.toggle("is-visible", !entry.isIntersecting);
      },
      { threshold: 0 }
    );
    observer.observe(hero);
  }

  if (window.lucide?.createIcons) window.lucide.createIcons();
})();

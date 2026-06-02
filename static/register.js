(() => {
  const DRAFT_KEY = "hrms.register.draft";

  function genOrgCode() {
    const bytes = new Uint8Array(4);
    crypto.getRandomValues(bytes);
    return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("").toUpperCase();
  }

  function scorePassword(v) {
    let s = 0;
    if (!v) return 0;
    if (v.length >= 8) s++;
    if (v.length >= 12) s++;
    if (/[A-Z]/.test(v)) s++;
    if (/[0-9]/.test(v)) s++;
    if (/[^A-Za-z0-9]/.test(v)) s++;
    return s;
  }

  function fieldError(form, name, message) {
    let el = form.querySelector(`[data-error-for="${name}"]`);
    if (!el) {
      const input = form.elements.namedItem(name);
      const wrap = input?.closest?.(".reg-field") || input?.parentElement;
      if (!wrap) return;
      el = document.createElement("p");
      el.className = "reg-error";
      el.dataset.errorFor = name;
      wrap.appendChild(el);
    }
    el.textContent = message;
    el.classList.toggle("hidden", !message);
  }

  function clearFieldErrors(form) {
    form.querySelectorAll("[data-error-for]").forEach((el) => {
      el.textContent = "";
      el.classList.add("hidden");
    });
  }

  function termsChecked(form) {
    return (
      form?.querySelector('[name="terms_accepted"]')?.checked &&
      form?.querySelector('[name="privacy_policy_accepted"]')?.checked
    );
  }

  window.registerOnboarding = function () {
    return {
      step: window.__REGISTER_INITIAL_STEP__ || 1,
      total: 2,
      showPwd: false,
      showConfirm: false,
      pwdScore: 0,
      orgCode: genOrgCode(),
      loading: false,
      otherType: false,
      termsTick: 0,

      init() {
        const el = document.getElementById("orgCodePreview");
        if (el) el.value = this.orgCode;
        this.loadDraft();
        const form = document.getElementById("signupForm");
        form?.addEventListener("input", () => this.saveDraft());
        form?.addEventListener("change", () => this.saveDraft());
        const orgType = form?.querySelector('[name="organization_type"]');
        orgType?.addEventListener("change", (e) => {
          this.otherType = e.target.value === "OTHER";
        });
        this.otherType = orgType?.value === "OTHER";
      },

      regenCode() {
        this.orgCode = genOrgCode();
        const el = document.getElementById("orgCodePreview");
        if (el) el.value = this.orgCode;
      },

      validateStep(n) {
        const form = document.getElementById("signupForm");
        if (!form) return true;
        clearFieldErrors(form);

        if (n === 1) {
          const name = form.elements.namedItem("organization_name");
          if (!name?.value?.trim()) {
            fieldError(form, "organization_name", "Organization name is required.");
            return false;
          }
        }

        if (n === 2) {
          const username = form.elements.namedItem("admin_username");
          const email = form.elements.namedItem("admin_email");
          const pwd = form.elements.namedItem("admin_password");
          const confirm = form.elements.namedItem("admin_confirm_password");
          let ok = true;

          if (!username?.value?.trim()) {
            fieldError(form, "admin_username", "Username is required.");
            ok = false;
          }
          if (!email?.value?.trim()) {
            fieldError(form, "admin_email", "Email is required.");
            ok = false;
          } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value)) {
            fieldError(form, "admin_email", "Enter a valid email address.");
            ok = false;
          }
          if (!pwd?.value) {
            fieldError(form, "admin_password", "Password is required.");
            ok = false;
          } else if (pwd.value.length < 8) {
            fieldError(form, "admin_password", "Password must be at least 8 characters.");
            ok = false;
          }
          if (pwd?.value !== confirm?.value) {
            fieldError(form, "admin_confirm_password", "Passwords do not match.");
            ok = false;
          }
          if (!termsChecked(form)) {
            ok = false;
          }
          return ok;
        }

        return true;
      },

      next() {
        if (!this.validateStep(this.step)) return;
        if (this.step < this.total) this.step++;
      },
      prev() {
        if (this.step > 1) this.step--;
      },

      onPwdInput(e) {
        this.pwdScore = scorePassword(e.target.value);
      },

      canSubmit() {
        void this.termsTick;
        const form = document.getElementById("signupForm");
        return this.step === this.total && termsChecked(form);
      },

      onTermsChange() {
        this.termsTick++;
      },

      saveDraft() {
        const form = document.getElementById("signupForm");
        if (!form) return;
        const data = { step: this.step };
        new FormData(form).forEach((v, k) => {
          if (k === "admin_password" || k === "admin_confirm_password") return;
          if (k === "csrfmiddlewaretoken") return;
          if (typeof v === "string") data[k] = v;
        });
        data.terms_accepted = form.querySelector('[name="terms_accepted"]')?.checked ? "1" : "";
        data.privacy_policy_accepted = form.querySelector('[name="privacy_policy_accepted"]')?.checked
          ? "1"
          : "";
        try {
          localStorage.setItem(DRAFT_KEY, JSON.stringify(data));
        } catch (_) {}
      },

      loadDraft() {
        try {
          const raw = localStorage.getItem(DRAFT_KEY);
          if (!raw) return;
          const data = JSON.parse(raw);
          const form = document.getElementById("signupForm");
          if (data.step && !window.__REGISTER_INITIAL_STEP__) {
            this.step = Math.min(Math.max(1, data.step), this.total);
          }
          Object.entries(data).forEach(([k, v]) => {
            if (k === "step" || k === "csrfmiddlewaretoken") return;
            const field = form?.elements.namedItem(k);
            if (field && "value" in field && k !== "terms_accepted" && k !== "privacy_policy_accepted") {
              field.value = v;
            }
          });
          const terms = form?.querySelector('[name="terms_accepted"]');
          const privacy = form?.querySelector('[name="privacy_policy_accepted"]');
          if (terms) terms.checked = !!data.terms_accepted;
          if (privacy) privacy.checked = !!data.privacy_policy_accepted;
        } catch (_) {}
      },

      clearDraft() {
        try {
          localStorage.removeItem(DRAFT_KEY);
        } catch (_) {}
      },

      onSubmit(e) {
        if (!this.validateStep(1)) {
          e.preventDefault();
          this.step = 1;
          return;
        }
        if (!this.validateStep(2)) {
          e.preventDefault();
          this.step = 2;
          return;
        }
        this.loading = true;
        this.clearDraft();
      },
    };
  };
})();

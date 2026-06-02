(() => {
  "use strict";

  const form = document.querySelector("[data-contact-form]");
  const submitBtn = document.querySelector("[data-contact-submit]");

  function setLoading(loading) {
    if (!submitBtn) return;
    submitBtn.classList.toggle("is-loading", loading);
    submitBtn.disabled = loading;
  }

  function buildFormSubmitBody(formData, siteUrl) {
    const modules = formData.getAll("interested_modules");
    const params = new URLSearchParams();
    params.set("name", formData.get("full_name") || "");
    params.set("email", formData.get("work_email") || "");
    params.set("company", formData.get("company_name") || "");
    params.set("phone", formData.get("phone_number") || "—");
    params.set("team_size", formData.get("employee_count") || "—");
    params.set("modules", modules.length ? modules.join(", ") : "—");
    params.set("message", formData.get("message") || "");
    params.set(
      "_subject",
      `Someone submitted your form on ${siteUrl || window.location.origin}`
    );
    params.set("_template", "table");
    params.set("_captcha", "false");
    return params;
  }

  async function sendViaFormSubmit(formEl) {
    const url = formEl.dataset.formsubmitUrl;
    if (!url || formEl.dataset.formsubmitEnabled !== "true") {
      return true;
    }

    const body = buildFormSubmitBody(
      new FormData(formEl),
      formEl.dataset.siteUrl || window.location.origin
    );

    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        Accept: "application/json",
      },
      body: body.toString(),
    });

    const payload = await response.json().catch(() => ({}));
    const ok =
      response.ok &&
      String(payload.success ?? "").toLowerCase() === "true";
    if (!ok) {
      console.warn("FormSubmit delivery failed", payload);
    }
    return ok;
  }

  if (form && submitBtn) {
    let submitting = false;

    form.addEventListener("submit", async (event) => {
      if (submitting) return;

      const useFormSubmit = form.dataset.formsubmitEnabled === "true";
      if (!useFormSubmit) {
        setLoading(true);
        return;
      }

      event.preventDefault();
      setLoading(true);

      try {
        await sendViaFormSubmit(form);
      } catch (error) {
        console.warn("FormSubmit network error", error);
      }

      submitting = true;
      form.submit();
    });
  }

  document.querySelectorAll(".hrms-field__select").forEach((sel) => {
    const sync = () => {
      sel.classList.toggle("is-filled", sel.value !== "");
    };
    sel.addEventListener("change", sync);
    sync();
  });

  if (window.lucide?.createIcons) window.lucide.createIcons();
})();

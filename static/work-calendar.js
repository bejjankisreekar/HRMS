(function () {
  const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const POLICY_CUSTOM = "CUSTOM";
  const POLICY_ROTATING_WEEKLY = "ROTATING_WEEKLY";
  const POLICY_ROTATING_MONTHLY = "ROTATING_MONTHLY";
  const POLICY_SHIFT = "SHIFT_BASED";

  const form = document.getElementById("wc-weekend-form");
  if (!form) return;

  const hiddenJson = form.querySelector('[name="rotating_patterns_json"]');
  const stepsInput = form.querySelector('[name="rotating_cycle_steps"]');
  const stepsContainer = document.getElementById("wc-rotation-steps");
  const panels = {
    custom: document.getElementById("wc-panel-custom"),
    rotating: document.getElementById("wc-panel-rotating"),
    shift: document.getElementById("wc-panel-shift"),
  };

  function selectedPolicy() {
    const checked = form.querySelector('input[name="weekend_policy"]:checked');
    return checked ? checked.value : "SAT_SUN";
  }

  function parsePatterns() {
    try {
      return JSON.parse(hiddenJson.value || "[]");
    } catch {
      return [{ off_days: [5, 6] }, { off_days: [6] }];
    }
  }

  function syncHidden() {
    const steps = parseInt(stepsInput.value, 10) || 2;
    const patterns = [];
    for (let i = 0; i < steps; i += 1) {
      const checked = form.querySelectorAll(`input[name="rot_step_${i}"]:checked`);
      const off_days = Array.from(checked).map((el) => parseInt(el.value, 10));
      patterns.push({ off_days });
    }
    hiddenJson.value = JSON.stringify(patterns);
  }

  function renderSteps() {
    if (!stepsContainer) return;
    const steps = parseInt(stepsInput.value, 10) || 2;
    const existing = parsePatterns();
    stepsContainer.innerHTML = "";

    for (let i = 0; i < steps; i += 1) {
      const off = (existing[i] && existing[i].off_days) || (i === 0 ? [5, 6] : [6]);
      const wrap = document.createElement("div");
      wrap.className = "wc-rotation-step";
      wrap.innerHTML = `<p class="text-xs font-semibold text-slate-600 mb-2">Step ${i + 1}</p>`;
      const row = document.createElement("div");
      row.className = "flex flex-wrap gap-2";
      DAY_LABELS.forEach((label, d) => {
        const id = `rot_step_${i}_${d}`;
        const lbl = document.createElement("label");
        lbl.className = "wc-day-chip";
        lbl.innerHTML = `<input type="checkbox" name="rot_step_${i}" value="${d}" id="${id}" ${off.includes(d) ? "checked" : ""}> ${label}`;
        row.appendChild(lbl);
      });
      wrap.appendChild(row);
      stepsContainer.appendChild(wrap);
    }
    syncHidden();
  }

  function updatePanels() {
    const p = selectedPolicy();
    Object.values(panels).forEach((el) => el && el.classList.remove("is-visible"));
    if (p === POLICY_CUSTOM && panels.custom) panels.custom.classList.add("is-visible");
    if ((p === POLICY_ROTATING_WEEKLY || p === POLICY_ROTATING_MONTHLY) && panels.rotating) {
      panels.rotating.classList.add("is-visible");
      renderSteps();
    }
    if (p === POLICY_SHIFT && panels.shift) panels.shift.classList.add("is-visible");
  }

  form.querySelectorAll('input[name="weekend_policy"]').forEach((el) => {
    el.addEventListener("change", updatePanels);
  });

  if (stepsInput) {
    stepsInput.addEventListener("change", renderSteps);
    stepsInput.addEventListener("input", renderSteps);
  }

  form.addEventListener("change", (e) => {
    if (e.target.name && e.target.name.startsWith("rot_step_")) {
      syncHidden();
    }
  });

  form.addEventListener("submit", syncHidden);
  updatePanels();
})();

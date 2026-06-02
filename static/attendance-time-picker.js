/**
 * Modern time picker for attendance check-in / check-out fields.
 */
(function () {
  "use strict";

  const OPEN_CLASS = "is-open";
  const CLOCK_SVG =
    '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>';

  let activePicker = null;

  function pad2(n) {
    return String(n).padStart(2, "0");
  }

  function parseValue(value) {
    const match = /^(\d{1,2}):(\d{2})$/.exec((value || "").trim());
    if (!match) {
      const now = new Date();
      return { h24: now.getHours(), m: now.getMinutes() };
    }
    return {
      h24: Math.min(23, Math.max(0, Number(match[1]))),
      m: Math.min(59, Math.max(0, Number(match[2]))),
    };
  }

  function to12(h24) {
    const ampm = h24 >= 12 ? "PM" : "AM";
    let h12 = h24 % 12;
    if (h12 === 0) h12 = 12;
    return { h12, ampm };
  }

  function to24(h12, ampm, m) {
    let hour = h12 % 12;
    if (ampm === "PM") hour += 12;
    return `${pad2(hour)}:${pad2(m)}`;
  }

  function parseManualTime(text, fallbackAmpm) {
    const raw = (text || "").trim();
    if (!raw) return null;

    const upper = raw.toUpperCase();

    // 9:45 AM, 09:45 PM, 14:30 (24h if no AM/PM and hour > 12)
    let match = /^(\d{1,2}):(\d{1,2})(?:\s*(AM|PM))?$/.exec(upper);
    if (match) {
      let h = Number(match[1]);
      let m = Number(match[2]);
      if (m > 59 || h > 23) return null;
      const ampm = match[3] || (h >= 13 ? null : fallbackAmpm || (h >= 12 ? "PM" : "AM"));
      if (ampm) {
        if (h === 0) h = 12;
        else if (h > 12) {
          /* keep 24h hour when no AM/PM and h > 12 */
        } else if (ampm === "PM" && h < 12) h += 12;
        else if (ampm === "AM" && h === 12) h = 0;
      }
      return { h24: Math.min(23, Math.max(0, h)), m: Math.min(59, Math.max(0, m)) };
    }

    // 945, 0945, 1345 (HHMM)
    const digits = raw.replace(/\D/g, "");
    if (digits.length === 3 || digits.length === 4) {
      const m = Number(digits.slice(-2));
      let h = Number(digits.slice(0, -2));
      if (m > 59) return null;
      const ampm = fallbackAmpm || "AM";
      if (h <= 12 && !fallbackAmpm) {
        if (h === 0) h = 12;
        else if (ampm === "PM" && h < 12) h += 12;
        else if (ampm === "AM" && h === 12) h = 0;
      } else if (h > 23) {
        return null;
      }
      return { h24: Math.min(23, Math.max(0, h)), m };
    }

    return null;
  }

  function clampHour12(value) {
    let h = parseInt(String(value).replace(/\D/g, ""), 10);
    if (Number.isNaN(h)) return 12;
    if (h < 1) return 1;
    if (h > 12) return 12;
    return h;
  }

  function clampMinute(value) {
    let m = parseInt(String(value).replace(/\D/g, ""), 10);
    if (Number.isNaN(m)) return 0;
    if (m < 0) return 0;
    if (m > 59) return 59;
    return m;
  }

  function formatDisplay(h24, m) {
    const { h12, ampm } = to12(h24);
    return `${h12}:${pad2(m)} ${ampm}`;
  }

  function selectAllOnFocus(e) {
    requestAnimationFrame(() => e.target.select());
  }

  class AttendanceTimePicker {
    constructor(input) {
      this.input = input;
      this.state = parseValue(input.value);
      this.root = document.createElement("div");
      this.root.className = "attendance-time-picker";
      if (input.classList.contains("w-full")) this.root.classList.add("attendance-time-picker--full");
      if (input.classList.contains("attendance-time-input--in")) this.root.classList.add("attendance-time-picker--in");
      if (input.classList.contains("attendance-time-input--out")) this.root.classList.add("attendance-time-picker--out");
      if (input.classList.contains("attendance-time-input--compact")) this.root.classList.add("attendance-time-picker--compact");

      input.classList.add("attendance-time-picker-native");
      input.parentNode.insertBefore(this.root, input);
      this.root.appendChild(input);

      this.trigger = document.createElement("button");
      this.trigger.type = "button";
      this.trigger.className = "attendance-time-picker-trigger";
      this.trigger.setAttribute("aria-haspopup", "dialog");
      this.trigger.setAttribute("aria-expanded", "false");
      this.trigger.innerHTML = `<span class="attendance-time-picker-value"></span><span class="attendance-time-picker-icon">${CLOCK_SVG}</span>`;
      this.root.appendChild(this.trigger);

      this.valueEl = this.trigger.querySelector(".attendance-time-picker-value");
      this.punchDisplayEl = this.input.closest(".att-punch")?.querySelector(".att-punch-time") || null;
      this.popover = null;
      this.outsideClickBound = false;

      this.onDocClick = this.onDocClick.bind(this);
      this.onKeydown = this.onKeydown.bind(this);
      this.onReposition = () => this.positionPopover();

      this.trigger.addEventListener("mousedown", (e) => e.stopPropagation());
      this.trigger.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (this.root.classList.contains(OPEN_CLASS)) this.close(false);
        else this.open();
      });

      this.syncFromInput();
      input.addEventListener("change", () => this.syncFromInput());
    }

    syncFromInput() {
      this.state = parseValue(this.input.value);
      this.valueEl.textContent = formatDisplay(this.state.h24, this.state.m);
    }

    updatePunchDisplay(markDraft = false) {
      if (!this.punchDisplayEl) return;
      this.punchDisplayEl.textContent = formatDisplay(this.state.h24, this.state.m);
      this.punchDisplayEl.classList.toggle("att-punch-time--draft", markDraft);
    }

    syncToInput() {
      this.input.value = `${pad2(this.state.h24)}:${pad2(this.state.m)}`;
      this.input.dispatchEvent(new Event("change", { bubbles: true }));
      this.valueEl.textContent = formatDisplay(this.state.h24, this.state.m);
      this.updatePunchDisplay(true);
    }

    buildPopover() {
      const { h12, ampm } = to12(this.state.h24);
      const pop = document.createElement("div");
      pop.className = "attendance-time-picker-popover";
      pop.setAttribute("role", "dialog");
      pop.setAttribute("aria-label", "Select time");
      pop.setAttribute("data-attendance-time-popover", "");
      pop.innerHTML = `
        <div class="atp-manual">
          <input type="text" class="atp-manual-input" data-manual placeholder="Type time, e.g. 9:45 AM" autocomplete="off" spellcheck="false" aria-label="Type time">
        </div>
        <div class="atp-controls">
          <div class="atp-unit">
            <button type="button" class="atp-step" data-step="hour-up" aria-label="Increase hour">+</button>
            <input type="text" inputmode="numeric" class="atp-digit-input" data-hour value="${pad2(h12)}" maxlength="2" aria-label="Hour">
            <button type="button" class="atp-step" data-step="hour-down" aria-label="Decrease hour">−</button>
            <span class="atp-unit-label">Hour</span>
          </div>
          <span class="atp-separator">:</span>
          <div class="atp-unit">
            <button type="button" class="atp-step" data-step="min-up" aria-label="Increase minute">+</button>
            <input type="text" inputmode="numeric" class="atp-digit-input" data-minute value="${pad2(this.state.m)}" maxlength="2" aria-label="Minute">
            <button type="button" class="atp-step" data-step="min-down" aria-label="Decrease minute">−</button>
            <span class="atp-unit-label">Min</span>
          </div>
        </div>
        <div class="atp-ampm" role="group" aria-label="AM or PM">
          <button type="button" class="atp-ampm-btn${ampm === "AM" ? " is-active" : ""}" data-ampm="AM">AM</button>
          <button type="button" class="atp-ampm-btn${ampm === "PM" ? " is-active" : ""}" data-ampm="PM">PM</button>
        </div>
        <div class="atp-actions">
          <button type="button" class="atp-action atp-action--ghost" data-action="now">Now</button>
          <button type="button" class="atp-action atp-action--primary" data-action="done">Done</button>
        </div>
      `;

      this.hourInput = pop.querySelector("[data-hour]");
      this.minuteInput = pop.querySelector("[data-minute]");
      this.manualInput = pop.querySelector("[data-manual]");

      pop.querySelector("[data-step=hour-up]").addEventListener("click", (e) => {
        e.stopPropagation();
        this.adjustHour(1);
      });
      pop.querySelector("[data-step=hour-down]").addEventListener("click", (e) => {
        e.stopPropagation();
        this.adjustHour(-1);
      });
      pop.querySelector("[data-step=min-up]").addEventListener("click", (e) => {
        e.stopPropagation();
        this.adjustMinute(5);
      });
      pop.querySelector("[data-step=min-down]").addEventListener("click", (e) => {
        e.stopPropagation();
        this.adjustMinute(-5);
      });

      this.hourInput.addEventListener("focus", selectAllOnFocus);
      this.minuteInput.addEventListener("focus", selectAllOnFocus);
      this.manualInput.addEventListener("focus", selectAllOnFocus);

      this.hourInput.addEventListener("input", () => this.applyDigitInputs(false));
      this.minuteInput.addEventListener("input", () => this.applyDigitInputs(false));
      this.hourInput.addEventListener("blur", () => this.applyDigitInputs(true));
      this.minuteInput.addEventListener("blur", () => this.applyDigitInputs(true));

      const commitManual = () => this.applyManualInput();
      this.manualInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          commitManual();
        }
      });
      this.manualInput.addEventListener("blur", commitManual);

      [this.hourInput, this.minuteInput].forEach((el) => {
        el.addEventListener("keydown", (e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            this.applyDigitInputs(true);
            this.syncToInput();
          }
        });
      });

      pop.querySelectorAll("[data-ampm]").forEach((btn) => {
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          const target = btn.getAttribute("data-ampm");
          const current = to12(this.state.h24);
          if (current.ampm === target) return;
          let h24 = this.state.h24;
          if (target === "PM" && h24 < 12) h24 += 12;
          if (target === "AM" && h24 >= 12) h24 -= 12;
          this.state.h24 = h24;
          this.renderPopover();
        });
      });

      pop.querySelector("[data-action=now]").addEventListener("click", (e) => {
        e.stopPropagation();
        const now = new Date();
        this.state = { h24: now.getHours(), m: now.getMinutes() };
        this.renderPopover();
      });

      pop.querySelector("[data-action=done]").addEventListener("click", (e) => {
        e.stopPropagation();
        this.applyDigitInputs(true);
        this.syncToInput();
        this.close(false);
      });

      pop.addEventListener("mousedown", (e) => e.stopPropagation());
      pop.addEventListener("click", (e) => e.stopPropagation());

      this.popover = pop;
      this.renderPopover();
    }

    applyDigitInputs(format) {
      const { ampm } = to12(this.state.h24);
      const h12 = clampHour12(this.hourInput.value);
      const m = clampMinute(this.minuteInput.value);
      this.state.h24 = parseValue(to24(h12, ampm, m)).h24;
      this.state.m = m;
      if (format) {
        this.hourInput.value = pad2(h12);
        this.minuteInput.value = pad2(m);
      }
      this.renderPopover(false);
    }

    applyManualInput() {
      const text = this.manualInput.value.trim();
      if (!text) return;
      const { ampm } = to12(this.state.h24);
      const parsed = parseManualTime(text, ampm);
      if (!parsed) {
        this.manualInput.classList.add("atp-manual-input--error");
        return;
      }
      this.manualInput.classList.remove("atp-manual-input--error");
      this.state = parsed;
      this.manualInput.value = "";
      this.renderPopover();
    }

    renderPopover(updateInputs = true) {
      if (!this.popover) return;
      const { ampm } = to12(this.state.h24);
      if (updateInputs) {
        const { h12 } = to12(this.state.h24);
        if (document.activeElement !== this.hourInput) {
          this.hourInput.value = pad2(h12);
        }
        if (document.activeElement !== this.minuteInput) {
          this.minuteInput.value = pad2(this.state.m);
        }
      }
      this.popover.querySelectorAll("[data-ampm]").forEach((btn) => {
        btn.classList.toggle("is-active", btn.getAttribute("data-ampm") === ampm);
      });
      this.updatePunchDisplay(true);
    }

    adjustHour(delta) {
      const { h12, ampm } = to12(this.state.h24);
      let next = h12 + delta;
      if (next > 12) next = 1;
      if (next < 1) next = 12;
      this.state.h24 = parseValue(to24(next, ampm, this.state.m)).h24;
      this.renderPopover();
    }

    adjustMinute(delta) {
      let m = this.state.m + delta;
      if (m > 59) m = 59;
      if (m < 0) m = 0;
      this.state.m = m;
      this.renderPopover();
    }

    positionPopover() {
      if (!this.popover) return;
      const rect = this.trigger.getBoundingClientRect();
      const pop = this.popover;
      const margin = 8;

      pop.style.display = "block";
      pop.style.visibility = "visible";
      pop.style.opacity = "1";

      const popRect = pop.getBoundingClientRect();
      let top = rect.bottom + margin;
      if (top + popRect.height > window.innerHeight - margin) {
        top = rect.top - popRect.height - margin;
      }
      top = Math.max(margin, Math.min(top, window.innerHeight - popRect.height - margin));

      let left = rect.left;
      if (left + popRect.width > window.innerWidth - margin) {
        left = window.innerWidth - popRect.width - margin;
      }
      left = Math.max(margin, left);

      pop.style.top = `${Math.round(top)}px`;
      pop.style.left = `${Math.round(left)}px`;
    }

    bindOutsideClick() {
      if (this.outsideClickBound) return;
      setTimeout(() => {
        document.addEventListener("mousedown", this.onDocClick, true);
        document.addEventListener("keydown", this.onKeydown);
        window.addEventListener("resize", this.onReposition);
        window.addEventListener("scroll", this.onReposition, true);
        this.outsideClickBound = true;
      }, 0);
    }

    unbindOutsideClick() {
      document.removeEventListener("mousedown", this.onDocClick, true);
      document.removeEventListener("keydown", this.onKeydown);
      window.removeEventListener("resize", this.onReposition);
      window.removeEventListener("scroll", this.onReposition, true);
      this.outsideClickBound = false;
    }

    open() {
      if (activePicker && activePicker !== this) activePicker.close(false);
      activePicker = this;
      this.state = parseValue(this.input.value);

      if (!this.popover) this.buildPopover();
      else this.renderPopover();

      document.body.appendChild(this.popover);
      this.positionPopover();
      this.root.classList.add(OPEN_CLASS);
      this.trigger.setAttribute("aria-expanded", "true");
      this.bindOutsideClick();
      requestAnimationFrame(() => {
        if (this.manualInput) this.manualInput.focus();
      });
    }

    close(save = true) {
      if (!this.popover) return;
      if (save) this.syncToInput();
      this.popover.remove();
      this.root.classList.remove(OPEN_CLASS);
      this.trigger.setAttribute("aria-expanded", "false");
      this.unbindOutsideClick();
      if (activePicker === this) activePicker = null;
    }

    onDocClick(e) {
      if (this.root.contains(e.target) || (this.popover && this.popover.contains(e.target))) return;
      this.applyDigitInputs(true);
      this.close(true);
    }

    onKeydown(e) {
      if (e.key === "Escape") {
        this.applyDigitInputs(true);
        this.close(true);
      }
    }
  }

  function init() {
    document.querySelectorAll("input.attendance-time-input:not(.attendance-time-picker-native)").forEach((input) => {
      new AttendanceTimePicker(input);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

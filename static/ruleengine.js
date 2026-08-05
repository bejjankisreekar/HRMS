(function () {
  "use strict";

  function cookie(name) {
    const m = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
    return m ? m.pop() : "";
  }

  function readJSONScript(id) {
    const el = document.getElementById(id);
    if (!el) return null;
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return null;
    }
  }

  window.readBuilderConfig = function readBuilderConfig(ruleId) {
    return {
      rule: readJSONScript("builder-rule-data"),
      facts: readJSONScript("builder-facts-data") || [],
      actions: readJSONScript("builder-actions-data") || [],
      operators: readJSONScript("builder-operators-data") || { labels: {}, by_type: {} },
      triggers: readJSONScript("builder-triggers-data") || [],
      statuses: readJSONScript("builder-statuses-data") || [],
      ruleId: ruleId || "",
    };
  };

  function requestJSON(url, method, body) {
    const opts = {
      method,
      headers: { "Content-Type": "application/json", "X-CSRFToken": cookie("csrftoken"), "X-Requested-With": "XMLHttpRequest" },
    };
    if (body !== undefined) opts.body = JSON.stringify(body);
    return fetch(url, opts).then((r) => r.json().then((data) => ({ ok: r.ok, status: r.status, data })));
  }

  window.ruleList = function ruleList() {
    return {
      toggleStatus(id, newStatus) {
        requestJSON(`/api/rule-engine/rules/${id}/status/`, "POST", { status: newStatus }).then(() => window.location.reload());
      },
      updatePriority(id, priority) {
        requestJSON(`/api/rule-engine/rules/reorder/`, "POST", { order: [{ id, priority: Number(priority) }] });
      },
      deleteRule(id, name) {
        if (!window.confirm(`Delete rule "${name}"? This cannot be undone.`)) return;
        requestJSON(`/api/rule-engine/rules/${id}/`, "DELETE").then(() => window.location.reload());
      },
    };
  };

  window.ruleBuilder = function ruleBuilder(config) {
    return {
      rule: config.rule || {
        name: "", description: "", trigger_event: "", status: "DRAFT", priority: 100,
        conditions: [], actions: [], is_test_mode: false,
      },
      facts: config.facts || [],
      actionDefs: config.actions || [],
      operatorLabels: (config.operators && config.operators.labels) || {},
      operatorsByType: (config.operators && config.operators.by_type) || {},
      triggers: config.triggers || [],
      statuses: config.statuses || [],
      ruleId: config.ruleId || "",
      saving: false,
      error: "",

      init() {
        if (!this.rule.conditions || !this.rule.conditions.length) this.addGroup();
        if (!this.rule.actions) this.rule.actions = [];
      },
      factByKey(key) {
        return this.facts.find((f) => f.key === key);
      },
      operatorsFor(field) {
        const f = this.factByKey(field);
        if (!f) return [];
        return (this.operatorsByType[f.value_type] || []).map((op) => ({ value: op, label: this.operatorLabels[op] || op }));
      },
      isEnumField(field) {
        const f = this.factByKey(field);
        return !!(f && f.value_type === "enum" && f.choices && f.choices.length);
      },
      addGroup() {
        this.rule.conditions.push([{ field: this.facts[0] ? this.facts[0].key : "", operator: "EQUALS", value: "", value2: "" }]);
      },
      removeGroup(gi) {
        this.rule.conditions.splice(gi, 1);
      },
      addCondition(gi) {
        this.rule.conditions[gi].push({ field: this.facts[0] ? this.facts[0].key : "", operator: "EQUALS", value: "", value2: "" });
      },
      removeCondition(gi, ci) {
        this.rule.conditions[gi].splice(ci, 1);
      },
      actionDef(type) {
        return this.actionDefs.find((a) => a.key === type);
      },
      addAction() {
        const first = this.actionDefs[0];
        this.rule.actions.push({ type: first ? first.key : "", params: {} });
      },
      removeAction(i) {
        this.rule.actions.splice(i, 1);
      },
      onActionTypeChange(action) {
        action.params = {};
      },
      paramFields(type) {
        const def = this.actionDef(type);
        if (!def) return [];
        return Object.entries(def.param_schema).map(([key, t]) => ({ key, type: t }));
      },
      paramInputKind(typeStr) {
        if (typeStr === "number") return "number";
        if (typeStr.indexOf("enum:") === 0) return "enum";
        return "text";
      },
      enumOptions(typeStr) {
        return typeStr.replace("enum:", "").split(",");
      },
      save() {
        this.error = "";
        if (!this.rule.name || !this.rule.name.trim()) {
          this.error = "Name is required.";
          return;
        }
        if (!this.rule.trigger_event) {
          this.error = "Trigger is required.";
          return;
        }
        this.saving = true;
        const url = this.ruleId ? `/api/rule-engine/rules/${this.ruleId}/` : `/api/rule-engine/rules/`;
        const method = this.ruleId ? "PUT" : "POST";
        requestJSON(url, method, this.rule)
          .then(({ ok, data }) => {
            this.saving = false;
            if (!ok) {
              this.error = (data.errors && data.errors.join(" ")) || data.error || "Save failed.";
              return;
            }
            window.location.href = "/rule-engine/";
          })
          .catch(() => {
            this.saving = false;
            this.error = "Save failed.";
          });
      },
    };
  };

  window.ruleTester = function ruleTester(config) {
    return {
      subjectType: "User",
      subjectId: config.initialEmployeeId || "",
      ruleId: config.ruleId || "",
      triggerEvent: config.triggerEvent || "",
      mode: config.ruleId ? "rule" : "trigger",
      running: false,
      logs: [],
      error: "",
      run() {
        this.error = "";
        this.logs = [];
        if (!this.subjectId) {
          this.error = "Pick a sample employee first.";
          return;
        }
        if (this.mode === "trigger" && !this.triggerEvent) {
          this.error = "Pick a trigger to test.";
          return;
        }
        this.running = true;
        const url = this.mode === "rule" && this.ruleId
          ? `/api/rule-engine/rules/${this.ruleId}/test/`
          : `/api/rule-engine/rules/test/`;
        requestJSON(url, "POST", {
          subject_type: this.subjectType,
          subject_id: this.subjectId,
          trigger_event: this.triggerEvent,
        })
          .then(({ ok, data }) => {
            this.running = false;
            if (!ok) {
              this.error = data.error || "Test failed.";
              return;
            }
            this.logs = data.logs || [];
          })
          .catch(() => {
            this.running = false;
            this.error = "Test failed.";
          });
      },
    };
  };
})();

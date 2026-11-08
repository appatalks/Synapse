export function elapsed(seconds) {
  const total = Math.max(0, Math.floor(seconds || 0));
  return total < 60 ? `${total}s` : `${Math.floor(total / 60)}m ${total % 60}s`;
}

export function bindSettingsTabs(tabs, panelFor, onSelect = () => {}) {
  const activate = (tab, focus = false) => {
    for (const item of tabs) {
      const selected = item === tab;
      item.setAttribute("aria-selected", String(selected));
      item.tabIndex = selected ? 0 : -1;
      panelFor(item).hidden = !selected;
    }
    if (focus) tab.focus();
    onSelect(tab);
  };
  for (const tab of tabs) {
    tab.addEventListener("click", () => activate(tab));
    tab.addEventListener("keydown", (event) => {
      let index = tabs.indexOf(tab);
      if (event.key === "ArrowRight") index = (index + 1) % tabs.length;
      else if (event.key === "ArrowLeft") index = (index + tabs.length - 1) % tabs.length;
      else if (event.key === "Home") index = 0;
      else if (event.key === "End") index = tabs.length - 1;
      else return;
      event.preventDefault();
      activate(tabs[index], true);
    });
  }
  return activate;
}

export function loadingText(loading) {
  if (!loading) return "";
  const pending = loading.waiting_for?.length ? ` Waiting for ${loading.waiting_for.join(", ")}.` : "";
  const quiet = loading.last_output_age_seconds >= 15
    ? ` No new backend output for ${elapsed(loading.last_output_age_seconds)}; readiness checks continue.` : "";
  return `${loading.phase} · ${elapsed(loading.elapsed_seconds)} elapsed.${pending}${quiet}`;
}

export function draftControls(status, mode, type) {
  const enabled = !!status?.speculation_enabled;
  const mtp = status?.backend_kind === "llama.cpp";
  return {
    disabled: !enabled,
    dflashDisabled: mode !== "standard",
    mtpDisabled: !mtp,
    inputDisabled: !enabled || type === "none" ||
      (type === "dflash" && mode !== "standard") || (type === "mtp" && !mtp),
    maximum: type === "mtp" && mode !== "standard" ? 31 : 32,
  };
}

export function modelLoadPayload(settings) {
  if (settings.execution_mode === "standard") return settings;
  const payload = {
    model: settings.model, execution_mode: settings.execution_mode, kv_cache_type: settings.kv_cache_type,
    draft_type: settings.draft_type, draft_model: settings.draft_model, draft_tokens: settings.draft_tokens,
  };
  if (settings.execution_mode === "hybrid") Object.assign(payload, {
    cpu_threads: settings.cpu_threads, batch_threads: settings.batch_threads, cpu_poll: settings.cpu_poll,
    expert_cache_mib: settings.expert_cache_mib,
  });
  if (settings.execution_mode === "hybrid" && settings.hybrid_variant !== undefined) {
    payload.hybrid_variant = settings.hybrid_variant;
  }
  return payload;
}

export function tuningPayload(settings, mode) {
  return mode === "standard" ? { ...settings, include_hybrid: false } : { ...settings, placement: "auto" };
}

export function bindEngineSelection(toggle, select, changed) {
  let previous = select.value;
  const sync = () => {
    toggle.checked = select.value !== "standard";
    previous = select.value;
  };
  const change = () => {
    const before = previous;
    sync();
    changed(before);
  };
  toggle.addEventListener("change", () => {
    select.value = toggle.checked ? "auto" : "standard";
    change();
  });
  select.addEventListener("change", change);
  sync();
  return sync;
}

export function engineSettingsText(status, mode, context) {
  const running = status?.model && status.state === "ready"
    ? `Running now: ${status.hybrid_active ? "Hybrid" : "Standard (Hybrid is not active)"} at ${status.context.toLocaleString()} context tokens. ` : "";
  const maximum = status?.engine_source === "measured" && status.tuning?.goal === "maximum" &&
    status.tuning.model === status.model && status.tuning.recommendation?.settings.context === status.context
    ? "Maximum Context tuning prioritizes capacity and long-prompt time, not fastest generation. " : "";
  const reload = status?.model && ["loading", "ready", "stopping"].includes(status.state)
    ? " Unload the active model before changing this setting; changes apply on the next load." : "";
  if (mode === "standard") {
    return `${running}${maximum}Hybrid is off. Loading and Auto Tune use Standard only. Context and run settings are editable below; Standard is an engine choice, not a general manual-settings switch.${reload}`;
  }
  if (mode === "hybrid") {
    return `${running}${maximum}Advanced override: Hybrid is required, not selected automatically. Context follows the installed profile; a failed Hybrid load is reported instead of retrying as Standard.${reload}`;
  }
  const policy = status?.hybrid_available
    ? "Hybrid is allowed, not forced. Automatic reuses Auto Tune's measured winner for this model and backend; otherwise it uses installation defaults. Hybrid is not always faster."
    : "No Hybrid profile is configured for this app. Automatic uses Standard here; allowing Hybrid does not install or activate it.";
  const budget = status?.hybrid_context_budget ?? status?.hybrid_context;
  const profile = status?.hybrid_available && Number.isInteger(budget)
    ? ` The installed Hybrid profile defaults to ${budget.toLocaleString()} context tokens; model limits and a matching Auto Tune result may change this.` : "";
  const manual = Number(context);
  const warning = Number.isInteger(manual) && manual >= 512
    ? ` The displayed ${manual.toLocaleString()}-token context is not requested manually in Automatic; switching modes may change it.` : "";
  return `${running}${maximum}${policy} Automatic manages context and run settings.${profile}${warning} Use Auto Tune to measure supported contexts, or uncheck Hybrid for editable Standard-only settings.${reload}`;
}

export function statusPollDelay(status, hidden) {
  if (hidden) return 30000;
  return status?.tuning?.active || status?.chat_busy || status?.chat_queued ||
    ["loading", "stopping"].includes(status?.state) ? 1500 : 5000;
}

export function restoreModelControls(status, initialized, control) {
  const active = status.model && ["loading", "ready", "stopping"].includes(status.state);
  if (initialized && !active) return null;
  const saved = status.saved_model_settings || status;
  const settings = active ? status : status.default_context
    ? { ...saved, context: status.default_context } : saved;
  const fields = {
    model: "model", execution_mode: "execution-mode", context: "context", placement: "placement",
    cpu_threads: "cpu-threads", batch_threads: "batch-threads", cpu_poll: "cpu-poll",
    host_op_offload: "host-op-offload", op_offload_min_batch: "op-offload-min-batch",
    kv_cache_type: "kv-cache-type", load_mode: "load-mode", expert_cache_mib: "expert-cache",
    fit_target_mib: "fit-target", draft_model: "draft-model", draft_type: "draft-type", draft_tokens: "draft-tokens",
  };
  for (const [field, id] of Object.entries(fields)) control(id).value = String(settings[field] ?? "");
  control("allow-hybrid").checked = settings.execution_mode !== "standard";
  return settings;
}

export function bindReasoningEffort(primary, quick, invalid) {
  const values = new Set(["default", "low", "medium", "high"]);
  quick.value = primary.value;
  for (const [source, target] of [[primary, quick], [quick, primary]]) {
    source.addEventListener("change", () => {
      if (!values.has(source.value)) {
        invalid("Select a supported reasoning effort.");
        return;
      }
      target.value = source.value;
    });
  }
}

export function precheckText(data) {
  const automatic = data.automatic, hybrid = data.required_hybrid;
  const lines = [
    `Hybrid eligibility: ${data.hybrid_candidate ? "Candidate - runtime unverified" : "Not eligible with this installation"}.`,
    `Architecture: ${data.architecture}${data.layout ? `; ${data.layout.expert_count} experts, ${data.layout.block_count} blocks` : ""}.`,
    `Automatic defaults: ${automatic.execution_profile === "standard" ? "Standard backend" : "Hybrid candidate"}. ${automatic.reason}`,
    `Require hybrid: ${data.hybrid_candidate ? `${hybrid.initialization} plan, ${hybrid.transfer} transfers, ${hybrid.context.toLocaleString()} context, ${hybrid.cache_mib.toLocaleString()} MiB cache.` : hybrid.reason}`,
    data.scope,
    ...data.limitations,
  ];
  return lines.join("\n\n");
}

export class ModelPrecheck {
  constructor({ input, button, output, request, changed }) {
    Object.assign(this, { input, button, output, request, changed });
    this.serial = 0;
    this.busy = false;
    button.addEventListener("click", () => this.check());
    input.addEventListener("input", () => this.invalidate());
    input.addEventListener("change", () => this.check());
  }

  invalidate() {
    this.serial += 1;
    this.busy = false;
    this.output.textContent = "Model path changed. Check hybrid eligibility for the selected file.";
    this.changed();
  }

  async check() {
    const model = this.input.value.trim(), serial = ++this.serial;
    this.busy = false;
    if (!model) {
      this.output.textContent = "Enter a local GGUF path to check hybrid eligibility.";
      this.changed();
      return;
    }
    this.busy = true;
    this.output.textContent = "Reading GGUF metadata and installation policy; no model is being loaded...";
    this.changed();
    try {
      const data = await this.request("/api/v1/model/precheck", { model });
      if (serial === this.serial && model === this.input.value.trim()) this.output.textContent = precheckText(data);
    } catch (error) {
      if (serial === this.serial && model === this.input.value.trim()) {
        this.output.textContent = `Pre-check failed: ${error.message}`;
      }
    } finally {
      if (serial === this.serial) {
        this.busy = false;
        this.changed();
      }
    }
  }
}

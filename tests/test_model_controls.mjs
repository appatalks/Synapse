import test from "node:test";
import assert from "node:assert/strict";
import { bindEngineSelection, bindReasoningEffort, bindSettingsTabs, draftControls, elapsed, engineSettingsText, loadingText, modelLoadPayload, ModelPrecheck, precheckText, restoreModelControls, statusPollDelay, tuningPayload } from "../synapse_app/web/model-controls.mjs";

class Select extends EventTarget {
  constructor(value) { super(); this.value = value; }
  choose(value) { this.value = value; this.dispatchEvent(new Event("change")); }
}

test("settings tabs switch panels and support keyboard navigation", () => {
  class Tab extends EventTarget {
    constructor() { super(); this.attrs = {}; this.focused = false; }
    setAttribute(key, value) { this.attrs[key] = value; }
    focus() { this.focused = true; }
  }
  const tabs = [new Tab(), new Tab(), new Tab()];
  const panels = new Map(tabs.map((tab) => [tab, { hidden: true }]));
  const select = bindSettingsTabs(tabs, (tab) => panels.get(tab));
  select(tabs[0]);
  assert.equal(panels.get(tabs[0]).hidden, false);
  tabs[1].dispatchEvent(new Event("click"));
  assert.equal(tabs[1].attrs["aria-selected"], "true");
  assert.equal(panels.get(tabs[0]).hidden, true);
  const right = new Event("keydown", { cancelable: true });
  Object.defineProperty(right, "key", { value: "ArrowRight" });
  tabs[1].dispatchEvent(right);
  assert.equal(right.defaultPrevented, true);
  assert.equal(tabs[2].attrs["aria-selected"], "true");
  assert.equal(tabs[2].focused, true);
  assert.equal(panels.get(tabs[2]).hidden, false);
});

test("Hybrid checkbox allows Automatic and disables Hybrid through Standard without forcing it", () => {
  const toggle = new Select(""), select = new Select("auto"), changes = [];
  bindEngineSelection(toggle, select, (previous) => changes.push(previous));
  assert.equal(toggle.checked, true);
  toggle.checked = false;
  toggle.dispatchEvent(new Event("change"));
  assert.equal(select.value, "standard");
  toggle.checked = true;
  toggle.dispatchEvent(new Event("change"));
  assert.equal(select.value, "auto");
  select.choose("hybrid");
  assert.equal(toggle.checked, true);
  select.choose("standard");
  assert.equal(toggle.checked, false);
  assert.deepEqual(changes, ["auto", "standard", "auto", "hybrid"]);
});

test("restored engine choices synchronize the checkbox without dispatching a change", () => {
  const toggle = new Select(""), select = new Select("auto"), changes = [];
  const sync = bindEngineSelection(toggle, select, (previous) => changes.push(previous));
  select.value = "standard";
  sync();
  assert.equal(toggle.checked, false);
  assert.deepEqual(changes, []);
  toggle.checked = true;
  toggle.dispatchEvent(new Event("change"));
  assert.deepEqual(changes, ["standard"]);
});

test("engine guidance distinguishes measured defaults, manual context and unavailable Hybrid", () => {
  const automatic = engineSettingsText({ hybrid_available: true, hybrid_context_budget: 16384 }, "auto", "142128");
  assert.match(automatic, /allowed, not forced/);
  assert.match(automatic, /measured winner/);
  assert.match(automatic, /otherwise it uses installation defaults/);
  assert.match(automatic, /not always faster/);
  assert.match(automatic, /142.?128-token context is not requested manually/);
  assert.match(automatic, /16.?384 context tokens/);
  assert.match(automatic, /switching modes may change it/);
  assert.match(engineSettingsText({}, "auto", ""), /No Hybrid profile is configured/);
  assert.match(engineSettingsText({}, "standard", "142128"), /Auto Tune use Standard only/);
  assert.match(engineSettingsText({}, "hybrid", "16384"), /failed Hybrid load is reported instead of retrying/);
  for (const mode of ["auto", "standard", "hybrid"]) {
    assert.match(engineSettingsText({ model: "/models/target.gguf", state: "ready", context: 16384 }, mode, "16384"),
      /Unload the active model.*next load/);
  }
});

test("Hybrid permission cannot be mistaken for the actual active engine or tuning objective", () => {
  const status = { model: "/models/target.gguf", state: "ready", context: 262144,
    hybrid_active: false, hybrid_available: true, engine_source: "measured",
    tuning: { model: "/models/target.gguf", goal: "maximum", recommendation: { settings: { context: 262144 } } } };
  const text = engineSettingsText(status, "auto", "262144");
  assert.match(text, /^Running now: Standard \(Hybrid is not active\) at 262.?144 context tokens/);
  assert.match(text, /Maximum Context tuning prioritizes capacity and long-prompt time, not fastest generation/);
  assert.match(engineSettingsText({ ...status, hybrid_active: true }, "auto", "262144"), /^Running now: Hybrid/);
  assert.doesNotMatch(engineSettingsText({ ...status, state: "loading" }, "auto", "262144"), /Running now/);
  for (const changes of [{ engine_source: "manual" }, { context: 16384 }, { model: "/models/another.gguf" }]) {
    assert.doesNotMatch(engineSettingsText({ ...status, ...changes }, "auto", "262144"), /Maximum Context tuning prioritizes/);
  }
});

test("status polling backs off while idle or hidden and stays responsive during work", () => {
  for (const status of [null, { state: "stopped" }, { state: "ready", chat_busy: false }, { state: "error" }]) {
    assert.equal(statusPollDelay(status, false), 5000);
    assert.equal(statusPollDelay(status, true), 30000);
  }
  for (const status of [{ state: "loading" }, { state: "stopping" }, { state: "ready", chat_busy: true },
    { state: "ready", chat_queued: 1 }, { state: "stopped", tuning: { active: true } }]) {
    assert.equal(statusPollDelay(status, false), 1500);
    assert.equal(statusPollDelay(status, true), 30000);
  }
});

test("Auto Tune honors Standard-only opt-out without forcing Hybrid on unsupported systems", () => {
  const settings = { model: "/models/target.gguf", goal: "balanced", placement: "auto",
    kv_cache_type: "f16", confirm: true };
  assert.deepEqual(tuningPayload(settings, "standard"), { ...settings, include_hybrid: false });
  for (const mode of ["auto", "hybrid"]) assert.deepEqual(tuningPayload(settings, mode), settings);
  assert.equal(tuningPayload({ ...settings, placement: "cpu" }, "auto").placement, "auto");
  assert.equal(tuningPayload({ ...settings, placement: "cpu" }, "standard").placement, "cpu");
  assert.equal(settings.include_hybrid, undefined);
});

test("reasoning selectors share the initial value and synchronize in both directions", () => {
  const primary = new Select("medium"), quick = new Select("default");
  const errors = [];
  bindReasoningEffort(primary, quick, (error) => errors.push(error));
  assert.equal(quick.value, "medium");
  quick.choose("high");
  assert.equal(primary.value, "high");
  primary.choose("low");
  assert.equal(quick.value, "low");
  quick.choose("default");
  assert.equal(primary.value, "default");
  assert.deepEqual(errors, []);
});

test("invalid reasoning effort is reported and cannot change the request selector", () => {
  const primary = new Select("default"), quick = new Select("default"), errors = [];
  bindReasoningEffort(primary, quick, (error) => errors.push(error));
  quick.choose("unlimited");
  assert.equal(primary.value, "default");
  assert.equal(errors.length, 1);
});

test("loading feedback distinguishes verification, elapsed time and quiet output without a fake ETA", () => {
  const text = loadingText({ phase: "Verifying experimental hybrid execution", elapsed_seconds: 125,
    last_output_age_seconds: 60, waiting_for: ["full routed-layer coverage"] });
  assert.match(text, /2m 5s elapsed/);
  assert.match(text, /Waiting for full routed-layer coverage/);
  assert.match(text, /No new backend output for 1m 0s/);
  assert.doesNotMatch(text, /remaining|%/);
  assert.equal(loadingText(null), "");
  assert.equal(elapsed(59.9), "59s");
});

const candidate = {
  architecture: "future-moe", hybrid_candidate: true, layout: { expert_count: 7, block_count: 3 },
  automatic: { execution_profile: "standard", reason: "Native fitting is preferred for this small model." },
  required_hybrid: { initialization: "causal", transfer: "staged", context: 16384, cache_mib: 8192 },
  scope: "Read-only metadata; no backend started.",
  limitations: ["Kernel support and memory fit are unverified.", "Speed and quality are unverified."],
};

test("pre-check separates candidate eligibility from Automatic's actual selection and unverified capabilities", () => {
  const text = precheckText(candidate);
  assert.match(text, /Candidate - runtime unverified/);
  assert.match(text, /Automatic defaults: Standard backend/);
  assert.match(text, /Require hybrid: causal plan, staged transfers/);
  assert.match(text, /Kernel support and memory fit are unverified/);
  assert.match(text, /Speed and quality are unverified/);
  const unavailable = precheckText({ ...candidate, hybrid_candidate: false,
    required_hybrid: { reason: "No hybrid installation profile found." } });
  assert.match(unavailable, /Not eligible with this installation/);
  assert.match(unavailable, /No hybrid installation profile/);
  const provider = precheckText({ ...candidate, automatic: {
    execution_profile: "provider-candidate", reason: "Runtime verification is required." } });
  assert.match(provider, /Automatic defaults: Registered provider \(verification required\)/);
  assert.doesNotMatch(provider, /Automatic defaults: Hybrid candidate/);
});

function precheck(request) {
  const input = new Select("/models/example.gguf"), button = new EventTarget(), output = { textContent: "" };
  const view = new ModelPrecheck({ input, button, output, request, changed: () => {} });
  return { input, button, output, view };
}

test("pre-check sends only the selected path, displays results and surfaces errors", async () => {
  const calls = [];
  const { view, output } = precheck(async (...args) => { calls.push(args); return candidate; });
  await view.check();
  assert.deepEqual(calls, [["/api/v1/model/precheck", { model: "/models/example.gguf" }]]);
  assert.match(output.textContent, /Hybrid eligibility: Candidate/);
  assert.equal(view.busy, false);
  const failing = precheck(async () => { throw new Error("GGUF metadata is truncated."); });
  await failing.view.check();
  assert.equal(failing.output.textContent, "Pre-check failed: GGUF metadata is truncated.");
  assert.equal(failing.view.busy, false);
});

test("editing the path invalidates results and prevents stale requests from replacing a newer check", async () => {
  const pending = [];
  const { view, input, output } = precheck(() => new Promise((resolve, reject) => pending.push({ resolve, reject })));
  const first = view.check();
  input.value = "/models/second.gguf";
  input.dispatchEvent(new Event("input"));
  assert.match(output.textContent, /Model path changed/);
  const second = view.check();
  pending[0].resolve(candidate);
  await first;
  assert.equal(view.busy, true);
  assert.match(output.textContent, /Reading GGUF metadata/);
  pending[1].resolve({ ...candidate, architecture: "second" });
  await second;
  assert.match(output.textContent, /Architecture: second/);
  input.value = "/models/third.gguf";
  const third = view.check();
  input.dispatchEvent(new Event("input"));
  pending[2].reject(new Error("obsolete failure"));
  await third;
  assert.doesNotMatch(output.textContent, /obsolete failure/);
});

test("empty paths do not send inspection requests", async () => {
  const { view, input, output } = precheck(() => assert.fail("Unexpected request"));
  input.value = " ";
  await view.check();
  assert.match(output.textContent, /Enter a local GGUF path/);
  assert.equal(view.busy, false);
});

test("draft controls preserve default-off behavior and restrict Hybrid to native MTP", () => {
  const status = { speculation_enabled: true, backend_kind: "llama.cpp" };
  assert.equal(draftControls({ ...status, speculation_enabled: false }, "standard", "mtp").disabled, true);
  assert.equal(draftControls(status, "standard", "none").inputDisabled, true);
  assert.equal(draftControls(status, "standard", "dflash").inputDisabled, false);
  assert.equal(draftControls(status, "hybrid", "dflash").inputDisabled, true);
  assert.equal(draftControls(status, "hybrid", "mtp").inputDisabled, false);
  assert.equal(draftControls(status, "auto", "mtp").inputDisabled, false);
  assert.equal(draftControls(status, "hybrid", "mtp").maximum, 31);
  assert.equal(draftControls(status, "standard", "mtp").maximum, 32);
  const experimental = draftControls({ ...status, backend_kind: "ik_llama.cpp" }, "standard", "mtp");
  assert.equal(experimental.mtpDisabled, true);
  assert.equal(experimental.inputDisabled, true);
});

test("Automatic and Hybrid payloads retain the explicit MTP draft instead of silently dropping it", () => {
  const settings = { model: "/models/target.gguf", execution_mode: "hybrid", context: 16384,
    cpu_threads: 8, batch_threads: 16, cpu_poll: 50, expert_cache_mib: 6144, kv_cache_type: "f16",
    draft_type: "mtp", draft_model: "/models/mtp.gguf", draft_tokens: 4 };
  assert.deepEqual(modelLoadPayload(settings), {
    model: settings.model, execution_mode: "hybrid", kv_cache_type: "f16",
    draft_type: "mtp", draft_model: settings.draft_model, draft_tokens: 4,
    cpu_threads: 8, batch_threads: 16, cpu_poll: 50, expert_cache_mib: 6144,
  });
  assert.deepEqual(modelLoadPayload({ ...settings, execution_mode: "auto" }), {
    model: settings.model, execution_mode: "auto", kv_cache_type: "f16",
    draft_type: "mtp", draft_model: settings.draft_model, draft_tokens: 4,
  });
  const standard = { ...settings, execution_mode: "standard", draft_type: "dflash" };
  assert.equal(modelLoadPayload(standard), standard);
});

const savedSettings = {
  model: "/models/manual.gguf", execution_mode: "standard", context: 142128, placement: "cpu",
  cpu_threads: 4, batch_threads: 8, cpu_poll: 0, host_op_offload: false, op_offload_min_batch: 256,
  kv_cache_type: "f16", load_mode: "none", expert_cache_mib: 0, fit_target_mib: 2048,
  draft_model: null, draft_type: "none", draft_tokens: 9, hybrid_variant: "auto",
};

function modelControls() {
  const fields = new Map();
  return { fields, control: (id) => {
    if (!fields.has(id)) fields.set(id, { value: "" });
    return fields.get(id);
  } };
}

test("a stopped service restores every saved manual control without loading or selecting Automatic", () => {
  const { control } = modelControls();
  const status = { ...savedSettings, model: null, state: "stopped", execution_mode: "auto", context: 4096,
    saved_model_settings: savedSettings };
  assert.equal(restoreModelControls(status, false, control), savedSettings);
  const expected = {
    model: "/models/manual.gguf", "execution-mode": "standard", context: "142128", placement: "cpu",
    "cpu-threads": "4", "batch-threads": "8", "cpu-poll": "0", "host-op-offload": "false",
    "op-offload-min-batch": "256", "kv-cache-type": "f16", "load-mode": "none",
    "expert-cache": "0", "fit-target": "2048", "draft-model": "", "draft-type": "none", "draft-tokens": "9",
  };
  for (const [id, value] of Object.entries(expected)) assert.equal(control(id).value, value, id);
  assert.equal(control("allow-hybrid").checked, false);
  control("context").value = "131072";
  assert.equal(restoreModelControls(status, true, control), null);
  assert.equal(control("context").value, "131072");
  assert.equal(status.model, null);
  assert.equal(status.state, "stopped");
});

test("shared context preference overrides an idle saved context without changing active runtime context", () => {
  const { control } = modelControls();
  restoreModelControls({ state: "stopped", model: null, default_context: 131072,
    saved_model_settings: savedSettings }, false, control);
  assert.equal(control("context").value, "131072");
  restoreModelControls({ ...savedSettings, state: "ready", model: "/models/active.gguf",
    context: 32768, default_context: 131072 }, true, control);
  assert.equal(control("context").value, "32768");
});

test("active runtime settings override older saved controls; idle polling and unload preserve edits", () => {
  const { control } = modelControls();
  const status = { ...savedSettings, model: "/models/current.gguf", context: 32768,
    execution_mode: "auto", state: "ready", saved_model_settings: savedSettings };
  assert.equal(restoreModelControls(status, true, control), status);
  assert.equal(control("model").value, status.model);
  assert.equal(control("execution-mode").value, "auto");
  assert.equal(control("allow-hybrid").checked, true);
  assert.equal(control("context").value, "32768");
  const stopped = { ...status, model: null, state: "stopped" };
  assert.equal(restoreModelControls(stopped, true, control), null);
  assert.equal(control("model").value, status.model);
  assert.equal(control("context").value, "32768");
});

test("first runs use runtime defaults and speculative settings remain visible for explicit revalidation", () => {
  const { control } = modelControls();
  restoreModelControls({ ...savedSettings, model: null, execution_mode: "auto", context: 4096,
    state: "stopped", saved_model_settings: null }, false, control);
  assert.equal(control("model").value, "");
  assert.equal(control("execution-mode").value, "auto");
  assert.equal(control("context").value, "4096");
  const draft = { ...savedSettings, draft_type: "mtp", draft_model: "/models/draft.gguf", draft_tokens: 4 };
  restoreModelControls({ state: "stopped", saved_model_settings: draft, speculation_enabled: false }, false, control);
  assert.equal(control("draft-type").value, "mtp");
  assert.equal(control("draft-model").value, draft.draft_model);
  assert.equal(control("draft-tokens").value, "4");
});

test("manual Hybrid restores its explicit method without pinning Automatic to a stale method", () => {
  const settings = { ...savedSettings, execution_mode: "hybrid", hybrid_variant: "hosted" };
  const { control } = modelControls();
  restoreModelControls({ state: "stopped", saved_model_settings: settings }, false, control);
  assert.equal(control("allow-hybrid").checked, true);
  assert.equal(modelLoadPayload(settings).hybrid_variant, "hosted");
  assert.equal(modelLoadPayload({ ...settings, execution_mode: "auto" }).hybrid_variant, undefined);
});

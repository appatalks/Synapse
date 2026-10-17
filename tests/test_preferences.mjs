import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import vm from "node:vm";

const web = existsSync(new URL("../synapse_app/web/", import.meta.url))
  ? "../synapse_app/web/" : "../tools/vrambridge/web/";
const { bindChatInput } = await import(new URL(`${web}chat-input.mjs`, import.meta.url));
const themeScript = readFileSync(new URL(`${web}theme.js`, import.meta.url), "utf8");

function composer(options = {}) {
  const input = new EventTarget(), send = { disabled: false }, calls = [];
  bindChatInput(input, { requestSubmit: (button) => calls.push(button) }, send);
  const event = Object.assign(new Event("keydown", { cancelable: true }), { key: "Enter", ...options });
  return { input, send, calls, event, dispatch: () => input.dispatchEvent(event) };
}

test("Enter sends through the existing form validation/submit path", () => {
  const c = composer();
  c.dispatch();
  assert.deepEqual(c.calls, [c.send]);
  assert.equal(c.event.defaultPrevented, true);
});

test("Shift+Enter and modified Enter retain native behavior", () => {
  for (const modifier of ["shiftKey", "ctrlKey", "altKey", "metaKey"]) {
    const c = composer({ [modifier]: true });
    c.dispatch();
    assert.deepEqual(c.calls, []);
    assert.equal(c.event.defaultPrevented, false);
  }
});

test("IME composition and commit keys do not send or swallow the composition", () => {
  for (const options of [{ isComposing: true }, { keyCode: 229 }]) {
    const c = composer(options);
    c.dispatch();
    assert.deepEqual(c.calls, []);
    assert.equal(c.event.defaultPrevented, false);
  }
});

test("disabled Send and repeated Enter preserve the draft without submitting", () => {
  const disabled = composer();
  disabled.send.disabled = true;
  disabled.dispatch();
  const repeat = composer({ repeat: true });
  repeat.dispatch();
  for (const c of [disabled, repeat]) {
    assert.deepEqual(c.calls, []);
    assert.equal(c.event.defaultPrevented, true);
  }
});

test("other keys and previously handled events do not submit", () => {
  const other = composer({ key: "a" });
  other.dispatch();
  assert.equal(other.event.defaultPrevented, false);
  const handled = composer();
  handled.event.preventDefault();
  handled.dispatch();
  assert.deepEqual(other.calls, []);
  assert.deepEqual(handled.calls, []);
});

function theme(stored = null, options = {}) {
  const listeners = {}, selectListeners = {}, windowListeners = {}, warnings = [], writes = [];
  const root = { dataset: {} }, select = { value: "", addEventListener: (event, callback) => { selectListeners[event] = callback; } };
  const status = { textContent: "", hidden: true }, meta = { setAttribute: (_, value) => { meta.content = value; } };
  const document = {
    documentElement: root,
    querySelector: () => meta,
    getElementById: (id) => id === "theme-selector" ? select : status,
    addEventListener: (event, callback) => { listeners[event] = callback; },
  };
  const window = {
    localStorage: {
      getItem: () => { if (options.readError) throw Error("storage read denied"); return stored; },
      setItem: (key, value) => { if (options.writeError) throw Error("storage write denied"); writes.push([key, value]); },
    },
    addEventListener: (event, callback) => { windowListeners[event] = callback; },
  };
  vm.runInNewContext(themeScript, { document, window, console: { warn: (...args) => warnings.push(args) } });
  return { root, select, status, meta, warnings, writes, boot: () => listeners.DOMContentLoaded(),
    change: (value) => { select.value = value; selectListeners.change(); },
    storage: (newValue, key = "synapse.theme") => windowListeners.storage({ key, newValue }) };
}

test("dark is the backward-compatible default and initial preference applies before DOM readiness", () => {
  assert.equal(theme().root.dataset.theme, "dark");
  const light = theme("light");
  assert.equal(light.root.dataset.theme, "light");
  assert.equal(light.meta.content, "#f5f7fb");
  assert.deepEqual(light.writes, []);
  light.boot();
  assert.equal(light.select.value, "light");
});

test("theme selection is applied and persisted without changing unrelated storage", () => {
  const t = theme();
  t.boot();
  t.change("light");
  assert.equal(t.root.dataset.theme, "light");
  assert.deepEqual(t.writes, [["synapse.theme", "light"]]);
  t.change("dark");
  assert.equal(t.root.dataset.theme, "dark");
  assert.equal(t.meta.content, "#0b0e14");
  assert.equal(t.status.hidden, true);
});

test("unavailable storage remains visible while in-memory theme switching works", () => {
  const t = theme(null, { readError: true, writeError: true });
  t.boot();
  assert.equal(t.status.hidden, false);
  t.change("light");
  assert.equal(t.root.dataset.theme, "light");
  assert.match(t.status.textContent, /cannot be saved/);
  assert.equal(t.warnings.length, 2);
});

test("invalid saved/selected themes are explicitly rejected", () => {
  const t = theme("neon");
  t.boot();
  assert.equal(t.root.dataset.theme, "dark");
  assert.equal(t.status.hidden, false);
  t.change("unrecognized");
  assert.equal(t.root.dataset.theme, "dark");
  assert.equal(t.select.value, "dark");
  assert.deepEqual(t.writes, []);
  t.change("light");
  assert.equal(t.status.hidden, true);
});

test("theme choice synchronizes across tabs and resets to dark when cleared", () => {
  const t = theme();
  t.boot();
  t.storage("light");
  assert.equal(t.root.dataset.theme, "light");
  assert.equal(t.select.value, "light");
  t.storage("ignored", "other.preference");
  assert.equal(t.root.dataset.theme, "light");
  t.storage("invalid");
  assert.equal(t.root.dataset.theme, "light");
  assert.equal(t.status.hidden, false);
  t.storage(null, null);
  assert.equal(t.root.dataset.theme, "dark");
  assert.equal(t.status.hidden, true);
  assert.deepEqual(t.writes, []);
});

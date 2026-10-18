import test from "node:test";
import assert from "node:assert/strict";
import { bindReasoningEffort, elapsed, loadingText } from "../synapse_app/web/model-controls.mjs";

class Select extends EventTarget {
  constructor(value) { super(); this.value = value; }
  choose(value) { this.value = value; this.dispatchEvent(new Event("change")); }
}

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

import test from "node:test";
import assert from "node:assert/strict";
import { existsSync } from "node:fs";
const web = existsSync(new URL("../synapse_app/web/", import.meta.url))
  ? "../synapse_app/web/" : "../tools/vrambridge/web/";
const { readings, segments, metrics } = await import(new URL(`${web}monitor.mjs`, import.meta.url));
const { viewForHash } = await import(new URL(`${web}navigation.mjs`, import.meta.url));

test("navigation accepts only existing views", () => {
  for (const view of ["run", "chat", "monitor", "connect"]) assert.equal(viewForHash(`#${view}`), view);
  for (const view of ["", "#", "#constructor", "#<script>", "#unknown"]) assert.equal(viewForHash(view), "run");
});

test("all requested monitors plus RAM are present", () => {
  assert.deepEqual(metrics.map(([key]) => key),
    ["speed", "gpu", "vram", "temperature", "power", "pcie", "cpu", "ram", "disk", "context"]);
});

test("real numeric units and multi-GPU aggregation", () => {
  const gpu = { load_percent: 40, vram_used_bytes: 2 * 1024 ** 3, vram_total_bytes: 8 * 1024 ** 3,
    temperature_c: 50, power_w: 80, pcie_rx_bytes_s: 2 * 1024 ** 2, pcie_tx_bytes_s: 1024 ** 2 };
  const sample = { backend: { state: "ready", generation_active: true, tokens_per_second: 42,
    context_used: 1024, context_total: 4096, context_source: "backend_slot" },
  system: { cpu_percent: 20, ram_used_bytes: 4 * 1024 ** 3, ram_total_bytes: 16 * 1024 ** 3,
    disk_read_bytes_s: 3 * 1024 ** 2 },
  gpus: [{ ...gpu, index: 0 }, { ...gpu, index: 1, load_percent: 80, temperature_c: 60 }] };
  const all = readings(sample);
  assert.equal(all.gpu.value, 60);
  assert.equal(all.vram.value, 4);
  assert.equal(all.vram.max, 16);
  assert.equal(all.temperature.value, 60);
  assert.equal(all.power.value, 160);
  assert.equal(all.pcie.value, 4);
  assert.equal(all.pcie.secondary, 2);
  assert.equal(all.disk.value, 3);
  assert.equal(all.context.value, 25);
  assert.equal(all.speed.value, 42);
  assert.equal(readings(sample, "0").gpu.value, 40);
  assert.equal(readings(sample, "1").vram.value, 2);
});

test("missing counters remain gaps instead of invented zeroes", () => {
  const values = readings({ backend: {}, system: {}, gpus: [] });
  for (const key of ["speed", "gpu", "vram", "temperature", "power", "pcie", "context"]) {
    assert.equal(values[key].value, null, key);
  }
  assert.deepEqual(segments([0, null, 2, 3, NaN, -1], 4).map((part) => part.length), [1, 2]);
  const valuesWithUnsupported = readings({ backend: {}, system: {}, gpus: [
    { index: 0, power_w: 30 }, { index: 1, power_w: null }] });
  assert.equal(valuesWithUnsupported.power.value, null);
});

test("context is capped and usage fallback is labeled", () => {
  const context = readings({ backend: { context_used: 5000, context_total: 4096,
    context_source: "reported_usage" } }).context;
  assert.equal(context.value, 100);
  assert.match(context.note, /usage estimate/);
});

test("short generations retain a completed-rate sample before going idle", () => {
  const sample = { backend: { state: "ready", generation_active: false,
    tokens_per_second: 123.5, last_tokens_per_second: 123.5, speed_source: "backend_final_timings" } };
  assert.equal(readings(sample).speed.value, 123.5);
  assert.equal(readings(sample).speed.note, "Completed decode average");
});

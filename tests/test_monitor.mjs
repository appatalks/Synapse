import test from "node:test";
import assert from "node:assert/strict";
import { existsSync } from "node:fs";
const web = existsSync(new URL("../synapse_app/web/", import.meta.url))
  ? "../synapse_app/web/" : "../tools/vrambridge/web/";
const { readings, segments, metrics, fraction, MonitorView } = await import(new URL(`${web}monitor.mjs`, import.meta.url));
const { viewForHash } = await import(new URL(`${web}navigation.mjs`, import.meta.url));

test("navigation accepts only existing views", () => {
  for (const view of ["chat", "monitor", "connect"]) assert.equal(viewForHash(`#${view}`), view);
  for (const view of ["", "#", "#run", "#constructor", "#<script>", "#unknown"]) assert.equal(viewForHash(view), "chat");
});

test("all requested monitors plus RAM are present", () => {
  assert.deepEqual(metrics.map(([key]) => key),
    ["speed", "load", "vram", "temperature", "power", "pcie", "ram", "disk", "context"]);
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
  assert.equal(all.load.value, 20);
  assert.equal(all.load.secondary, 60);
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

test("pie fractions handle zero, full capacity and unavailable totals", () => {
  assert.equal(fraction(0, 128), 0);
  assert.equal(fraction(32, 128), 0.25);
  assert.equal(fraction(128, 128), 1);
  assert.equal(fraction(256, 128), 1);
  for (const [value, total] of [[null, 128], [32, null], [0, 0], [NaN, 1], [-1, 1]]) {
    assert.equal(fraction(value, total), null);
  }
});

test("combined load keeps CPU when GPU sensors are unavailable", () => {
  const load = readings({ system: {cpu_percent: 24}, gpus: [] }).load;
  assert.equal(load.value, 24);
  assert.equal(load.secondary, null);
  const gpuOnly = readings({ system: {}, gpus: [{index:0, load_percent: 30}] }).load;
  assert.equal(gpuOnly.value, undefined);
  assert.equal(gpuOnly.secondary, 30);
});

test("RAM pie separates occupied cache from pressure and never adds overlapping RSS", () => {
  const ram = readings({
    system: {ram_total_bytes: 128 * 1024 ** 3, ram_used_bytes: 80 * 1024 ** 3,
      ram_available_bytes: 110 * 1024 ** 3, ram_cache_bytes: 64 * 1024 ** 3,
      ram_pressure_bytes: 18 * 1024 ** 3, ram_basis: "physical_occupied"},
    backend: {rss_bytes: 62 * 1024 ** 3}
  }).ram;
  assert.equal(ram.value, 80);
  assert.equal(ram.max, 128);
  assert.deepEqual(ram.breakdown.map((item) => item.value), [80, null, null, 64, 110]);
  assert.match(ram.note, /RSS 62.0 GiB \(overlaps\)/);
  assert.equal(fraction(ram.value, ram.max), 0.625);
});

function renderRam(system) {
  class Node {
    constructor() {
      this.children = [];
      this.attributes = {};
      this.style = {};
      this.text = "";
      this.classList = { toggle() {} };
    }
    set textContent(value) { this.text = String(value); this.children = []; }
    get textContent() { return this.text + this.children.map((child) => child.textContent).join(""); }
    setAttribute(key, value) { this.attributes[key] = String(value); }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.text = ""; this.children = children; }
    get firstChild() { return this.children[0]; }
    get lastChild() { return this.children.at(-1); }
  }
  const previous = globalThis.document;
  globalThis.document = {
    createElement: () => new Node(),
    createElementNS: () => new Node(),
    createTextNode: (text) => { const node = new Node(); node.textContent = text; return node; },
  };
  try {
    const ram = { card: new Node(), value: new Node(), description: new Node(), chart: new Node(),
      scale: new Node(), breakdown: new Node(), title: "System RAM", unit: "GiB", pie: true };
    ram.scale.append(new Node(), new Node());
    const monitor = Object.create(MonitorView.prototype);
    Object.assign(monitor, {
      history: [{ time_ms: Date.now(), system, backend: {}, gpus: [], errors: {} }],
      paused: false, gpu: { value: "all" }, status: new Node(), error: new Node(), cards: { ram },
    });
    monitor.render();
    return ram;
  } finally {
    if (previous === undefined) delete globalThis.document;
    else globalThis.document = previous;
  }
}

test("RAM ring, caption and footer consistently show used rather than the free complement", () => {
  for (const [used, percent] of [[0, 0], [32, 25], [128, 100]]) {
    const ram = renderRam({ ram_used_bytes: used * 1024 ** 3, ram_total_bytes: 128 * 1024 ** 3,
      ram_free_bytes: (128 - used) * 1024 ** 3, ram_basis: "physical_occupied" });
    assert.equal(ram.value.textContent, `${used.toFixed(1)}GiB`);
    assert.equal(ram.chart.children.find((node) => node.attributes.class === "pie-used")
      .attributes["stroke-dasharray"], `${percent} 100`);
    assert.equal(ram.chart.children.find((node) => node.attributes.class === "pie-caption").textContent, "used");
    assert.equal(ram.scale.firstChild.textContent, "Used incl. cache");
    assert.equal(ram.scale.lastChild.textContent, `${percent.toFixed(1)}% used`);
    assert.match(ram.chart.attributes["aria-label"], new RegExp(`${percent.toFixed(1)}% Used incl. cache`));
  }
});

test("RAM usage remains unavailable when its capacity or used counter is missing", () => {
  for (const values of [{ ram_used_bytes: 32 * 1024 ** 3 }, { ram_total_bytes: 128 * 1024 ** 3 }]) {
    const ram = renderRam(values);
    assert.equal(ram.scale.lastChild.textContent, "Used: unknown");
    assert.equal(ram.chart.children.some((node) => node.attributes.class === "pie-used"), false);
    assert.equal(ram.chart.children.some((node) => node.attributes.class === "pie-caption"), false);
  }
});

test("Windows RAM shows used percentage while preserving the OS-unavailable definition", () => {
  const ram = renderRam({ ram_used_bytes: 32 * 1024 ** 3, ram_total_bytes: 128 * 1024 ** 3,
    ram_available_bytes: 96 * 1024 ** 3, ram_basis: "os_unavailable" });
  assert.equal(ram.scale.firstChild.textContent, "Used (OS-unavailable)");
  assert.equal(ram.scale.lastChild.textContent, "25.0% used");
  const rows = ram.breakdown.children;
  assert.equal(rows[0].children[0].textContent, "Used (OS-unavailable)32.0 GiB · 25.0%");
  for (const index of [1, 2, 3]) {
    assert.match(rows[index].children[0].textContent, /Unavailable/);
    assert.equal(rows[index].children[1].children.length, 0);
  }
  assert.equal(rows[4].children[0].textContent, "OS available96.0 GiB · 75.0%");
});

test("RAM bars independently show all overlapping Linux counters as shares of total", () => {
  const gb = 1024 ** 3;
  const ram = renderRam({ ram_total_bytes: 128 * gb, ram_used_bytes: 80 * gb,
    ram_free_bytes: 48 * gb, ram_shared_bytes: 0.5 * gb, ram_cache_bytes: 64 * gb,
    ram_available_bytes: 110 * gb, ram_basis: "physical_occupied" });
  const rows = ram.breakdown.children;
  const expected = [
    ["Used incl. cache", "80.0 GiB · 62.5%", "ram-used", "62.5"],
    ["Free", "48.0 GiB · 37.5%", "ram-free", "37.5"],
    ["Shared", "0.5 GiB · 0.4%", "ram-shared", "0.390625"],
    ["Buff/cache (file-backed)", "64.0 GiB · 50.0%", "ram-cache", "50"],
    ["OS available", "110.0 GiB · 85.9%", "ram-available", "85.9375"],
  ];
  expected.forEach(([label, text, color, width], index) => {
    const [heading, bar] = rows[index].children;
    assert.equal(heading.children[0].textContent, label);
    assert.equal(heading.children[1].textContent, text);
    assert.equal(bar.attributes["aria-hidden"], "true");
    assert.equal(bar.children[0].className, `ram-bar-fill ${color}`);
    assert.equal(bar.children[0].style.width, `${width}%`);
  });
  assert.match(rows[5].textContent, /overlap and must not be added/);
  assert.match(rows[5].textContent, /OS available is an estimate/);
});

test("RAM bars preserve zero, missing capacity and invalid counters without inventing shares", () => {
  const gb = 1024 ** 3;
  const mac = renderRam({ram_total_bytes: 8 * gb, ram_used_bytes: 8 * gb,
    ram_free_bytes: 0, ram_available_bytes: 2 * gb, ram_basis: "physical_occupied"});
  assert.equal(mac.breakdown.children[1].children[0].textContent, "Free0.0 GiB · 0.0%");
  assert.equal(mac.breakdown.children[1].children[1].children[0].style.width, "0%");
  for (const index of [2, 3]) assert.match(mac.breakdown.children[index].textContent, /Unavailable/);

  const incomplete = renderRam({ram_used_bytes: 2 * gb, ram_free_bytes: -1,
    ram_basis: "physical_occupied"});
  assert.equal(incomplete.breakdown.children[0].children[0].textContent, "Used incl. cache2.0 GiB · % unavailable");
  assert.equal(incomplete.breakdown.children[0].children[1].children.length, 0);
  assert.match(incomplete.breakdown.children[1].textContent, /Unavailable/);

  const inconsistent = renderRam({ram_total_bytes: 8 * gb, ram_shared_bytes: 9 * gb});
  assert.equal(inconsistent.breakdown.children[2].children[0].textContent, "Shared9.0 GiB · exceeds total");
  assert.equal(inconsistent.breakdown.children[2].children[1].children.length, 0);
});

async function pollingFixture(run) {
  const previous = { document: globalThis.document, window: globalThis.window };
  const timers = new Map(), calls = [];
  let serial = 0, now = 0;
  globalThis.document = { hidden: false };
  globalThis.window = {
    location: { hash: "#chat" },
    clearTimeout(id) { timers.delete(id); },
    setTimeout(callback, delay) {
      timers.set(++serial, { callback, due: now + delay });
      return serial;
    },
  };
  const monitor = Object.assign(Object.create(MonitorView.prototype), {
    polling: false, timer: null, paused: false, cursor: 0, history: [],
    status: {}, error: {}, render() {},
    request: async (path) => { calls.push({ path, time: now }); return { samples: [] }; },
  });
  async function advance(milliseconds) {
    const end = now + milliseconds;
    while (true) {
      const next = [...timers.entries()].sort((a, b) => a[1].due - b[1].due)[0];
      if (!next || next[1].due > end) break;
      timers.delete(next[0]);
      now = next[1].due;
      await next[1].callback();
    }
    now = end;
  }
  try {
    await run({ monitor, calls, timers, advance, document: globalThis.document, window: globalThis.window });
  } finally {
    for (const [name, value] of Object.entries(previous)) {
      if (value === undefined) delete globalThis[name];
      else globalThis[name] = value;
    }
  }
}

test("monitor makes no requests in Chat, Connect, hidden tabs or paused charts", async () => {
  await pollingFixture(async ({ monitor, calls, timers, document, window }) => {
    for (const hash of ["#chat", "#connect", ""]) {
      window.location.hash = hash;
      await monitor.poll();
    }
    window.location.hash = "#monitor";
    document.hidden = true;
    await monitor.poll();
    document.hidden = false;
    monitor.paused = true;
    await monitor.poll();
    assert.equal(calls.length, 0);
    assert.equal(timers.size, 0);
  });
});

test("visible Monitor fetches exactly 30 batches per minute rather than 60", async () => {
  await pollingFixture(async ({ monitor, calls, timers, advance, window }) => {
    window.location.hash = "#monitor";
    await monitor.poll();
    await advance(59999);
    assert.equal(calls.length, 30);
    assert.deepEqual(calls.slice(0, 3).map((call) => call.time), [0, 2000, 4000]);
    assert.equal(timers.size, 1);
    assert.equal(monitor.polling, false);
  });
});

test("leaving Monitor cancels its timer and returning fetches from the retained cursor", async () => {
  await pollingFixture(async ({ monitor, calls, timers, advance, document, window }) => {
    window.location.hash = "#monitor";
    await monitor.poll();
    monitor.cursor = 23;
    document.hidden = true;
    await monitor.poll();
    await advance(60000);
    assert.equal(calls.length, 1);
    assert.equal(timers.size, 0);
    document.hidden = false;
    await monitor.poll();
    assert.equal(calls[1].path, "/api/v1/monitor?after=23");
    window.location.hash = "#chat";
    await monitor.poll();
    await advance(60000);
    assert.equal(calls.length, 2);
    assert.equal(timers.size, 0);
  });
});

test("navigation during an in-flight monitor request cannot create overlapping polls", async () => {
  await pollingFixture(async ({ monitor, timers, document, window }) => {
    let resolve, requests = 0;
    monitor.request = () => { requests += 1; return new Promise((done) => { resolve = done; }); };
    window.location.hash = "#monitor";
    const pending = monitor.poll();
    await monitor.poll();
    assert.equal(requests, 1);
    document.hidden = true;
    resolve({ samples: [] });
    await pending;
    assert.equal(timers.size, 0);
    assert.equal(monitor.polling, false);
  });
});

test("monitor failures stay explicit and are retried only while the view is visible", async () => {
  await pollingFixture(async ({ monitor, timers, window }) => {
    window.location.hash = "#monitor";
    monitor.request = async () => { throw new Error("backend unavailable"); };
    await monitor.poll();
    assert.equal(monitor.error.hidden, false);
    assert.match(monitor.error.textContent, /backend unavailable/);
    assert.equal(timers.size, 1);
    window.location.hash = "#chat";
    await monitor.poll();
    assert.equal(timers.size, 0);
  });
});

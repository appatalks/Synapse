const gib = 1024 ** 3;
const mib = 1024 ** 2;
const valid = (value) => typeof value === "number" && Number.isFinite(value) && value >= 0;
const sum = (devices, key) => devices.length && devices.every((d) => valid(d[key]))
  ? devices.reduce((total, d) => total + d[key], 0) : null;

export const metrics = [
  ["speed", "Generation speed", "tok/s"], ["load", "CPU & GPU load", "%"],
  ["vram", "VRAM", "GiB"], ["temperature", "GPU temperature", "C"],
  ["power", "GPU power", "W"], ["pcie", "PCIe throughput", "MiB/s"],
  ["ram", "System RAM", "GiB"],
  ["disk", "Disk read", "MiB/s"], ["context", "Context fill", "%"],
];

function ramReading(system, backend) {
  const { ram_total_bytes: total, ram_used_bytes: occupied, ram_free_bytes: free,
    ram_cache_bytes: cache, ram_shared_bytes: shared, ram_available_bytes: available } = system;
  const physical = system.ram_basis === "physical_occupied";
  const split = physical && valid(cache);
  const inconsistent = valid(total) && (
    valid(occupied) && occupied > total || valid(free) && free > total ||
    valid(cache) && cache > total ||
    physical && valid(occupied) && valid(free) && occupied !== total - free
  ) || split && valid(occupied) && cache > occupied;
  const used = inconsistent ? null : valid(occupied) ? split ? occupied - cache : occupied : null;
  const usedLabel = split ? "Used excl. buff/cache" : physical ? "Occupied incl. cache"
    : system.ram_basis === "os_unavailable" ? "OS-unavailable" : "RAM usage";
  const centerLabel = split ? "used" : physical ? "occupied"
    : system.ram_basis === "os_unavailable" ? "OS-unavail." : "usage";
  const fullSplit = split && !inconsistent && valid(total) && total > 0 && valid(used) && valid(free);
  return {
    value: valid(used) ? used / gib : null,
    max: valid(total) ? total / gib : null,
    usedLabel, centerLabel, split,
    ring: fullSplit ? [
      { key: "used", label: usedLabel, value: used / gib },
      { key: "cache", label: "Buff/cache (file-backed)", value: cache / gib },
      { key: "free", label: "Free", value: free / gib },
    ] : null,
    breakdown: [
      ["used", usedLabel, used], ["free", "Free", free], ["shared", "Shared", shared],
      ["cache", "Buff/cache (file-backed)", cache], ["available", "OS available", available],
    ].map(([key, label, value]) => ({ key, label, value: valid(value) ? value / gib : null })),
    note: [
      valid(total) ? `${(total / gib).toFixed(1)} GiB total` : "System memory",
      valid(backend.rss_bytes) ? `backend RSS ${(backend.rss_bytes / gib).toFixed(1)} GiB (overlaps)` : null,
      inconsistent ? "RAM breakdown unavailable: inconsistent counters"
        : split && !fullSplit ? "RAM breakdown unavailable: missing counters"
          : !split ? "Cache breakdown unavailable; showing OS-specific usage" : null,
    ].filter(Boolean).join(" · "),
  };
}

export function readings(sample, selection = "all") {
  const devices = (sample.gpus || []).filter((d) => selection === "all" || String(d.index) === selection);
  const b = sample.backend || {}, s = sample.system || {};
  const used = sum(devices, "vram_used_bytes"), total = sum(devices, "vram_total_bytes");
  const load = sum(devices, "load_percent"), rx = sum(devices, "pcie_rx_bytes_s"), tx = sum(devices, "pcie_tx_bytes_s");
  const context = valid(b.context_used) && valid(b.context_total) && b.context_total > 0
    ? Math.min(100, 100 * b.context_used / b.context_total) : null;
  const temps = devices.map((d) => d.temperature_c);
  return {
    speed: { value: b.state === "ready" ? b.tokens_per_second : null,
      note: b.generation_active ? b.speed_source === "backend_slot_counter" ? "Rolling accepted-output counter" : "Backend-reported decode rate"
        : b.speed_source === "backend_final_timings" ? "Completed decode average"
          : valid(b.last_tokens_per_second) ? `Idle · last decode ${b.last_tokens_per_second.toFixed(1)} tok/s` : "No generation yet" },
    gpu: { value: load === null ? null : load / devices.length, max: 100, note: devices.length > 1 ? "Average across selected GPUs" : "Device-wide load" },
    load: { value: s.cpu_percent, secondary: load === null ? null : load / devices.length, max: 100,
      note: valid(b.cpu_logical_cores) ? `System CPU · backend ${b.cpu_logical_cores.toFixed(1)} cores · device-wide GPU` : "System CPU and selected device-wide GPU" },
    vram: { value: used === null ? null : used / gib, max: total === null ? null : total / gib,
      note: total === null ? "NVIDIA memory counter" : `of ${(total / gib).toFixed(1)} GiB · all apps` },
    temperature: { value: temps.length && temps.every(valid) ? Math.max(...temps) : null, max: 100, note: devices.length > 1 ? "Hottest selected GPU" : "GPU sensor" },
    power: { value: sum(devices, "power_w"), note: "GPU board power, not whole-machine power" },
    pcie: { value: rx === null ? null : rx / mib, secondary: tx === null ? null : tx / mib,
      note: rx === null || tx === null ? "Driver PCIe counters" : `RX ${(rx / mib).toFixed(1)} · TX ${(tx / mib).toFixed(1)} MiB/s` },
    cpu: { value: s.cpu_percent, max: 100, note: valid(b.cpu_logical_cores) ? `System · backend ${b.cpu_logical_cores.toFixed(1)} logical cores` : "Whole-machine CPU usage" },
    ram: ramReading(s, b),
    disk: { value: valid(s.disk_read_bytes_s) ? s.disk_read_bytes_s / mib : null, note: "Backend read I/O · see platform notes" },
    context: { value: context, max: 100, note: valid(b.context_used)
      ? `${Math.round(b.context_used).toLocaleString()} / ${b.context_total?.toLocaleString()} tokens · ${b.context_source === "backend_slot" ? "slot occupancy" : "usage estimate"}` : "Waiting for backend context counters" },
  };
}

export function segments(values, maximum) {
  const result = [];
  let current = [];
  values.forEach((value, index) => {
    if (!valid(value)) {
      if (current.length) result.push(current);
      current = [];
    } else {
      current.push([values.length > 1 ? index * 100 / (values.length - 1) : 100,
        40 - Math.min(value / maximum, 1) * 38]);
    }
  });
  if (current.length) result.push(current);
  return result;
}

export function fraction(value, maximum) {
  return valid(value) && valid(maximum) && maximum > 0 ? Math.min(1, value / maximum) : null;
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function svg(tag, attributes) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  return node;
}

export class MonitorView {
  constructor(request) {
    this.request = request;
    this.history = [];
    this.cursor = 0;
    this.paused = false;
    this.polling = false;
    this.timer = null;
    this.cards = {};
    this.gpu = document.getElementById("monitor-gpu");
    this.status = document.getElementById("monitor-status");
    this.error = document.getElementById("monitor-error");
    for (const [key, title, unit] of metrics) {
      const pie = key === "ram" || key === "context";
      const card = element("article", "card metric");
      card.dataset.metric = key;
      card.classList.toggle("pie-metric", pie);
      const value = element("div", "metric-value", "Sampling...");
      const description = element("p", "metric-description");
      const chart = svg("svg", { viewBox: pie ? "0 0 120 120" : "0 0 100 42",
        preserveAspectRatio: pie ? "xMidYMid meet" : "none",
        role: "img", "aria-label": `${title} history; waiting for samples` });
      const scale = element("div", "chart-scale");
      scale.append(element("span", "", "0"), element("span", "", unit));
      card.append(element("h3", "", title), value, description, chart, scale);
      let breakdown = null;
      if (key === "ram") {
        breakdown = element("div", "ram-breakdown");
        card.append(breakdown);
      }
      document.getElementById("monitor-cards").append(card);
      this.cards[key] = { card, value, description, chart, scale, title, unit, pie, breakdown };
    }
    this.gpu.addEventListener("change", () => this.render());
    document.getElementById("monitor-pause").addEventListener("click", (event) => {
      this.paused = !this.paused;
      event.currentTarget.textContent = this.paused ? "Resume charts" : "Pause charts";
      event.currentTarget.setAttribute("aria-pressed", String(this.paused));
      this.render();
      this.poll();
    });
    document.addEventListener("visibilitychange", () => this.poll());
    window.addEventListener("hashchange", () => this.poll());
  }

  visible() {
    return !document.hidden && viewForHash(window.location.hash) === "monitor" && !this.paused;
  }

  async poll() {
    window.clearTimeout(this.timer);
    if (this.polling || !this.visible()) return;
    this.polling = true;
    try {
      const data = await this.request(`/api/v1/monitor?after=${this.cursor}`);
      if (data.reset) {
        this.history = [];
        this.cursor = 0;
      }
      for (const sample of data.samples) {
        if (sample.sequence > this.cursor) {
          this.history.push(sample);
          this.cursor = sample.sequence;
        }
      }
      this.history = this.history.slice(-300);
      const latest = this.history.at(-1);
      if (latest) {
        const options = [{ index: "all", name: "All NVIDIA GPUs" }, ...latest.gpus];
        const identity = JSON.stringify(options.map((d) => [d.index, d.name]));
        if (identity !== this.gpu.dataset.devices) {
          const selected = this.gpu.value;
          this.gpu.replaceChildren(...options.map((device) => {
            const option = element("option", "", device.name);
            option.value = String(device.index);
            return option;
          }));
          this.gpu.value = options.some((d) => String(d.index) === selected) ? selected : "all";
          this.gpu.dataset.devices = identity;
        }
      }
      if (!this.paused) this.render();
      else this.status.textContent = "Charts paused. Background sampling continues.";
    } catch (error) {
      this.error.hidden = false;
      this.error.textContent = `Monitoring unavailable: ${error.message}`;
      this.status.textContent = "Disconnected — displayed samples are not current.";
    } finally {
      this.polling = false;
      if (this.visible()) this.timer = window.setTimeout(() => this.poll(), 2000);
    }
  }

  render() {
    const last = this.history.at(-1);
    if (this.paused) {
      this.status.textContent = "Charts paused. Background sampling continues.";
      return;
    }
    if (!last) return;
    const values = readings(last, this.gpu.value);
    const age = Date.now() - last.time_ms;
    this.status.textContent = `${age > 5000 ? "Stale sample" : "Live"} · updated ${new Date(last.time_ms).toLocaleTimeString()} · ${this.history.length} / 300 samples · 1s interval`;
    const errors = [...Object.values(last.errors), ...Object.values(last.backend.errors || {}),
      ...last.gpus.flatMap((device) => Object.values(device.errors))];
    this.error.hidden = errors.length === 0;
    const errorText = [...new Set(errors)].join(" · ");
    if (this.error.textContent !== errorText) this.error.textContent = errorText;
    for (const [key, view] of Object.entries(this.cards)) {
      const reading = values[key];
      const value = reading.value;
      const available = valid(value) || key === "load" && valid(reading.secondary);
      view.card.classList.toggle("unavailable", !available);
      if (key === "load") {
        view.value.replaceChildren();
        for (const [label, number, style] of [["CPU", value, "cpu-value"], ["GPU", reading.secondary, "gpu-value"]]) {
          const stat = element("span", style, valid(number) ? `${number.toFixed(1)}%` : "Unavailable");
          stat.prepend(element("small", "", label));
          view.value.append(stat);
        }
      } else {
        view.value.replaceChildren(document.createTextNode(valid(value)
          ? value.toFixed(key === "temperature" || key === "power" ? 0 : 1) : "Unavailable"));
        if (valid(value)) view.value.append(element("small", "", view.unit));
      }
      view.description.textContent = reading.note;
      if (view.pie) {
        const part = key === "ram" && (reading.split && !reading.ring || valid(value) && valid(reading.max) && value > reading.max)
          ? null : fraction(value, reading.max);
        const label = part === null ? "Unavailable" : `${(part * 100).toFixed(1)}%`;
        view.chart.replaceChildren(svg("circle", { cx: 60, cy: 60, r: 44, class: "pie-track" }));
        if (part !== null && key === "ram" && reading.ring) {
          let offset = 0;
          for (const item of reading.ring) {
            const percentage = 100 * item.value / reading.max;
            view.chart.append(svg("circle", { cx: 60, cy: 60, r: 44, pathLength: 100,
              "stroke-dasharray": `${percentage} 100`, "stroke-dashoffset": `${-offset}`,
              transform: "rotate(-90 60 60)", class: `pie-${item.key}` }));
            offset += percentage;
          }
        } else if (part !== null) {
          view.chart.append(svg("circle", { cx: 60, cy: 60, r: 44, pathLength: 100,
            "stroke-dasharray": `${part * 100} 100`, transform: "rotate(-90 60 60)", class: "pie-used" }));
        }
        const text = svg("text", { x: 60, y: 64, "text-anchor": "middle", class: "pie-label" });
        text.textContent = label;
        view.chart.append(text);
        if (key === "ram" && part !== null) {
          const caption = svg("text", { x: 60, y: 80, "text-anchor": "middle", class: "pie-caption" });
          caption.textContent = reading.centerLabel;
          view.chart.append(caption);
        }
        const ringSummary = key === "ram" && reading.ring
          ? reading.ring.map((item) => `${item.label} ${item.value.toFixed(1)} GiB (${(100 * item.value / reading.max).toFixed(1)}%)`).join(", ")
          : `${label} ${reading.usedLabel || "used"}`;
        view.chart.setAttribute("aria-label", `${view.title}: ${ringSummary}; ${reading.note}`);
        view.scale.firstChild.textContent = reading.usedLabel || "Used";
        view.scale.lastChild.textContent = key === "ram" ? part === null ? "Breakdown: unavailable" : `${label} ${reading.centerLabel}`
          : part === null ? "Remaining: unknown" : `${((1 - part) * 100).toFixed(1)}% ${reading.freeLabel || "available"}`;
        if (key === "ram") {
          view.breakdown.replaceChildren();
          for (const item of reading.breakdown) {
            const row = element("div", "ram-row");
            const heading = element("div", "ram-row-heading");
            const exceedsTotal = valid(item.value) && valid(reading.max) && item.value > reading.max;
            const share = exceedsTotal ? null : fraction(item.value, reading.max);
            const text = !valid(item.value) ? "Unavailable"
              : `${item.value.toFixed(1)} GiB · ${exceedsTotal ? "exceeds total" : share === null ? "% unavailable" : `${(share * 100).toFixed(1)}%`}`;
            heading.append(element("span", "", item.label), element("span", "", text));
            const track = element("div", "ram-bar");
            track.setAttribute("aria-hidden", "true");
            if (share !== null) {
              const fill = element("div", `ram-bar-fill ram-${item.key}`);
              fill.style.width = `${share * 100}%`;
              track.append(fill);
            }
            row.append(heading, track);
            view.breakdown.append(row);
          }
          view.breakdown.append(element("p", "ram-breakdown-note",
            reading.ring
              ? "The ring adds used, buff/cache and free. Shared overlaps used; OS available overlaps other values and is an estimate."
              : "Each bar is a share of total RAM. Values may overlap; OS available is an estimate."));
        }
        continue;
      }
      const all = this.history.map((sample) => readings(sample, this.gpu.value)[key]);
      const maximum = Math.max(1, reading.max || 0, ...all.flatMap((r) =>
        [r.value, r.secondary].filter(valid)));
      view.chart.replaceChildren(svg("path", { d: "M0 2H100 M0 21H100 M0 40H100", class: "chart-grid" }));
      for (const secondary of [false, true]) {
        for (const part of segments(all.map((r) => secondary ? r.secondary : r.value), maximum)) {
          view.chart.append(svg("polyline", { points: part.map((point) => point.join(",")).join(" "),
            class: `chart-line${secondary ? " secondary-line" : ""}` }));
        }
      }
      const summary = key === "load"
        ? `CPU ${valid(value) ? value.toFixed(1) + "%" : "unavailable"}, GPU ${valid(reading.secondary) ? reading.secondary.toFixed(1) + "%" : "unavailable"}`
        : valid(value) ? `${value.toFixed(1)} ${view.unit}` : "unavailable";
      view.chart.setAttribute("aria-label", `${view.title}: ${summary}; ${this.history.length} historical samples`);
      view.scale.lastChild.textContent = `${maximum.toFixed(1)} ${view.unit}`;
    }
  }
}
import { viewForHash } from "./navigation.mjs";

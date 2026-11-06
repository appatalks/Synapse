# Monitoring and platform support

SYNAPSE keeps at most 300 one-second samples in memory. There is no telemetry
upload or disk history. Opening Monitor does not restart a model or clear a chat.
Pausing charts pauses display updates, not sampling.

Monitor fetches batches every two seconds only while that view is visible
and charts are not paused. Chat, Connect and hidden browser tabs do not fetch
Monitor data. Returning to Monitor or resuming charts fetches immediately and
catches up from the retained sample cursor; once started, server-side sampling
still retains at most 300 one-second samples.

App status refreshes every five seconds when idle, every 1.5 seconds during
loading, unloading, tuning or chat work, and every 30 seconds in a hidden tab.
Returning to a visible tab refreshes immediately. Multiple tabs still have
their own status polling loops. Process CPU/RAM/I/O telemetry is sampled once
per second; backend lifecycle/readiness checks retain their 0.2-second cadence.
The reduced polling is not a measured model-throughput optimization.

Successful status, Monitor and model-list GET access messages are DEBUG-level,
not repeated INFO output. Failed requests, model actions and backend errors
remain visible. External clients still control how often they request
`/v1/models`; Synapse does not suppress or cache their actual requests.

CPU and GPU load share one history graph with independently labeled values:
mint is whole-machine CPU, blue is the selected device-wide GPU load. They
are not added into a misleading utilization total. System RAM and context
fill use live doughnut pie charts, not historical line charts.
Missing capacity or usage leaves an explicitly unavailable ring.
Experimental-engine details and warnings live on this tab.
On Linux, the System RAM ring shows used excluding the displayed buff/cache
and buff/cache as colored arcs; the unfilled track represents free memory,
which is also shown in the statistics. The large value, ring center and footer
show used excluding buff/cache. Buff/cache is file cache and buffers
excluding shared memory (not reclaimable slab); used still includes shared
memory and other allocations, including reclaimable slab. This is not
necessarily the same accounting as the `free` command.

The colored bars also show shared and OS-available memory as fractions of
total. These overlap other values and must not be added to the ring segments.
OS available is an estimate, not an allocation guarantee. Backend RSS overlaps
used and cache. Unsupported counters are shown as unavailable. Windows does not
provide free, shared or buff/cache through this monitor and shows an explicitly
labeled OS-unavailable ring instead; macOS does not provide shared or buff/cache
and shows occupied memory including cache. If Linux counters are inconsistent
or the split is incomplete, the breakdown ring is unavailable.

| Counter | Scope and source |
| --- | --- |
| Generation speed | Backend timings, including reasoning, or a rolling difference of actual accepted-output token counters. Never text-length estimates. |
| GPU load / VRAM / temperature / power | Installed NVIDIA driver's NVML, per GPU or aggregated. Device-wide, including other apps. Missing individual counters remain unavailable. |
| PCIe | NVML RX/TX snapshots, converted from driver KB/s counters with a 1024-byte unit. RX is into the GPU; TX is out. Short driver measurement windows can miss bursts; this is not a transfer integral or bus utilization percentage. |
| CPU | Whole-machine OS CPU-time deltas. Backend logical-core use is shown separately. Windows systems with more than 64 processors may report the calling processor group's load. |
| System RAM | Linux: used (physical occupancy minus file cache/buffers), cache/buffers and free. macOS: physical occupancy including cache. Windows: OS-unavailable RAM (total minus OS availability). Shared, backend RSS and OS availability overlap other values. |
| Disk read | Backend process read-counter deltas. Linux uses physical `read_bytes`; macOS uses `ri_diskio_bytesread`. Windows counts process read transfers, which can include cached/non-disk I/O. |
| Context fill | Backend slot-token occupancy divided by actual context size. When slots are unsupported, reported input + output usage is labeled as an estimate. It is not the physical KV-cache byte allocation. |

## Release-candidate targets

File-backed model weights are resident RAM even when Linux counts them in its
reclaimable page cache. A low `total - MemAvailable` value does not mean the
model is not using RAM. The Linux RAM ring shows cached file pages separately
from other occupied memory, while keeping the original physical occupancy,
OS-available value and pressure estimate separate in the API. macOS availability
is estimated as free plus inactive pages. Driver-pinned pages can make
OS-reported availability optimistic; it is not a safe-allocation guarantee.
Backend RSS and cache overlap: adding them would double-count mapped model pages.
On Linux, shared memory is separated from disk-backed file cache, and process
RSS is broken down into file-backed, anonymous, and shared/driver-mapped pages
where the OS provides those counters. CUDA host allocations need not appear
as ordinary anonymous memory; do not assume every RAM copy is private memory.
Higher occupancy by itself is not evidence of faster generation.

| Platform | Application / native backend | CPU, RAM, process read I/O | GPU sensors | Research hybrid engine |
| --- | --- | --- | --- | --- |
| Linux | llama.cpp CPU/CUDA/other supported builds | `/proc` | NVIDIA NVML | Optional, Linux/CUDA only; not quality-qualified |
| Windows | llama.cpp `.exe`, CPU/CUDA/other supported builds | Windows APIs | NVIDIA NVML | Not supported by this candidate |
| macOS | llama.cpp CPU/Metal build | Mach, sysctl, libproc | AMD/Metal GPU sensors unavailable | Not supported by this candidate |

Hardware-free lifecycle tests and native OS-counter smoke tests run in the
Linux/Windows/macOS CI matrix. Only Linux/NVIDIA inference has been exercised
on the project maintainer's physical hardware. CI does not establish GPU,
large-model, performance or answer-quality qualification on other platforms.

NVIDIA sensor monitoring needs the driver, not a Python NVML package.
An absent driver, permission failure, unsupported sensor or disconnected backend
is displayed explicitly; graphs contain gaps rather than invented zero values.
GPU utilization alone is not proof of useful compute or efficient inference.

The loopback-only `/api/v1/monitor?after=N` endpoint supplies incremental,
bounded numeric samples. It never returns prompts, generated text, token IDs,
backend credentials or raw slot responses. Model reload resets request metrics;
historical points retain their own context denominator.

## Model Controls and browsing

Chat is the default page. **Model Controls** opens a keyboard-accessible dialog
for loading/unloading, runtime settings, max output tokens and reasoning effort.
Closing it preserves the settings; they apply to the next message. Runtime
selection stays locked while a model is loaded, and generation settings cannot
change during a browser request.

**Allow experimental Hybrid acceleration** is permission for Automatic, not an
indicator that Hybrid is running. The explanation names the actual loaded
engine and context. A matching **Maximum Context** result is labeled as
prioritizing capacity and long-prompt time rather than generation speed.
For example, Standard at a measured 262K capacity is not a matched speed
comparison against Standard or Hybrid at 142K. Review the active engine,
actual context and tuning goal before attributing a speed change to Hybrid.

For an unbound causal layout, **Require hybrid** permits a manual GPU expert-cache
budget in Advanced performance. This can leave room for a model's larger KV
cache/backbone without lowering context or dropping experts. It does not guarantee
fit. Automatic mode retains the installation budget, and checkpoint-bound training
plans retain their fixed budgets; a manual override cannot borrow or alter them.

In the composer, Enter uses the same Send action; Shift+Enter keeps a new line.
IME text composition, modified Enter shortcuts and held/repeated keys do not
accidentally send messages. Enter cannot submit while Send is disabled.
The sidebar's Dark/Light selector applies to every page, chart and dialog,
persists only `synapse.theme` in browser local storage, and synchronizes across
open tabs. No conversation or model settings are stored. If storage is blocked,
theme switching still works for the page and an explicit persistence notice appears.

**Browse models** lists local folders and GGUF filenames with Home, parent and
root navigation. Selecting a model fills its absolute path; it does not upload
or read the model into the browser. Hidden dotfiles are excluded. Each request
examines at most 4,096 entries and displays at most 512 matches, with an explicit
truncation notice. Enter a more specific folder to narrow a large listing.
Filesystem permissions are respected, and missing/inaccessible folders are
reported instead of appearing empty. You can still supply a direct model path,
including another Windows drive's folder.

The guarded local `POST /api/v1/models/browse` endpoint accepts `{"path":"..."}`
or `{}` for Home. It returns directory/file names and paths, never file contents.
Like the rest of the local API, it must not be exposed to remote users.

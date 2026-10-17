# Monitoring and platform support

SYNAPSE keeps at most 300 one-second samples in memory. There is no telemetry
upload or disk history. Opening Monitor does not restart a model or clear a chat.
Pausing charts pauses display updates, not sampling.

| Counter | Scope and source |
| --- | --- |
| Generation speed | Backend timings, including reasoning, or a rolling difference of actual accepted-output token counters. Never text-length estimates. |
| GPU load / VRAM / temperature / power | Installed NVIDIA driver's NVML, per GPU or aggregated. Device-wide, including other apps. Missing individual counters remain unavailable. |
| PCIe | NVML RX/TX snapshots, converted from driver KB/s counters with a 1024-byte unit. RX is into the GPU; TX is out. Short driver measurement windows can miss bursts; this is not a transfer integral or bus utilization percentage. |
| CPU | Whole-machine OS CPU-time deltas. Backend logical-core use is shown separately. Windows systems with more than 64 processors may report the calling processor group's load. |
| System RAM | OS total minus available. macOS available memory is estimated as free plus inactive pages, not a memory-pressure measurement. |
| Disk read | Backend process read-counter deltas. Linux uses physical `read_bytes`; macOS uses `ri_diskio_bytesread`. Windows counts process read transfers, which can include cached/non-disk I/O. |
| Context fill | Backend slot-token occupancy divided by actual context size. When slots are unsupported, reported input + output usage is labeled as an estimate. It is not the physical KV-cache byte allocation. |

## Release-candidate targets

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

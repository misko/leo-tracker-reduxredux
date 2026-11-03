# Experimental 20 ms capture and offline analysis

The opt-in implementation captures 50,000 complex sample times per receiver at
2.5 MS/s, computes power from those exact samples, and saves every accepted
window. Dual-RX CI16 requires 400,000 bytes per window. GLRT runs after recording.
Existing 120/240/360 ms detector contracts and production services are unchanged.

The next increment is split into [two continuous scanning workstreams](scan-workstreams.md):
ordered eight-channel 20 ms IQ output, and a standalone FPGA power scanner.
Both target device-owned looping until an explicit STOP request. The finite,
weighted prototype described here remains the measured implementation baseline.

## Entry points and ownership

- `src/leo/scanner/short_window.py`: exact sample geometry, owned IQ, power,
  quality decisions, assembly and round-robin scheduling for pull sources.
- `src/leo/scanner/short_window_recording.py`: capture orchestration, live power
  events, bounded writer admission, cancellation and incomplete-session reporting.
- `src/leo/acquisition/short_window_ppu.py`: public PPU fixed-dwell campaign,
  actual firmware-selected target order, hardware counters and restoration.
- `src/leo/acquisition/short_window_iio.py`: diagnostic USB/IP provider and the
  separate bounded TX2 loopback tone owner. Legacy refills have UNKNOWN validity.
- `src/leo/contracts/short_window_recording.py` and
  `src/leo/storage/short_window.py`: additive version-1 recording format, bounded
  compressed chunks, per-window hashes, atomic sealing and verified reading.
- `native/adaptive/detector/short_window_glrt.h`: exact-length single/dual-RX
  offline entry points using the existing native numerical implementation.
- `src/leo/analysis/starlink/native_short_window.py`: reusable native contexts.
- `tools/analyze_short_window_recording.py`: all-window offline analysis with
  hash-bound templates, library, input and configuration, and resumable output.

The firmware chooses weighted targets without activity feedback in this initial
PPU mode. Its three-second revisit bound is different from a guaranteed full
eight-channel round-robin sweep. Repeated visits are kept and correctly labeled.
No target is filtered out to simulate a host-controlled order.

## Recording command

Preview is radio-free and creates no recording. Supply actual IF frequencies;
the following eight nearby frequencies are the cable-loopback test plan, not a
Starlink RF channel mapping:

```bash
leo scan windows --host 192.168.1.15 \
  --serial 104000b29905000e17000800065934759d \
  --if-hz 1800000000 --if-hz 1810000000 \
  --if-hz 1820000000 --if-hz 1830000000 \
  --if-hz 1840000000 --if-hz 1850000000 \
  --if-hz 1860000000 --if-hz 1870000000 \
  --duration-seconds 5 --max-visits 512 \
  --transition-budget-ms 20 \
  --output-root /srv/bulk/leo/short-window-qualification --dry-run
```

Remove `--dry-run` only for an authorized collection. PPU captures are currently
bounded to 300 seconds; the repository's independent RF authorization rule still
applies. Use explicit output paths outside QNAP. CLI progress distinguishes
capture-complete/power, writer-accepted, and final publication. A writer backlog
is bounded by bytes and count, including the in-flight write. Overload stops the
session with an explicit failure; it never silently removes quiet windows.

The default transition allowance is the conservative 100 ms. The 20 ms setting
is experimental: it shortens the provider's selection-to-valid boundary and
must be assessed on the intended firmware, transport and RF setup. It is not
an extra host sleep added after an already guarded validity receipt.

PPU's current campaign API uses physical LAN READSCAN. USB enumeration of the
same serial verifies device identity but does not turn these measurements into
USB-streaming measurements. `--provider iio --host usb:BUS.DEVICE.INTERFACE`
selects the diagnostic USB path; it reports UNKNOWN activity because ordinary
refills do not attest the valid sample boundary.

## Offline analysis

Build the native detector using its [build instructions](../../native/adaptive/detector/README.md).
Then supply the exact/control template pair and library explicitly:

```bash
.venv/bin/python tools/analyze_short_window_recording.py /absolute/recording \
  --library /absolute/libleo-adaptive-detector.so \
  --exact-template /absolute/exact.c128 \
  --control-template /absolute/control.c128 \
  --output /absolute/analysis.jsonl
```

The analyzer processes complete quiet windows as well as active windows, using
one reusable context. Partial or integrity-invalid windows retain explicit skip
records. It preserves actual counter intervals and generation; it does not
invent sample UTC from host arrival time. Resumption verifies source and output
hashes before continuing. A common operator-selected template pair is marked
as unqualified for RF mapping; these outputs do not publish tracking observations.

## Local qualification on 2026-10-09

Device `.15` matched USB serial `104000b29905000e17000800065934759d`, with firmware
`v0.60-plutoplus-spf-adaptive-native-fastlock`. User-confirmed wiring is TX2 through
a **20 dB attenuator** and a tee to RX1/RX2. Splitter and cable loss are additional
and have not been calibrated. RX gain is fixed at 40 dB in these smokes.

The five-second receive-only run recorded 44 complete dual-RX windows, covered
all eight profiles including slot zero, reported no missing samples, and passed
reader hash checks. All 88 quiet receiver results were retained. Offline GLRT
processed all 44 windows in 0.0901 seconds on this host, including verified I/O,
context setup and publication but excluding Python startup/imports. This is a
small noise-recording throughput observation, not a worst-case detector budget.
See [offline evaluation](../../reports/2026_10_09_short_window/native-rx8-smoke-v2-evaluation.json).

The matched five-second TX2 runs use a +100 kHz DDS tone at 1.8 GHz, TX attenuation
60 dB, and eight IF targets spaced by 10 MHz. All successful windows contain
exactly 50,000 sample times per receiver. A separate qualification receipt keeps
tone spectra, ADC12 clipping counts, terminal counters and restoration readbacks.
Raw IQ and per-run receipts are under `/srv/bulk/leo/short-window-qualification`.

| Five-second run | Windows retained | Median valid-start spacing | First complete eight-target coverage |
| --- | ---: | ---: | ---: |
| TX −60 dB, transition 100 ms | 50 | 120.220 ms | 2,828.805 ms / 31 visits |
| TX −60 dB, transition 20 ms | 131 | 40.231 ms | 564.424 ms / 15 visits |
| TX −30 dB, transition 20 ms | 129 | 40.272 ms | 1,270.922 ms / 33 visits |

The runs used different recorded scheduler seeds. The window counts are observed
throughput, not a paired identical-order benchmark. Initial coverage measures
the first valid start through completion of the eighth distinct target. At about
40.2 ms per changed-channel visit, a strict eight-target round robin would take
about 322 ms. The existing weighted scheduler does **not** guarantee that sweep;
these measured coverage times make the distinction visible.

The stronger tone test yielded **36 ACTIVE receiver decisions** at target zero
and **222 QUIET decisions** elsewhere using the explicitly named −75 dBFS test
policy. The tone was at +100 kHz on both receivers in all 18 destination visits,
with no ADC12 clipping. This test threshold is not a deployed Starlink threshold.

The final normal recording CLI run captured, admitted and durably wrote all
134 windows, using three chunks. Peak writer backlog was four windows / 1.6 MB.
Whole-command elapsed time was 9.290 seconds, including preparation and
restoration around the five-second acquisition. Delivery-to-classification
latency was median 1.001 ms, p95 2.705 ms and p99 3.173 ms; classification compute
p99 was 2.748 ms. The proposed 1 ms p99 target was **not met** and remains an
optimization gate. These are host-delivery latencies, not sample-time RF latencies.

Across six successful short runs, 536 complete dual-RX windows were verified.
Final readback confirmed TX muted and original RX settings restored. Detailed
[radio verification](../../reports/2026_10_09_short_window/radio-short-window-verification.json),
[timing and coverage summary](../../reports/2026_10_09_short_window/hardware-summary.json),
and [timing/power figure](../../reports/2026_10_09_short_window/loopback-timing-and-power.png)
are saved with the per-run receipts. No production service or firmware was deployed.

An initial attempt to start TX after OPENM failed because firmware locks TX
attributes during a scan. No tone was enabled in that attempt. Its incomplete
recording was preserved; the original radio settings were restored and checked.
The harness now sets TX after PPU preparation and before OPENM, then releases
the scan owner before restoring TX. It requires an initially muted transmitter,
exact serial selection, finite campaign and watchdog bounds.

## Limits and release gates

Power means mean CI16 component energy normalized to 32768, matching the existing
comparison convention. AD9361 ADC12 clipping is separately flagged even though
the container is int16. ACTIVE means threshold crossing, not Starlink detection.
The default −38 dBFS policy is uncalibrated for this loopback chain; weak but
spectrally visible tones can correctly remain QUIET under that policy.

Unknown LNB LO, polarization or band remains unknown/hypothetical. Power cannot
resolve an RF mapping that the hardware filters out. These smokes validate the
recorder and a cable-loopback tuning path, not Starlink sensitivity or localization.

Still required for production release: raw transition and coded-waveform tests
for stale samples; all directed transitions and wider frequency jumps; held-out
settling tolerances; gain/noise threshold calibration; loaded writer/transport
qualification; strict coverage policy; per-target templates and qualified UTC
projection into tracking; reader/UI deployment followed by an authorized canary.
Keep the [full release plan](short-window-scan-plan.md) as the deployment gate.

Restoration and finalization errors are explicit. A timeout cannot forcibly stop
an already-running filesystem fsync or rename: an incomplete command result
with no publication path requires checking the eventual destination/partial
recording before retrying. No successful durability claim is emitted on timeout.

The initial runtime used PPU Python source commit
`0a07581ab2b60888d85ba6ca1d6c85065bf820e3`, an ABI3-verified native runtime from the
feature-103 environment, and temporary dependency wheels. Repository package
initialization still imports existing analysis dependencies at startup; no GLRT
is executed on the capture path. Freeze a reproducible hardware environment and
record its receipts before deployment; these local paths are development evidence.

## Software validation

The combined focused suite passed 169 tests before the final threshold-label
regression was added; that final change was checked with the affected core/CLI
suites. Coverage includes native 20 ms parity against first/middle/final probes
of existing recorded 120 ms inputs, strict short-input bounds, reusable contexts,
quiet-window replay, interruption/resume, reader corruption, empty/partial IQ,
queue overload, shutdown failures, USB/IP selection, and legacy scanner CLI
compatibility. Golden scientific fixtures were not modified.

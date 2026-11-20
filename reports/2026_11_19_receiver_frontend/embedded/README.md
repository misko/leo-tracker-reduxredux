# Embedded receiver feasibility

Physical Pluto+ measurements cover an earlier saved-IQ receiver through regional position selection at 2.5 MS/s. The 10 MS/s, 20 ms, dual-receiver survey detector now also runs on a Cortex-A9 instruction set under QEMU on authenticated IQ. The latest compact v5 finish still runs in Python and uses native projection for one numerical stage. Full physical timing and peak memory for the 10 MS/s survey receiver through v5 position remain unmeasured. Local USB metadata identified an attached PlutoSDR+ with timestamp support. The board was left untouched.

## Throughput required by the recordings

The two complete host replays retain their original monotonic delivery clocks. The utility verifies the saved SHA-256 and session bindings, checks strictly increasing delivery timestamps, and accounts for every visit as two receiver probes or a capture exclusion. The delivery span is first to last saved delivery. It measures actual arrival demand independently of the nominal `300 s` scan length and the earlier 15-minute study deadline. [Inputs and output](arrival-budget.json) · [Original clock receipts](../../2026_11_18_pipeline_eval/evidence/whole-recording-time.json)

| Recording | Delivery span (s) | Scheduled / eligible dual-RX visits | Mean / peak arrivals per second | Mean eligible CI16 rate (MB/s) | Maximum mean CPU ms/visit with one / two fully available cores |
|---|---:|---:|---:|---:|---:|
| DS26-0036, Oct 25 | 299.966 | 6,769 / 6,765 | 22.55 / 24 | 36.08 | 44.34 / 88.68 |
| DS29-0082, Nov 3 | 299.997 | 6,772 / 4,868 | 16.23 / 22 | 25.96 | 61.63 / 123.25 |

The peak is an exact rolling one-second count of eligible visits. The two-core column is a ceiling for **all** computation, including arrival processing, acquisition, association and position fitting. Reserving one core for source and downstream work leaves at most **44.34 ms of mean detector CPU per dual-receiver visit** on the denser recording. With `A` CPU seconds reserved for the other stages, `N` visits and delivery span `T`, the aggregate detector ceiling per visit is `(2T − A)/N`. The wideband research wrapper is process-serialized. Any design that splits work across cores must count the aggregate CPU and prove it can drain bursts at a bounded queue depth. [Scanner ownership model](../../../native/adaptive/scanner/README.md)

A 20 ms CI16 visit is 1,600,000 bytes with both receivers. Both schedules have about 22.57 arrivals/s before capture exclusions, so an all-valid run at either schedule would send about 36.1 MB/s of valid windows to the detector on average. An uninterrupted dual-RX source produces 80 MB/s, which still matters for transport and DMA during retunes and discarded samples. A complete offline replay timed against the delivery span measures batch capacity. A paced receiver also needs end-of-recording-to-fix latency and a bounded backlog across successive recordings. [Historical 10 MS/s capture transport](../../2026_10_05_recent_10msps/review.txt)

## Measurements on their original boundaries

| Platform and experiment | Input, algorithm and scope | Measured result |
|---|---|---|
| Physical Cortex-A9, Sept 28 | Four saved DS7 20 ms receiver probes at 10 MS/s. Earlier full-search experimental FFT V4 with integer-epoch final GLRT. | 8,614.717 ms mean CPU per receiver probe. |
| Physical Cortex-A9, Sept 29 | 10 MS/s, 120 ms, two receivers. Standalone dwell-preparation experiment. | 242.854 ms control CPU for both receivers, averaged across alternating repetitions. |
| Physical Cortex-A9, Sept 30 | DS9 visit 301, 7.5 MS/s, 120 ms, two receivers. The 22-slot wideband interval/fractional algorithm with −312.5 kHz receiver centers and ±800 kHz residual search. | 55.300 s detector wall, 55.287 s detector CPU, 40,244 KiB process peak RSS. Coarse search used 46.016 s CPU, 83.29% of summed receiver CPU. |
| Physical Cortex-A9, Oct 1 | Three complete 2.5 MS/s DS9 recordings, 120 ms dual-RX dwells, native integer-epoch acquisition then seeds, tracks, orbits, 400-site search and selected-site associations. | 6,649/6,649 dwells with queue depth 48. Loaded downstream times 304.410 and 310.180 s, maximum dwell latency 5.479 s, sampled aggregate RSS 299,516 KiB. One recording selected different grid coordinates between independent ARM and host full-chain runs. |
| x86 corpus host, Nov 18 | Two complete 10 MS/s recordings, 20 ms dual-RX acquisitions, ordinary C detector with fractional evaluation followed by v5 numerical position. | DS26 total 371.30 s, including 176.11 s raw replay/assembly and 195.17 s fit. DS29 total 228.39 s, including 116.94 s raw replay/assembly and 111.44 s fit. |

Sources in row order. [DS7 probe measurements](../../2026_09_28_arm_fft_integration/ARM_RESULTS.md) · [Dwell preparation](../../2026_09_29_arm_wave8_integer_input/README.md) · [Wideband physical profile](../../2026_09_30_native_adaptive_deployment/detector/corrected-wideband-stage-profile-v1/README.md) · [Distinct-recording physical replay](../../2026_10_01_arm_three_scan_sequence/README.md) · [Complete x86 IQ-to-v5 replay](../../2026_11_18_pipeline_eval/README.md)

On the Oct 1 physical replay, detector CPU was 261.494–286.228 s per 300 s recording. Native observation/support projection used 6.901–8.768 s summed wall, seeding 2.832–4.408 s, reconstruction 3.583–5.361 s, orbit generation 5.151–5.660 s, and the 400-site position search 218.393–289.210 s. These stage intervals overlapped. Four repeated copies of one recording met the prerecorded-load gates narrowly with 242,476 KiB sampled process-tree RSS and a minimum 2.148 s downstream margin. A separate Sept 30 saved-candidate replay missed the five-second full-prefix publication gate despite completing each started one-site search. [Distinct-recording stage times](../../2026_10_01_arm_three_scan_sequence/stage-comparison.json) · [Repeated-recording result](../../2026_10_01_native_replay_qualification/cadence-four-queue32-v1/README.md) · [Full-prefix replay](../../../native/adaptive/application/LIVE.md)

The November ordinary detector begins with a proposal-guided search and then evaluates a five-cell epoch lattice at the retained CFO. The wideband detector uses the capture producer's folded, 21-cell coarse CFO search, eight retained basins and conditioned acquisition, with a 22-anchor retry when called for. On four matched November IQ windows, the ordinary fractional detector matched 13 of 15 passing capture-era candidates and added 20. The wideband detector reproduced all 64 retained ranks within tolerance, including the 15 passing candidates. Whole-recording geographic errors for the ordinary detector followed by v5 were 0.231/0.186 km on DS26 and 2.802/2.662 km on DS29 for zero/fitted calibration. The matched historical fitted errors were 1.208 and 0.517 km. The geographic outcomes and detector candidate agreement describe different comparisons. [Matched detector outputs and timings](../../2026_11_19_receiver_streaming/native-geometry/README.md) · [Matched calibrated and zero-calibration positions](../../2026_11_18_pipeline_eval/evidence/full-iq/scorer-errors.csv)

## Same recorded window on host and ARM under QEMU

DS26-0036 visit 0 used 200,000 complex time samples, two receivers, and the exact and rolled-control templates from the bound capture producer. The wideband replay used the saved 0 Hz receiver centers and ±800 kHz bounds. Both ARM binaries were cross-built with the Pluto firmware toolchain for Cortex-A9/NEON hard-float. The short ordinary binary uses the maintained C entry point. The wideband reference uses the existing isolated 20 ms layout patch and the same search settings as its matched x86 trial. Each ARM executable reproduced all **16 of its corresponding host's ranked candidates** within the existing 1e-6 Hz CFO and 1e-10 scalar tolerances. Ranks, integer epochs, fractional status, and margin gates agreed. The maximum fractional-epoch offsets between architectures were 4.56e-15 samples in ordinary mode and 2.97e-15 samples in wideband mode. [Smoke input, binaries and comparisons](same-iq-smoke.json) · [Short wideband patch and host replay](../../2026_11_19_receiver_streaming/native-geometry/README.md)

| Detector on the same CI16 window | x86 call CPU | x86 process peak RSS | QEMU call CPU | QEMU host-process peak RSS |
|---|---:|---:|---:|---:|
| Ordinary plus fractional epoch | 35.865 ms | 41,284 KiB | 427.809 ms | 47,156 KiB |
| Wideband interval plus fractional epoch | 2.824 s | 47,060 KiB | 73.764 s | 52,812 KiB |

The QEMU columns measure the Linux emulator process on x86. They establish the ARM executable and numerical ABI on these inputs. Physical throughput and memory require a board receipt. The ordinary CLI RSS includes setup for its full context. The host wideband replay spent 2.167 s in coarse search, 0.632 s in integer acquisition including 0.568 s in conditioned CFO, and 0.0128 s in fractional refinement. Even a hypothetical zero-cost coarse pass would leave 0.656 s of host detector CPU on this window. The bottleneck spans coarse and conditioned acquisition. An optimization of the fractional lattice alone has little leverage. At the two measured windows per recording, detected mean wideband call costs exceed the whole two-core ceilings by roughly 33× on DS26 and 44× on DS29. These are measured-clip ratios against necessary compute ceilings. [Stage measurements](same-iq-smoke.json)

## Memory and native boundary

The original v5 scientific workers prepare orbit catalogues and tracks and run association, nuisance fitting, cavity replay and conditional post-fit repairs in Python/NumPy. Both calibration arms are exercised on identical detections and search inputs. The C projector replaces orbital interpolation and geometry inside that worker. An existing Cortex-A9/QEMU test covers 18 synthetic cells, with maximum Doppler discrepancy of 7.28e-11 Hz. The full Python worker has no tested Pluto runtime or native equivalent in this repository. The portable native `location` component implements the separate DS9 bounded scorer/search and has physical evidence as shown above. [Compact finish replay](../../2026_11_19_receiver_streaming/finish/README.md) · [Orbit kernel ARM check](../../2026_11_19_receiver_duty/arm-kernel.json) · [Native location contracts](../../../native/adaptive/location/README.md)

For the measured DS26-0036 grid shape of 1,524 satellites and 2,053 times, the compact C projector keeps 24,604,512 bytes of prepared arrays and allocates three 8-byte outputs per cell, another 75,090,528 bytes. The combined 99,695,040 bytes, about 95.08 MiB, cover this call's prepared arrays and output alone. Copies of the orbit bank, scoring arrays, track supports, interpreters and allocator high-water add to those bytes. With one active detector and one acquisition copy, queue depths of 4, 32 and 48 own at most 9.16, 51.88 and 76.29 MiB of 20 ms CI16 payload respectively. The earlier Pluto+ monitor recorded 506,568 KiB total RAM and no swap. This makes peak resident memory during overlapping capture, detection and both fit arms a separate qualification gate. [Grid sizes](../../2026_11_19_receiver_duty/grid-development.json) · [Projector allocation](../../../tools/pipeline_eval/variants/orbit_projector.py) · [Archived device memory telemetry](../../2026_09_30_native_adaptive_deployment/live-qualification/revisitfix-120ms-smoke-monitor.jsonl)

A new one-core x86 run measured the stock DS26-0036 compact v5 worker from stored detector rows through its completed position fits. It used **204.37 s wall, 179.63 s CPU and 1,389,240 KiB max RSS** for the measured invocation including its waited workers. That RSS is 2.74 times the archived Pluto+'s total available physical RAM before capture or detector work. It establishes an additional resource gate for porting the current implementation. Memory use of a redesigned native solver requires its own measurement. [Peak memory receipt](compact-position-memory.json)

Both fit arms reproduced the prior coordinates, associated observation count, objective and conditional RMS. Zero calibration gave 1.278 km position error and 74.761 Hz conditional RMS. Fitted calibration gave 1.208 km and 74.682 Hz. The largest component wall times within the profiled call were reassociation admission (40.03 s), initial inference (30.16 s), native preparation (28.20 s), conservative recovery (26.85 s), family fit (19.63 s) and cavity fit (16.47 s). These wall stages on one archived observation inventory characterize downstream work independently from the waveform detector. [Independent fit controls](../../2026_11_19_receiver_streaming/finish/comparison.json)

## Reproduction

From the repository root, generate the arrival- and throughput-budget receipt using the existing read-only archive bindings.

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.embedded_deadline
.venv/bin/python -m pytest -q tests/pipeline_eval/test_embedded_deadline.py
```

For the same-IQ smoke, use the [matched survey replay instructions](../../2026_11_19_receiver_streaming/native-geometry/README.md), select DS26-0036 visit 0, and retain the files produced by its `_manifest` helper before cleanup. Compare the raw CI16 and both templates with `same-iq-smoke.json`. Build the pinned wideband source with `short-dwell.patch` and `--target arm-cortex-a9 --enable-server-reference`. Build the maintained `native/adaptive/detector/build.py` with `--target arm-cortex-a9` for the ordinary short CLI. The ARM compiler, sysroot, and FFTW inputs are in the build receipts. The float FFTW version is 3.3.10, configured with `--host=arm-linux-gnueabihf --enable-float --enable-neon --disable-shared --enable-static --disable-fortran` and `CFLAGS='-O3 -fPIC -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard'`. Run the wideband replay with `--manifest visits.tsv --deployed-server-interval-fractional` and ordinary with `--rate-hz 10000000 --fractional-epoch` plus the same CI16/template paths. For ARM, use `qemu-arm -cpu cortex-a9 -L "$sysroot"` before the executable. Apply `native_geometry_trial.compare_ranked` to each host/ARM candidate list after normalizing with `ranked_candidate`. [ARM wideband build](wideband-build.json) · [ARM ordinary build](ordinary-build.json)

To repeat the compact worker footprint test on a corpus host, choose one available logical CPU and wrap the bound, single-threaded worker with GNU `time`. The archive verification runs after inference.

```sh
cpu=16
taskset -c "$cpu" /usr/bin/time -f 'wall_s=%e cpu_user_s=%U cpu_system_s=%S max_rss_kib=%M' \
  timeout 240s .venv/bin/python -B - "$cpu" <<'PY'
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from tools.pipeline_eval.__main__ import DEFAULT_OUT, public_cases, references
from tools.pipeline_eval.qualification.compact_finish_eval import FINISH, measured, verify_adapter

panel, refs = references('ds26-common127', ['DS26-0036'])
case, = public_cases(panel, refs, DEFAULT_OUT / 'inputs')
with TemporaryDirectory() as work:
    result = measured(case, FINISH, int(sys.argv[1]), Path(work))
baseline = Path('reports/2026_11_19_receiver_streaming/finish/adapter/DS26-0036.json')
verify_adapter(json.loads(baseline.read_bytes()), result)
print(json.dumps(result, indent=2, allow_nan=False))
PY
```

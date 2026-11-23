# Guarded 32-sample phase recurrence in the signed verifier

Re-anchoring the fractional rotation every 32 samples saved a paired median **13.11 ms** in the native mixed detector and **11.25 ms** in the independent exact-gather CFO tail on the 102 signed DS30-0169 lanes. The complete batch saved **24.36 ms CPU**. Across the scheduled dense, weak and held panels, all 159 native factors and verifier flag records retained their order, signed CFO and timing. The maximum normalized detector score change was **1.22×10⁻¹³**. This is a distinct experimental receiver identity with raw score bytes that can differ. [Complete native receipts](measurements/anchored-phase.json.gz)

## Dependency and guard

The coarse bank and packed and resident signed cancellation already use a recurrence. They keep their original native arithmetic. The earlier bracket method reused time and CFO proposals across visits. The prior frame-relative verifier instead folded a common oscillator into the pilot, changed tiny continuous scores and spent most of its earlier gain when it recomputed every selected score exactly. The present path retains each absolute sample position, Lanczos tap weight, complex multiplication and symbol reduction. It calls the original `sincos` at each block anchor, then multiplies by the one-sample oscillator for the next 31 samples. No phase is reused across visits or between pilot frames. The integer stencil and unaffected original detector stages still use the released code. [Coarse bank](../single-core-2x/receiver-coarse-bank.md) · [Packed cancellation](../single-core-2x/receiver-packed-cancellation.md) · [Resident cancellation](../single-core-2x/receiver-resident-cancel.md) · [Bracket experiment](../single-core-2x/receiver-brackets.md) · [Earlier frame-relative verifier](../single-core-2x/receiver-fractional-phase.md) · [Exact-score repair](../single-core-2x/receiver-fractional-score-consumers.md)

The detector uses the earlier normalized-spectrum enclosure with extra allowance for 31 recurrence steps and absolute phase rounding. The trial must clear both FFT bin gaps and keep its entire margin interval away from the original 0.025 acceptance threshold and 0.1 strong-margin boundary. Unsupported rounding, zero spectrum, and inconclusive guards take the released exact correlator. The original two-factor order check retains its exact retry using both margin radii. The independent CFO tail starts from the exact-gather implementation and adds exact retries near the existing coherence, margin, signed correction, cross-half agreement and signed-band decisions. It also uses exact work at low coherence. The tail collars are experimental safeguards assessed on these panels. They do not establish a universal numerical equivalence guarantee. [Native guards and recurrence builder](anchored_phase.py) · [Guarded spectrum helper](anchored_phase.inc) · [Exact gather baseline](short-cfo-exact-cost.md)

## Signed observed outputs

The controlled detector builds use the frozen 12 ms primary and full 20 ms signed cancellation object closures, with only their verifier object replaced. Pristine relinks reproduced both published DSO digests. The instrumented exact control reproduced each pristine lane factor byte for byte. The two candidate paths match all sampled factor memberships, ordered ranks, original timing and signed native CFO. The native verifier trace checks actual flags, fractional timing and residual bin-derived CFO, including rejected calls and exact retries. The released pilot edges, floor arithmetic, halo and trial per-visit inputs stay bound to the staged manifests. The 159 scheduled native factors include **37 rank-1 residual factors**. [Signed factors and original flag traces](measurements/anchored-phase.json.gz)

The independent frequency update preserved every original amend outcome. Across the scheduled panels and the additional separate all-short weak control, the greatest diagnostic CFO difference was **2.38×10⁻⁹ Hz** and the greatest emitted independent CFO difference was **8.74×10⁻¹⁰ Hz**. The largest change among tail coherence and score outputs was **7.02×10⁻¹³**. These errors describe measured arithmetic on saved waveforms. No position fit or new accuracy comparison was run. [Original fixed-timing CFO reference experiment](short-cfo-refine.md) · [Native outputs](measurements/anchored-phase.json.gz)

| Panel | Full / short lane calls | Short positives | Native factors | Recurrence accepted / attempted | Exact tail retries |
|---|---:|---:|---:|---:|---:|
| Dense mixed, 24 visits | 16 / 32 | 21 | 36 | 35 / 36 | 0 |
| Weak by saved-case mixed schedule, 18 visits | 34 / 2 | 2 | 57 | 56 / 57 | 0 |
| Held DS30-0169 mixed member | 16 / 86 | 45 | 66 | 64 / 66 | 2 |
| Same weak clips forced to short only | 0 / 36 | 34 | 34 | 33 / 34 | 2 |

The weak all-short control strengthens short-path validation on the same 18 clips and is outside the scheduled throughput estimate. Guard tests cover the original acceptance, strong-margin and bin-gap collars. A direct native zero-energy fractional call exercised the actual exact fallback and returned identical scores and flags. Additional tests cover tail decision collars, exact anchor bits and bounded absolute phase error near the signed frequency limits. The staged waveform intake for each panel charged zero block-storage bytes. [Guard fixtures](../../../tests/pipeline_eval/test_anchored_phase.py) · [Zero-energy and boundary results](measurements/anchored-phase.json.gz)

## Paid CPU and scope

Four paired repeats alternate order for each panel. The native column times all scheduled short and full receiver calls, including guard and fallback. The separate tail clock includes conditional invocation, exact retries, diagnostic transfer and the frozen amend rule. The complete batch includes both contributions plus callback preparation and measurement readback. The same small verifier trace is active in both measured detectors. Timing excludes authenticated fixture intake, one-time build and context setup. The relink and measurement DSO build took **1.715 s wall**. [Stage and batch clocks](measurements/anchored-phase.json.gz)

| Panel | Native CPU, stock → recurrence | Independent tail CPU, stock → recurrence | Complete batch CPU, stock → recurrence | Paired batch CPU / elapsed saving |
|---|---:|---:|---:|---:|
| Dense mixed | 81.47 → 73.76 ms | 12.04 → 6.28 ms | 94.40 → 80.82 ms | 12.85 / 12.77 ms |
| Weak mixed | 137.23 → 119.57 ms | 1.20 → 0.69 ms | 139.88 → 121.55 ms | 17.81 / 17.81 ms |
| Held mixed | 146.54 → 133.21 ms | 25.80 → 14.58 ms | 174.10 → 149.28 ms | 24.36 / 24.09 ms |
| Weak short-only control | 45.13 → 41.21 ms | 19.08 → 11.23 ms | 65.13 → 53.17 ms | 11.96 / 12.16 ms |

The held paired reductions were **89.8 µs per short call**, **318.5 µs per full call**, and **250.0 µs per refined short positive**. If those rates carried to the archived dense workload of 11,834 short and 1,696 full calls, detector CPU would fall by **1.60 s**. Applying the tail rate to 6,380 short positives adds a separately projected **1.60 s** versus the exact-gather tail. The conditional total is **3.20 CPU s** before any effect on I/O, fitting and publication. Tail acceleration alone covers only the second term. No whole-recording or wall-time speedup was measured. [Archived dense call counts](dense-full-short-raw.md) · [Original projected tail charges](short-cfo-exact-cost.md)

## Reproduction

The two-source measurement archive SHA-256 is `2cb94ea15f0382b85093db41976220fe63aab71c2c6ffd4f5c63b186bf9c7232`. Seventeen component and adjacent tests passed. The optional weak-primary command reuses the binary digests and receipt of the archived scheduled run. Both benchmarks read only local previously staged waveforms, with no original recording read, acquisition, or solver. [Runner](anchored_phase.py)

```bash
install_root=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
gauss() {
  flock -w 60 -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
    sudo -n -u leo ionice -c2 -n7 nice -n15 taskset -c 2 env \
    TMPDIR=/dev/shm PYTHONPATH="$install_root/src:$PWD:$PWD/src:$install_root" \
    OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 "$@"
}
gauss "$install_root/venv/bin/python" -BP -m reports.ALGO08.v3.anchored_phase /dev/shm/leo-anchored-phase-rebuild
gauss "$install_root/venv/bin/python" -BP -m reports.ALGO08.v3.anchored_phase \
  /dev/shm/leo-anchored-phase-weak-primary-rebuild.json --weak-primary-from /dev/shm/leo-anchored-phase-results02
gauss "$install_root/venv/bin/python" -BP -m pytest -q -p no:cacheprovider \
  --basetemp=/dev/shm/leo-anchored-phase-rebuild-tests tests/pipeline_eval/test_anchored_phase.py \
  tests/pipeline_eval/test_short_cfo_refine.py tests/pipeline_eval/test_short_cfo_exact_cost.py
```

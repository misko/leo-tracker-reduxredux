# Where ALGO08v3 spends acquisition time on DS30-0008

Inside one complete installed-v3 acquisition, the stereo detector callbacks used **37.34 CPU s** and the rest of the path to the solver used **21.62 CPU s**. The callbacks ordered by the prespecified one-in-eight anchor schedule cost **4.59 CPU s**. These are actual timers covering all 6,765 admitted stereo visits. Earlier budgets projected detector cost from short prefixes. [Measured receipt](measurements/acquisition-split-DS30-0008.json) · [Anchor schedule and earlier estimates](anchor-orbit-census.md)

| Instrumented boundary | Stereo visits | Selections | CPU s | Elapsed s |
|---|---:|---:|---:|---:|
| Detector callbacks at anchor visits | 848 | 846 | 4.594 | 4.621 |
| Detector callbacks between anchors | 5,917 | 6,170 | 32.744 | 32.952 |
| Everything outside those callbacks through solver entry | | | 21.623 | 61.955 |
| **In-process publication entry to solver handoff** | **6,765** | **7,016** | **58.961** | **99.528** |

The code added two process clocks and two monotonic clocks per admitted stereo visit. It timed the complete original callback, including continuation. The outside-callback interval includes setup after preflight, authenticated acquisition and input waits, serializing and checking the sealed detector document and publishing the inventory. Host process startup, preflight, cache observation, numerical solving and PNG publication are outside this measurement. All 13,530 ordered probes reproduced the archived detection file byte for byte. The computed file SHA-256 was `2df28e68ea845576ea5e8a02057bce32983dbafb469fa2c4f710a3d89729fa85`. [Runner](acquisition_split.py) · [Archived physical comparison](bounds-physical-pair.md)

Linux reported 37,775 of 1,997,612 compressed input pages resident at launch (1.89%) and charged 8.046 GB of input blocks during the measured run. Cache state matters. The archive's previously warm launch reached the detection file at 52.70 s, with a slightly earlier stopping boundary. [Historical stage clocks](first-55/stage-clocks.csv)

## How much time remains to predict and verify a signal?

With acquisition time (A), solver time (S) and publication time (P), a contender that halves solver time while keeping publication cost must reduce acquisition to at most ((A-P)/2). This follows by comparing the total to ((A+S+P)/2). CPU and elapsed time each require their own inputs.

* **Measured cold elapsed scenario.** Even granting zero publication cost, half of 99.53 s is 49.76 s. The measured 61.96 s outside the callbacks alone exceeds that. Preserving this observed outside time would require a change to input handling, overlap, or the solver speed assumption to reach 2×. Removing receiver work can change the amount of I/O wait. A separate timed candidate and cache-matched control would be needed to establish that effect.
* **Measured CPU scenario.** If outside-callback CPU and anchor CPU stay fixed, and publication is free, the 29.48 s half-acquisition CPU budget has 3.264 s left. Dividing by the 6,170 non-anchor selections gives **0.529 ms per selected signal**, before paying for generation, false proposals or fallback. Charging 2 or 4 hypothetical CPU seconds for publication reduces the allowance to 0.367 or 0.205 ms. These are processor budgets; qualification uses elapsed time.
* **Historical warm elapsed scenario.** Attributing the 37.34 measured callback CPU seconds one-for-one to the older 52.70 s warm acquisition leaves an estimated 15.36 s elsewhere. The older total, solver and publication clocks allow 24.68 s of acquisition. Subtracting those 15.36 s and the 4.59 s of measured anchor work leaves 4.724 s, or **0.766 ms per selected signal**. The previous 0.633 ms estimate used 36.5 projected receiver seconds and mean cost per anchor. Both warm numbers depend on transfer between runs.

The allowances assume the predictor knows which 6,170 detections will survive and tries only those. A real proposal stream must also cover negative lanes, multiple candidate timings, signed cancellation, and any complete two-scan retries. The dense roof recording supports cost attribution. It supplies no independent-site performance or end-to-end successor timing.

## Reproduction

Use a fresh output path under a writable research directory. This reads one saved recording, preserves the sealed detector bytes there, and returns at the first stock solver call. The original receipt is also stored on Gauss beside `v3-dense-acquisition-split/fast-scan-automatic-work`.

```sh
v3_code="$PWD/reports/ALGO08/v3"
v3_payload=/opt/leo-algo08/algo08v3/payload
v3_release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock timeout 210s \
  sudo -n -u leo ionice -c2 -n7 nice -n15 taskset -c 2 env \
  PYTHONPATH="$v3_code:$v3_payload:$v3_release/src:$v3_release" \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$v3_release/venv/bin/python" -BPs "$v3_code/acquisition_split.py" "$new_output"
```

# Profiled Gamma updates on saved ALGO08v3 solves

Minimizing the profiled Gamma objective cut dense native likelihood time from **13.90 to 7.47 CPU seconds**. The complete DS30-0008 saved solve saved **1.08 to 5.48 CPU seconds** across two order-reversed pairs. The installed solve spent **33.80 CPU seconds outside the entire likelihood wrapper**, even including the Python fallback in the measured wrapper. This boundary cannot take the dense solver to 24 seconds by itself. Keep the prototype out of the release. [Saved comparisons](measurements/profiled-gamma.json) · [Dense stage budget](single-core-target.md)

## Update rule

For each noise group, let `r` be the Gamma rate, `a` its fixed shape and `next_r` the ordinary update from the exact Gaussian posterior. Differentiating the profiled negative twice ELBO with respect to `log(r)` gives `2*a*(1 - next_r/r)`. The prior precision rates obey the same expression with their respective shapes and posterior second moments. This uses moments already computed for the ordinary updates. It lets the optimizer use gradients of the objective instead of extrapolating the sequence of updates. [Native overlay](../../../tools/pipeline_eval/variants/algo08_profiled_gamma.py)

Each call starts at the installed initialization and takes at least three ordinary updates. Limited-memory BFGS then proposes a step in log rate scaled by the square root of twice the shape. The proposal is projected to the Gamma floors and clipped to a maximum absolute log-rate step of 0.75. A fresh Gaussian posterior must satisfy sufficient decrease in the full profiled objective, including likelihood power, prior precision, log-volume and Gamma penalties. A rejected trial resumes from the saved ordinary successor. The original `1e−5` maximum log-rate change must be reached, followed by the ordinary successor and the installed final posterior/ELBO readout. A numerical failure or exhausted budget replays the installed cold kernel. A separate trial that reached the fixed point earlier can still differ from a stock call that hit its cap. [Step implementation](../../../tools/pipeline_eval/variants/algo08_profiled_gamma.h) · [Earlier rate proposals](../single-core-2x/solver-robust-updates.md)

The installed dispatch still makes the same layout and condition checks. Layouts unsupported by that dispatch continue through the original Python fallback. Its separate compiled grid factor handoff continues using the installed iteration path. The experiment binds only the native run entry point and uses the installed solver, region, detector packet, causal TLE archive and calibration pair. [Saved trial](profiled_gamma_trial.py)

## Kernel and whole-solve accounting

Five-call median timings of previously captured likelihoods show how the effect varies with the work presented to the native kernel. The two dense native samples took 13.25 → 5.56 ms and 108.01 → 37.28 ms, with 39 → 13 and 256 → 84 updates. The largest conditional residual change across the eight captures was 0.175 Hz, on the dense fit that hit the installed 256-update cap. Its negative twice ELBO decreased by `6.49e−6`. The captured unsupported private-width call returned identical values and made no profiled proposals. Two captured ill-conditioned southern calls replayed cold and returned identical values. [Capture timings](measurements/profiled-gamma-witnesses.json) · [Replay code](profiled_gamma_witnesses.py)

| Installed stage on DS30-0008, instrumented | Wall seconds, installed → profiled | Native C CPU seconds, installed → profiled | Native updates, installed → profiled |
|---|---:|---:|---:|
| Initial search | 15.665 → 10.250 | 8.904 → 3.192 | 22,435 → 7,372 |
| Conservative recovery | 12.639 → 12.596 | 0.868 → 0.605 | 2,666 → 1,681 |
| Family | 8.264 → 8.290 | 1.626 → 1.317 | 4,608 → 3,518 |
| Signed | 2.446 → 2.519 | 0.344 → 0.260 | 999 → 699 |
| Cavity | 5.503 → 5.374 | 0.465 → 0.390 | 1,386 → 1,092 |
| Selected path and grid | Included in total | 1.688 → 1.706 | 4,863 → 4,851 |
| Complete saved solve | **54.698 → 49.231** | **13.896 → 7.471** | **36,957 → 19,213** |

Initial search used 64.1% of baseline native C time and produced 88.9% of the native C saving. Its observed kernel CPU per returned update rose from 397 to 433 μs, which includes the new search overhead and changes in the mix of updates. In conservative recovery, 83 unsupported layouts cost 5.55 CPU seconds through the installed Python path. The candidate also routed 83 calls there. The 356 grid factor handoffs remained active. Native wrapper overhead excluding C cost 1.42 → 1.46 seconds. Including the original fallback, observed likelihood work changed from 39,251 to 21,507 iterations and from 162.53 million to 84.93 million weighted row visits. Those counts exclude trial maps discarded by a cold replay. The candidate separately recorded 14,950 posterior evaluations in its accelerated kernel, with 7,771 accepted proposals, 305 rejected proposals and three cold replays. [Per-stage CPU, wall and count receipts](measurements/profiled-gamma.json)

Erasing the entire native C stage would leave 40.77 CPU seconds. Erasing all time inside the installed likelihood dispatch, including its C path, validation and fallback, would leave 33.80 seconds. An additional 9.80 seconds outside that complete dispatch would still have to disappear to reach a 24-second solve. In the uninstrumented candidate-first pair, the family stage rose from 8.23 to 10.84 wall seconds and initial search saved 2.06 seconds. The order-reversed instrumented pair showed almost no family-stage difference and a 5.41-second initial saving. These are two single pairs. The kernel clock bounds the contribution of the algorithm more directly than the full-run difference. [Both dense pairs](measurements/profiled-gamma.json)

## Saved decisions and calibration

| Saved detector and region | Solve CPU seconds, installed → profiled | Solve wall seconds, installed → profiled | Terminal decision |
|---|---:|---:|---|
| DS30-0008, candidate first | 54.808 → 53.724 | 54.814 → 54.012 | Accepted in both arms, 4,472 associated points |
| DS30-0008, control first with timing audit | 54.666 → 49.190 | 54.698 → 49.231 | Accepted in both arms, 4,472 associated points |
| Southern containing near edge | 4.773 → 4.997 | 4.773 → 4.998 | Accepted in both arms, 266 associated points |
| Northern containing near edge | 5.789 → 5.737 | 5.790 → 5.738 | Accepted in both arms, 302 associated points |
| Northern far-region offer | 9.314 → 7.481 | 9.314 → 7.481 | Both arms withheld with the same two-receiver exterior decision |

The accepted cases retained both owner hashes and optimizer path point counts per round. Endpoint objective replay was exact in each run. The largest endpoint movement was 0.05 mm on DS30-0008, 23.04 mm in the south and 0.012 mm in the north. Both methods completed the same grid sizes. On 81 shared coarse locations per fix, the largest score differences were `9.93e−7`, `6.87e−5` and `6.90e−8`, respectively. The endpoint-centered grid locations and numeric digests changed. The wrong-region case used the same northern detector bytes and a different geographic offer. Both implementations completed 96 exterior probes with identical regional guard evidence. [Positions, digests and geographic controls](measurements/profiled-gamma.json)

| Saved input | Installed RF RMS, `c = 0` / fitted (Hz) | Profiled RF RMS, `c = 0` / fitted (Hz) | Installed error, `c = 0` / fitted (km) | Profiled error, `c = 0` / fitted (km) |
|---|---:|---:|---:|---:|
| DS30-0008 | 129.703040 / 129.662931 | 129.703040 / 129.662931 | 1.638978 / 1.511956 | 1.638978 / 1.511956 |
| Southern containing | 6.502299 / 6.391940 | 6.502301 / 6.391940 | 0.816789 / 1.101409 | 0.816808 / 1.101408 |
| Northern containing | 5.406434 / 5.166631 | 5.406434 / 5.166631 | 0.105690 / 0.140779 | 0.105690 / 0.140779 |

Fitted `c` lowered RF RMS on all three accepted cases. It improved the DS30-0008 location error by 127 m and increased the southern and northern errors by approximately 285 m and 35 m. The station references enter only the post-solve scoring. The southern and northern examples are saved simulated recordings, so this trial provides no independent physical-site validation. The timed boundary ends at numerical path and grid evidence. Raw I/Q and the eight PNGs were outside the comparison. [DS30 reference](../../2026_11_21_ds30_full/reference-audit.json) · [Geographic controls](../regional-release/scoring-key.json)

## Reproduce on Gauss

Use the archived pair paths in the [measurements](measurements/profiled-gamma.json). The dense plain pair used `--reverse` and the audit pair used `--audit`. The northern missing-site offer is `/tmp/leo-regional-qZJKBw4W/public/e99fe65747d72e6b793584a9.json`.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
lock=/tmp/leo-algo08v2-2x-bench/gauss.lock
flock -x "$lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH=src:. OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 "$release/venv/bin/python" -B -c \
  'import sys; from tools.pipeline_eval.variants.algo08_profiled_gamma import build; build(sys.argv[1])' \
  "$library"
flock -x "$lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$payload:$release/src:$release" OPENBLAS_NUM_THREADS=1 \
  OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 "$release/venv/bin/python" -Bs \
  reports/ALGO08/v3/profiled_gamma_trial.py "$pair" "$new_receipt" --library "$library"
```

Nine component and adjacent regression tests passed, including both calibration variants, deterministic replay and exact cold fallback under a constrained iteration budget. [Regression tests](../../../tests/pipeline_eval/test_algo08_profiled_gamma.py)

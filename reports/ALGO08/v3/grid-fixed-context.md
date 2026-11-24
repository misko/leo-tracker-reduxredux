# Fixed standard-grid inputs on DS30-0169

Reusing the fixed curved masks, powers, scale and noise-volume term together with the fixed predictive whitening inputs, Gaussian bias columns and normalization produced no end-to-end grid-strip saving. Four balanced pairs used **0.665771 CPU s released and 0.670564 CPU s candidate**, including closure and workspace construction. The candidate was 0.72% slower and held 2,471,256 additional scratch bytes across the two arms. All 36 released scores reproduced the archived values bit for bit, and every candidate evaluation agreed with the released score and 12 numerical output fields, including location-dependent features, posterior coefficients, calibration residuals and elevation. [Frozen protocol](grid-fixed-context-protocol.md) · [Signed-input receipt](measurements/grid-fixed-context-0169.json)

## What actually changed

The control already reuses phase interpolation within each fixed problem and calls the release's native direct-design selector and posterior-factor export. The candidate prepares one fixed set of curve masks, group indices, powers, scales and noise volume per arm. It keeps the original native row-selection/multiplication port and the original order of retained rows. On the predictive side, it reuses fixed Gaussian row precision, normalization, unit priors, and ordinary and row-weighted bias columns. A private C-order workspace replaces their repeated allocations. The original point-dependent phase and geometry projections, robust posterior, exported factor, whitening triangular solve, full predictive Gram and right-hand side, Cholesky and the two solves all remain in the computation. The earlier rank-one bias collapse changes that algebra and was not installed for this comparison. [Current phase reuse](grid_phase_state_reuse.py) · [Earlier predictive reduction](grid-predictive-reduction.md) · [Candidate implementation](grid_fixed_context.py)

The checked saved inputs are DS30-0169's full named 20 ms packet, its original operator offer and exact causal snapshot roster, and the previously accepted lean-route signed final fit. Each arm used 1,782 conditional and 454 predictive observations over 41 curved slots and 30 predictive tracks. The benchmark reconstructed only this retrospective selected likelihood. The support, signed aliases, ordered predictive entries, measured CFO, clock, noise, hardware, smooth terms, phase widths, sky and orbit modes were bound to the saved witness before accepting the stock replay. Three wholly excluded curved slots were left in the design. Their weights never enter active native rows or the volume, so the unrecorded weights use a neutral placeholder. No optimizer, ranking, waveform, figure generation or new position publication ran. [Replay driver](grid_fixed_context_trial.py)

## Paid strip and whole-grid scale

Each row below represents both calibration arms at the same 18 prespecified standard coordinates. The clocks include fresh likelihood-closure construction and fresh phase caches, the entire per-point objective, and candidate scratch setup. Input validation, prep and the output hashing used for experimental comparison sit outside every paired clock. The phase cache prepared 18 views over the validation strip and eight timed strips, exactly two per strip. All 324 evaluations used the native posterior export and predictive factor. Candidate views admitted all 36 calls in each of its four strips with zero predictive fallback.

| Execution order | Released CPU ms | Candidate CPU ms | Released minus candidate, ms |
| --- | ---: | ---: | ---: |
| Released, candidate | 171.587 | 169.017 | +2.570 |
| Candidate, released | 168.298 | 169.307 | −1.008 |
| Candidate, released | 161.943 | 162.930 | −0.986 |
| Released, candidate | 163.942 | 169.311 | −5.369 |
| Median | 166.120 | 169.162 | |

Total elapsed time was 0.665795 s released and 0.670590 s candidate, measured inside the same single-core process. The existing whole publication recorded 1.686 s elapsed for the standard 179-point grid and 1.831 CPU s for the larger standard-evidence stage. Scaling only the paired node work by 179/18 and charging one closure build projects a 4.1 ms mean slowdown, with individual pair projections spanning 35.1 ms saved to 43.8 ms lost. That spread describes these four repeats on the same input. It supplies neither a confidence interval nor a through-exit clock.

The installed predictive-factor callback logged 280.460 CPU ms across 324 calls in all nine strips. Scaling that measured slice to 358 calls would give approximately **0.310 CPU s** even if every callback operation disappeared, including its required dynamic whitening and full-position linear algebra. The production phase-cache counter recorded 356 calls in the original 179-point publication because the selected endpoints were already memoized, which makes the corresponding projection 0.308 s. The 0.3–0.7 s materiality range is out of reach for the measured fixed-input change. The larger curved/native time remains tied to distinct locations and position-dependent likelihood terms under the unchanged model. No release option was added.

## Reproduction

With the authenticated saved DS30-0169 stage and archived original publication resident under `/dev/shm`, run the checked driver in a fresh process with the installed ALGO08v3 interpreter. The setup-only failed launches did not produce accepted measurements or perform a fit. One of those runs reproduced the saved scores before the candidate source guard stopped on the release's compiled curved selector. The measured driver preserves that selector explicitly.

```bash
flock -x -w 30 /tmp/leo-algo08v2-2x-bench/gauss.lock \
  ionice -c2 -n7 nice -n15 taskset -c 2 sudo -n -u leo env TMPDIR=/dev/shm \
  OMP_THREAD_LIMIT=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 timeout 45s \
  /opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/venv/bin/python -IB \
  "$PWD/reports/ALGO08/v3/grid_fixed_context_trial.py" /dev/shm/grid-fixed-context-reproduced.json
```

The receipt has file SHA-256 `d771f24acd62ad2ac1384a0c3a0069f4af2b506abedc3726437017f50f35207f`. Its witnessed output digest includes both exact score arrays and the per-node numerical fingerprints. Four component tests cover dynamic posterior input, checked curved source, exact weighted/predictive output, and unchanged invalid-input or changed-noise fallback. [Component tests](test_grid_fixed_context.py)

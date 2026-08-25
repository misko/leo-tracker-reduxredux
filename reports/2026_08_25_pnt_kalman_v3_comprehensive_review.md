# Signal-matched PNT Kalman V3 review

Date: 2026-08-25

## Executive decision

The current pilot PNT Kalman V2 is not competitive with a short local-frequency model on the measured signal. Across 12 untouched, estimable dwells in three explicitly stratified replay cohorts, V2 lost every dwell to a causal trailing-20-ms robust frame-CFO line. The within-stratum equal-dwell geometric-mean RMS ratios were 6.8567, 3.6579, and 4.4842, where values above one favor the line. This is decisive evidence against promoting V2. A single inferential aggregate is intentionally not formed because the recent-three replay used persisted-posterior sigma weighting while the two replays added here use equal-weight Huber fitting.

The phrase "Kalman versus 20-ms GLRT" conflates two different roles. The sealed GLRT supplies a coarse candidate, CFO, and epoch. The matched one-step forecast baseline used here is a causal robust line over the preceding 20 ms of frame-CFO observations, downstream of that acquisition. Separately, the true ten-dwell GLRT-rate study found that one sealed multi-second GLRT slope had 60.202 Hz held-out odd-Qin RMS, while reset-debiased local slopes had 33.996 Hz RMS, a 43.529% reduction. Both results say that the signal is locally ramp-like and contains intercept changes that a single smooth trajectory should not absorb.

The implemented remedy is additive research V3, not a mutation of persisted V1/V2 semantics. V3:

- searches the complete approximately 1.333 ms frame epoch as a discrete circular hypothesis, jointly with bounded local CFO;
- retains multiple acquisition basins and adjudicates them on disjoint pilots;
- maximizes the exact and rolled-control hypotheses over the same epoch/CFO nuisance domain;
- keeps only sub-sample timing and timing rate in the Gaussian state after branch selection;
- treats Qin carrier phase as modulo-pi, frame-local nuisance evidence that cannot steer CFO or Doppler rate;
- uses empirical frequency and rate-process floors instead of transplanting the paper covariance; and
- resets all states on caller-qualified continuity segments, rather than smoothing through a refill or timing jump.

On the five August-22 raw dwells, V3 beat its matched causal line in all five, with a geometric-mean ratio of 0.9564. On the August-24 raw cohort, V3 beat the line in all four estimable dwells with a ratio of 0.9736; sparse D4 remained non-estimable. Across the two explicitly stratified cohorts, V3 therefore won all 9 estimable dwells out of 10 attempted. The gains are modest and configuration selection was not a preregistered holdout exercise, so this is evidence that the structural repair works, not yet a production-promotion result.

## What was compared

| Evidence | Candidate | Baseline or validator | Unit and mask |
|---|---|---|---|
| Twelve-dwell filter review | Current pilot PNT Kalman V2 one-step CFO prediction | Causal trailing-20-ms robust frame-CFO line | Pairwise common post-bootstrap frames; recording-anchored one-second block RMS; equal dwell weight within each explicitly stratified replay |
| Five-dwell V3 replays | Pilot PNT Kalman V3 one-step CFO prediction | Same causal line | Same-mask within each tracker; no frame pooling across dwells |
| Ten-dwell raw Doppler study | Sealed multi-second degree-1 GLRT branch slope | Reset-debiased ramp-local slope | Odd Qin held out from even-Qin intercept fitting; 471 local ramps |
| Phase qualification | Exact Qin | Rolled-Qin negative control | Window counts and supported frames, reported separately from CFO forecast error |

The frame-CFO observation is noisy and is not truth. These are comparative prediction and held-out residual metrics, not absolute Doppler-accuracy claims. August-22 and August-24 are different releases/design strata and are shown side by side; frames are never pooled as exchangeable samples.

## What the papers imply for this signal

### Kassas five-state topology

The local paper, `kassas_unveiling_starlink_for_pnt.pdf`, uses the familiar five-state structure: carrier phase, carrier frequency, carrier-frequency rate, code phase, and code-phase rate. That topology is reasonable inside a continuity-qualified tracking arc. It does not justify placing every possible delay branch inside one broad Gaussian timing state.

Section 6 performs a delay/Doppler acquisition search before the local Kalman tracking in Eq. 8. The paper's code-phase measurements come from its own full-beacon prompt/early/late discriminator, and its measurement covariance belongs to that observable. This repository instead measures phase slope and an eight-edge-subcarrier fractional delay from Qin pilots. The paper's numerical R values therefore do not transfer.

The paper also documents recurrent OFDM carrier-phase slips associated with user/CFO changes and abrupt code/Doppler corrections. That is consistent with the local corpus: phase and intercept discontinuities are signal behavior, not merely Gaussian measurement noise.

### Qin pilot model

The local paper, `qin_pilots_starlink_dl.pdf`, separates sample-clock/SFO and carrier-clock/CFO effects in Eq. 19. Its Eq. 21 first performs a two-dimensional lag/Doppler argmax to obtain a nearest-sample frame alignment. Only afterward does Eq. 22 define a small residual delay, and Eqs. 25-26 and 32 fit local phase/CFO and delay/SFO within the frame. The paper retains a frame-specific complex phase nuisance; it does not establish a generally continuous absolute carrier phase between frames.

That ordering matters here:

| Quantity | Correct representation |
|---|---|
| Full frame epoch | Discrete/circular branch over one 750 Hz frame |
| Local fractional delay | Small continuous state after one branch is selected |
| SFO/timing drift | Continuous local rate within a continuity arc |
| Qin carrier phase | Modulo-pi, frame-local nuisance/lock evidence |
| CFO and Doppler rate | Driven by the within-frame phase-slope discriminator, not phase residual feedback |
| Refill or confirmed joint CFO/epoch jump | New segment, new acquisition, new covariance and intercept |

At 2.5 MS/s, one frame is 1/750 s = 1.333333 ms = 3333.333 samples. The integer start hypotheses in the half-open physical interval are therefore 0 through 3333: 3334 candidates, not 3333. Subsequent frame starts must retain the exact `round(k * 3333.333...)` 3333/3334-sample lattice. A typical 15 ppm SFO produces only about 0.3 microseconds, or 0.75 sample, of drift over 20 ms. That is the scale for the local timing state; the full 1.3 ms domain belongs to acquisition.

Carrier phase cannot resolve this full epoch. Delay creates a subcarrier-dependent phase ramp, while the common complex frame phase is an independent nuisance. Averaging circular epoch modes in one enlarged timing covariance would manufacture a nonphysical mean between branches.

## Why V2 failed

1. V2 assumes the GLRT epoch is already exact and searches only plus/minus 0.75 sample around it. It cannot repair a branch error of hundreds or thousands of samples.
2. Full phase feedback couples legitimate frame-local phase changes into frequency/rate through covariance cross-terms. Existing experiments changed fitted slopes by roughly +269 and -228 Hz/s, while frequency-only variants stayed within about 5 Hz/s of the GLRT comparison.
3. Even after the modulo-pi correction, phase lock is rare in real windows. The August-22 V2 replay qualified only 3 of 40 windows. The August-24 D1/D2/D4/D5/D6 evidence qualified 12 of 3000 windows (0.4%), with zero rolled controls.
4. The former one-Hz frequency-noise floor and 500 Hz/s/sqrt(s) rate-process setting were much more confident and smoother than the observed tens-of-hertz frame discriminator and rapidly changing local ramps.
5. Application refills and signal change points are hard discontinuities. A prior corpus audit found 383 of 391 large CFO jumps bracketing exact 262,144-sample refills, often with timing jumps. A single filter that spans such a boundary smears two locklets.
6. A robust jump-filter prototype improved substantially over V2 but still lost to the causal line. Across four untouched complete August-24 dwells it was 3.2% worse in geometric mean and won 0/4; on development dwell D3 it was 4.15% worse. The needed model is local ramps plus explicit boundaries, not merely larger Q or more reset heuristics.

## Twelve untouched dwells: current V2 result

Lower ratios are better; one is parity with the matched causal line. The August-22 and fixed-design August-24 rows use equal-weight Huber lines because the raw discriminator sigma is not exposed. The recent-extension artifact uses the older persisted-posterior frequency sigma with a 15 Hz floor. The cohorts therefore establish breadth and direction, but are not pooled into one exchangeable estimate.

| Stratum | Dwell | V2 RMS (Hz) | 20-ms line RMS (Hz) | Ratio |
|---|---:|---:|---:|---:|
| Aug-22 earlier release | D1 | 188.927 | 39.937 | 4.731 |
| Aug-22 earlier release | D2 | 231.966 | 16.727 | 13.868 |
| Aug-22 earlier release | D3 | 147.659 | 46.630 | 3.167 |
| Aug-22 earlier release | D4 | 198.573 | 14.650 | 13.554 |
| Aug-22 earlier release | D5 | 204.421 | 37.977 | 5.383 |
| Aug-24 fixed design | D1 | 170.713 | 58.966 | 2.895 |
| Aug-24 fixed design | D2 | 187.174 | 47.810 | 3.915 |
| Aug-24 fixed design | D5 | 169.597 | 59.606 | 2.845 |
| Aug-24 fixed design | D6 | 270.388 | 48.703 | 5.552 |
| Aug-24 recent extension | R01 | 167.488 | 50.785 | 3.298 |
| Aug-24 recent extension | R02 | 236.551 | 48.082 | 4.920 |
| Aug-24 recent extension | R03 | 241.540 | 43.464 | 5.557 |

Results by stratum:

- August-22 five-dwell geometric mean: 6.8567, V2 wins 0/5.
- August-24 four estimable fixed-design dwells: 3.6579, V2 wins 0/4. D4 was honestly non-estimable because no post-bootstrap frame had a causal line prediction.
- Recent three-dwell extension: 4.4842, V2 wins 0/3.
- Breadth total: 12 estimable untouched dwells, V2 wins 0/12. The recent-extension artifact records an older descriptive cross-stratum geometric mean of 4.9916 under its mixed historical definitions; it is retained for provenance but is not used as an inferential aggregate here.

The August-24 development D3 is deliberately excluded from the 12 untouched results. Its matched V2/line ratio was 4.812.

## Independent ten-dwell GLRT/local-rate result

The persisted ten-dwell raw-Doppler cohort is a different, complementary test. All 10 dwells completed, contributing 35,550 raw frames, 29,246 qualified frames, 21,079 coherent frames, and 471 ramps. A fixed sealed GLRT branch slope was evaluated on odd-Qin frame CFO after fitting a per-ramp intercept from even Qin. A reset-debiased local slope used the same held-out lane.

| Model | Pooled held-out odd-Qin RMS |
|---|---:|
| Sealed multi-second GLRT slope | 60.202 Hz |
| Reset-debiased local slope | 33.996 Hz |

The local model reduced RMS by 43.529%; 9/10 dwells required a material slope correction. This does not say that GLRT acquisition is poor. It says that one multi-second slope is not the right post-acquisition dynamics model for these local ramps and intercept changes.

## V3 implementation

### Discrete acquisition, then local Gaussian tracking

`align_known_pilot_frames` now searches every integer epoch in one frame and a bounded CFO grid around the GLRT seed. It:

- uses `ceil(sample_rate / 750)` hypotheses, including epoch 3333 at 2.5 MS/s;
- retains eight separated local basins rather than trusting one even-pilot argmax;
- refines epoch circularly and CFO locally;
- uses even Qin for basin selection and disjoint odd Qin for verification;
- maximizes both the expected and opposite-roll control over the same epoch/CFO domain before comparing them;
- combines correlation magnitudes per frame, making selection invariant to common and arbitrary frame-local carrier phase; and
- returns candidate-only alignment evidence, including nominal/raw/circular offsets, CFO correction, search cardinality, support, exact/control scores, and margin.

The full epoch is never inserted into the five-state covariance. After acquisition, the existing timing states represent only receiver-relative fractional delay and timing rate.

### Phase-safe five-state filter

`PilotPntKalmanConfigV3` preserves the five-state transition but changes the observation policy and empirical dynamics:

- minimum frame-frequency sigma: 25 Hz;
- Doppler-rate process sigma: 5000 Hz/s/sqrt(s);
- full-frame CFO grid step: 250 Hz over the caller's bounded residual domain;
- independent phase reacquisition required;
- full-frame initial acquisition required; and
- phase-to-frequency decoupling required.

Frequency and timing updates use their own rows. An accepted modulo-pi phase innovation updates only the phase marginal. The phase mean still integrates predicted frequency and rate, but phase observations cannot change CFO or rate. This is intentionally a nuisance-state covariance, not a calibrated joint carrier-phase posterior.

`PilotPntKalmanV3Result` is additive and carries the initial alignment evidence without changing the exported V1/V2 result dataclass shape. Existing V1/V2 entry points and persisted contracts remain unchanged.

### Discontinuities

`analyze_piecewise_pilot_pnt_kalman_v3` accepts ordered, non-overlapping, caller-qualified continuity arcs. Each arc independently reacquires epoch/CFO and resets phase, timing, CFO intercept, rate, and covariance. The function deliberately does not infer a boundary from the observations it later scores. Automatic refill/change-point qualification remains a separate upstream responsibility.

## Synthetic and fail-closed verification

Focused tests cover the signal-specific failure modes:

- recovery from a nominal epoch nearly one full frame away (about 1.32 ms);
- the non-integral frame-period boundary at epoch 3333, with 30 supported frames and at least 28 timing updates;
- exact 3333/3334-sample lattice progression;
- arbitrary frame-local phase and modulo-pi sign changes without rate steering;
- deterministic 750 Hz and 1500 Hz CFO-seed nulls inside the advertised plus/minus 2 kHz domain;
- a stronger even-only false epoch rejected by held-out odd pilots;
- symmetric rejection of a symbol-rolled timing alias in both exact and rolled-control replay directions;
- complex-Gaussian noise failing closed end to end;
- strict V3 policy-type and policy-value checks; and
- a confirmed +1000-sample epoch and +600 Hz CFO discontinuity split into two 20-frame locklets, with exactly one outer reacquisition and no rate smoothing across the jump.

The focused implementation/tool suite passes 37/37 tests. The complete DSP suite passes 72 tests; its remaining two real-corpus cases cannot read `/srv/bulk/leo/test-corpus/retro-positive-68p7` in this environment and fail with `PermissionError`, rather than an assertion or numerical mismatch.

## Real-data V3 result

### August-22 five-dwell replay

Each V3 row is compared with a freshly computed causal line on that V3 row's common supported-frame mask. V2 and V3 recovered different frame sets, so their raw RMS values are not divided directly.

| Dwell | V3 RMS (Hz) | Matched line RMS (Hz) | Ratio | Common frames |
|---|---:|---:|---:|---:|
| D1 | 30.750 | 30.868 | 0.996 | 229 |
| D2 | 15.832 | 16.622 | 0.952 | 336 |
| D3 | 43.966 | 46.614 | 0.943 | 386 |
| D4 | 11.400 | 11.764 | 0.969 | 328 |
| D5 | 14.150 | 15.336 | 0.923 | 199 |

Equal-dwell geometric mean: 0.9564; V3 wins 5/5. Rolled-control phase locks were zero in every dwell. One D5 rolled-control window produced 77 supported frames but did not satisfy phase-lock qualification; every other dwell had zero rolled support. Exact phase lock remained sparse (four qualified windows total), reinforcing the decision not to use phase to steer Doppler.

### August-24 five-dwell raw replay

| Dwell | V3 RMS (Hz) | Matched line RMS (Hz) | Ratio | Common frames |
|---|---:|---:|---:|---:|
| D1 | 50.918 | 52.065 | 0.978 | 3487 |
| D2 | 45.983 | 47.391 | 0.970 | 10189 |
| D4 | -- | -- | -- | 0 |
| D5 | 58.230 | 59.351 | 0.981 | 3568 |
| D6 | 46.237 | 47.912 | 0.965 | 6683 |

Equal-dwell geometric mean over the four estimable dwells: 0.9736; V3 wins 4/4. D4 produced no V3-supported frames after the symmetric full-epoch expected/control adjudication and is retained as non-estimable.

V3's CFO result is materially different from V2's multi-fold losses, but the V2 and V3 masks differ, so this report does not divide their RMS values directly. Each tracker is judged only against the causal line recomputed on its own common frame mask.

Phase qualification is not calibrated: 52 of 3000 exact windows qualified, but so did 3 of 3000 rolled-control windows, all on D2. The rolled false locks are only 0.1%, yet they are enough to reject any absolute carrier-phase or navigation-lock claim. This does not contaminate the CFO/rate result because V3 structurally prevents phase observations from steering those states.

## Scientific interpretation and limits

V3 repairs the identified topology mismatch and is a credible research candidate. It is not yet a carrier-phase navigation solution and should not be presented as one.

- Absolute carrier phase is unresolved. The reported phase is modulo pi and receiver/channel-relative.
- Timing is a receiver-relative edge-subcarrier fractional delay, not code phase, transmit time, pseudorange, or a calibrated clock observable.
- The full-frame alignment result is candidate evidence, not a calibrated multiple-hypothesis detector. End-to-end gates fail closed in the tested nulls, but false-alarm calibration over a broader null corpus remains future work.
- V3 phase covariance is a block-diagonal heuristic. CFO/rate mean and covariance are protected from phase, but phase sigma is not a calibrated joint posterior uncertainty.
- Piecewise boundaries must be qualified upstream. V3 does not yet discover refills/change points automatically.
- The 25 Hz frequency floor and 5000 Hz/s/sqrt(s) process setting are corpus-motivated. Coverage/NIS calibration and a preregistered same-release holdout are still required.
- The frame-CFO discriminator is the scoring reference, not ground truth. Satellite/TLE truth and receiver-clock separation are outside this benchmark.
- Dwell D4 in the August-24 V2 set was non-estimable on the declared common mask; it is reported, not silently dropped.

Production promotion should require a frozen V3 configuration, at least 10 untouched same-release estimable dwells, zero or explicitly bounded rolled-control locks, innovation coverage/NIS checks, and stratification by confirmed refill crossing. Until then, keep the causal trailing-20-ms line as the promotion baseline and V3 as an additive research API.

## Evidence and reproduction

Primary persisted evidence:

- `reports/figures/2026_08_24_ten_dwell_raw_doppler/ten-dwell-summary.json`, SHA-256 `fb62bb84d149e75b2c688130891540a788aafa6382e54fc3666e9d7abe110cbc`.
- `reports/figures/2026_08_25_pnt_kalman_v3_review/aug22-v2-same-mask.json`, SHA-256 `9df0e25e45daac803650cdb38996600963057f31b5f2ac289969c579d9e67d65`.
- `reports/figures/2026_08_25_pnt_kalman_v3_review/aug22-v3-same-mask.json`, SHA-256 `48eadbe0430f28cc3649176e139f12f7afce3918ac8e4e47fc99af5e9ba2b3a4`.
- `reports/figures/2026_08_25_pnt_kalman_v3_review/aug24-v2-same-mask.json`, SHA-256 `30d73c14265a92245041c083400223da0dd08bd9e3a7b873a196b4cdb3529d43`.
- `reports/figures/2026_08_25_pnt_kalman_v3_review/aug24-v3-same-mask.json`, SHA-256 `a779796a0394caa8a2669052ce78984d8a4cc22e534776be0526e5cda45df8cf`.
- `reports/figures/2026_08_25_pnt_kalman_v3_review/recent12-v2-cohort-summary.json`, SHA-256 `67460bef27487b294bb5ca0928e90c82361b02e3205e463ad4bc79b4b873ed24`.

Focused verification command:

```bash
.venv/bin/pytest -q \
  tests/dsp/test_starlink_acquisition.py \
  tests/dsp/test_pilot_pnt_kalman.py \
  tests/analysis/test_replay_aug22_pnt_kalman_same_mask_tool.py \
  tests/analysis/test_summarize_pnt_kalman_npz_same_mask_tool.py
```

August-22 replay:

```bash
.venv/bin/python tools/replay_aug22_pnt_kalman_same_mask.py \
  --tracker v3 \
  --output reports/figures/2026_08_25_pnt_kalman_v3_review/aug22-v3-same-mask.json
```

August-24 NPZ same-mask summary:

```bash
.venv/bin/python tools/summarize_pnt_kalman_npz_same_mask.py \
  --source-root /tmp/leo-five-dwell-filter-v3-final \
  --tracker v3 \
  --output reports/figures/2026_08_25_pnt_kalman_v3_review/aug24-v3-same-mask.json
```

The final August-24 replay used an isolated source snapshot. Kalman source SHA-256: `a6135b011dac049dddaeeb742cf6f00a262c819a6a0b70ecff84861e5164e57b`; acquisition source SHA-256: `98bc6ea389d34102395d035a93eda6eb40a5b2cec7d2ff5d139ac9b3bc6595b7`; deterministic snapshot-tree digest: `adbf7d7281b4e3cb1a21eaa3a0be82e6e81af4f6b05fb21c9f6a55ab1e77323d`.

The final read-only audit then added support masking for two-frame seam cases, input-bound/status validation, and self-describing control-winner metadata. These paths do not change the 100-ms replay geometry, where every searched epoch has far more than the two-frame minimum. Current final-source SHA-256 values are `e3489a7cc1426b09223abdf536f556b505ec7647a65650ebe1670950aa36b054` for the Kalman module and `b4891b7ceb7f60a8d23c7e8127b836159a48aa5a2e2f0245e25ac26bd96d3742` for acquisition. A whole-working-tree digest is deliberately omitted because the shared dirty tree contains unrelated concurrent work and generated cache/native files; the named module hashes and isolated replay-snapshot digest are the reproducible bindings.

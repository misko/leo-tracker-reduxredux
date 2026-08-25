# Experimental seeded PNT Kalman V4: `cap-20260825T150802-473cb5bbcbd6`

Date: 2026-08-25

## Decision and status

The V3 acquisition correction has been implemented as an additive,
research-only V4.  It is an explicit opt-in API and is not connected to the
Standard analysis pipeline.  Published V1--V3 contracts, V3 artifacts, Standard
analyzers, phase thresholds, and golden fixtures remain unchanged.

The implementation, full 537-window capture canary, deterministic-resume audit,
and isolated V3/V4 performance comparison are complete.  Every predeclared
Experimental gate passed.  This establishes an **Experimental V4 candidate**;
it does not calibrate a detector or promote V4 into the Standard pipeline.

## What was implemented

V4 changes discrete acquisition and then delegates each accepted mode to one
fresh instance of the unchanged phase-safe V3 tracking core:

1. The caller supplies a provenance-bound epoch, absolute CFO, Doppler rate,
   and branch identity.  The primary seed is always evaluated, so sparse local
   peak retention cannot erase it.
2. Acquisition evaluates four approximately 20 ms blocks across each 75 ms
   window.  Block coordinates follow the exact 750 Hz frame lattice, including
   the 3333/3334-sample progression at 2.5 MS/s.
3. Even Qin symbols propose geometry; odd Qin symbols validate it.  Exact,
   rolled, deranged, and opposite-edge evidence is measured on the same
   absolute samples and at the candidate's same epoch/CFO coordinates.
4. A bounded block-trajectory search admits slow timing motion while enforcing
   epoch span, adjacent-step, fit-RMS, and CFO-span limits.  Every block-admitted
   proposal is re-scored over the whole window before component selection.
5. A bounded full-frame fallback is attempted only when the protected local
   seed is unsupported.  Its coarse proposal grid uses 12 predeclared even-Qin
   anchors in the first 20 ms block, then applies the unchanged four-block
   exact/held-out/whole-window adjudication.  Refinement stays local to each
   retained peak instead of forming irrelevant cross-peak Cartesian pairs.
   Proposal bounds, truncation, coordinates, and work counts remain explicit.
6. CFO copies are collapsed only when their complete timing paths match and
   their CFO trajectories differ by one constant 227,272.727273 Hz alias lift
   with compatible Doppler rates.  Non-alias modes, including the observed
   approximately 85 kHz family separation, remain distinct.
7. Presence, code specificity, alias resolution, uniqueness, numerical
   tracking, and modulo-pi phase qualification are separate dispositions.
   Strong exact evidence with ambiguous control evidence is reported as an
   uncalibrated candidate/ambiguity, not as signal absence.
8. Each accepted mode gets an independent V3-core track.  Only that mode's
   acquired Doppler rate is substituted as the initial state; the V3 policy and
   thresholds are unchanged.  Caller-qualified piecewise arcs reacquire from a
   fresh state and V4 does not discover resets automatically.

The additive implementation is in
`src/leo/analysis/starlink/seeded_acquisition.py` and
`src/leo/analysis/qam/pilot_pnt_kalman_v4.py`.  Public exports are deliberately
explicit and opt-in.

## Root causes addressed

The implementation directly addresses the acquisition defects established by
the frozen V3 investigation:

- V3 could discard the supplied trajectory basin while retaining only eight
  sparse-anchor peaks; V4 protects and evaluates the seed.
- V3 independently searched its 17-symbol rolled control.  At 2.5 MS/s the
  compensating displacement is 187 samples, so the control could reacquire the
  same Qin pilot and veto it.  V4 conditions controls on the exact candidate's
  coordinates and absolute verification samples.
- V3 mapped a global negative exact-minus-control margin to `NO_RESULT`; V4
  keeps pilot presence and code-phase specificity as distinct claims.
- A single static epoch across the four blocks rejected real slow timing
  motion.  V4 selects a bounded lattice-aware timing path and rejects abrupt
  paths rather than forcing all blocks onto one integer epoch.
- Representative selection before whole-window validation could preserve the
  wrong local component.  V4 jointly re-scores every admitted proposal before
  redundancy and alias collapse.

These changes correct acquisition semantics.  They do not establish satellite
identity, absolute phase, transmit time, pseudorange, a calibrated detector, or
physical frame resets.

## Focused verification

The combined frozen-V3 and V4 acquisition, tracker, canary-tool, and benchmark
tool suite passed **152 tests** in the final clean-worktree run.  The
suite covers protected-seed and global-fallback accounting, exact 3333/3334
lattice behavior, same-coordinate
held-out controls, whole-window ordering, bounded trajectory paths, alias/rate
equivalence, true multi-mode preservation, adversarial/null inputs, deterministic
serialization/resume, per-mode direct-core parity, piecewise fresh-state
behavior, and benchmark fail-closed semantics.  Ruff formatting/checks and
mypy with untyped-import following also passed for the V4 source and replay
tools.

The frozen V3 sources and their regression tests retain these SHA-256 values:

| Frozen path | SHA-256 |
|---|---|
| `src/leo/analysis/qam/pilot_pnt_kalman.py` | `e3489a7cc1426b09223abdf536f556b505ec7647a65650ebe1670950aa36b054` |
| `src/leo/analysis/starlink/acquisition.py` | `b4891b7ceb7f60a8d23c7e8127b836159a48aa5a2e2f0245e25ac26bd96d3742` |
| `tests/dsp/test_pilot_pnt_kalman.py` | `172a5d1ce9a7bd862f6e05f37638515edfb726a2ad74e6d43337305b31fd256a` |
| `tests/dsp/test_starlink_acquisition.py` | `54a9d20decd6d12c79bc250bb4d2fbcaa1a29135172b8f39d76dbccdfb3f547c` |

### Real-IQ trajectory regressions

Two V2-complete/V3-`NO_RESULT` rows that exposed the static-coordinate defect
were replayed through the final V4 path logic:

| Frozen row | Path/time | Seed epoch | Selected four-block path | Reference epoch | Epoch span / max step / fit RMS | CFO span | V4 outcome |
|---:|---|---:|---|---:|---|---:|---|
| 80 | `stream-0/rx1`, 36.725 s | 2996 | 2996 -> 2997 -> 2997 -> 2998 | 2997 | 2 / 1 / 0.223610 samples | 50 Hz | complete; 1 track; 0 phase locks |
| 87 | `stream-0/rx1`, 39.050 s | 573 | 573 -> 574 -> 574 -> 575 | 574 | 2 / 1 / 0.223610 samples | 50 Hz | complete; 1 track; 0 phase locks |

These are focused regressions only.  They demonstrate why a bounded path is
needed, but they do not predict the full-capture pass rate.

## Full 537-window canary

The replay is bound to frozen input
`sha256:6b740a994181f13e9c6e21538026ee7531d68edbb9c40c54bab26ee11fe1b9a4`
and recording manifest
`sha256:ab55917851a9cd37af94b6145cc719f7b8d9d0809f2202a2dcd1ac38c3e7a31e`.
It verifies the read-only IQ chunks before analysis and records every proposal,
trajectory, component decision, fallback, truncation, and track.

<!-- V4_CANARY_RESULTS_BEGIN
STATUS: COMPLETE
RUN_UTC: 2026-08-25T21:29:01Z
CANARY_RESULTS_SHA256: 3455129164ec4b56275a00b938c9da2cd4dd2e123b3406b7f1aac79b02201cab
CANARY_INDEX_SHA256: 62a9a310b2a89434b0551aaeb86e7bff35ba211721c06f6ef9489a5d031d0590
STANDARD_QUALIFIED_TRACKS_PRESERVED: 53/53
V2_PHASE_QUALIFIED_TRACKS_PRESERVED: 55/55
ROBUST_V3_LOSSES_SELECTED: 50/50
ROBUST_V3_LOSSES_TRACKED: 50/50
ONE_UPDATE_ALIAS_INDEPENDENT_TRACKS: 0/7
MATCHED_ALIAS_NULL_PEERS_SELECTED: 0/57
MATCHED_ALIAS_NULL_PEERS_TRACKED: 0/57
NEW_PHASE_QUALIFIED_ROW_COUNT: 1 (review-only; no automatic promotion)
NEW_PHASE_QUALIFIED_ROWS: sha256:f684afe7108a70a5a74c8a5201b84b88c5074d28a189f0b3e66cea1f7bb3a7ed
POPULATION_ROWS_ACCOUNTED: 537/537
ALL_ROWS_AND_PROPOSALS_ACCOUNTED: true
PHASE_THRESHOLDS_UNCHANGED: true
RESEARCH_CLAIM_BOUNDARIES_PRESERVED: true
OVERALL_CANARY_GATE: pass
CANARY_RESULTS_LINK: figures/2026_08_25_150802_pnt_kalman_v4_experimental/canary-results.json
CANARY_INDEX_LINK: figures/2026_08_25_150802_pnt_kalman_v4_experimental/canary-index.json
V4_CANARY_RESULTS_END -->

The canary passed all ten checks.  A resume reused all 537 row checkpoints and
reproduced both top-level files byte-for-byte.  An independent audit parsed all
539 JSON documents, recomputed every row and evidence digest, verified all 14
manifest-bound IQ chunks, and reproduced every cohort and accounting identity.
The final scientific outcomes and tracks are exactly equal to the earlier full
canary; the bounded performance optimization changed proposal-work counts only.

Across all 537 rows, the numerical-status contingency was 261 V3/V4 complete,
50 V3 `NO_RESULT` to V4 complete, 5 V3 complete to V4 `NO_RESULT`, and 221
neither complete.  The five V4 regressions are non-phase-qualified fallback
rows reported as `no_research_candidate`; none belongs to a protected canary
cohort.  They remain explicit review cases and are another reason V4 is not a
drop-in Standard replacement.

Machine-readable evidence: [canary results](figures/2026_08_25_150802_pnt_kalman_v4_experimental/canary-results.json)
and [checkpoint index](figures/2026_08_25_150802_pnt_kalman_v4_experimental/canary-index.json).

## Isolated performance and parity gate

The benchmark runs V3 and V4 in fresh isolated processes and keeps a combined
process timing only as a diagnostic.  Required limits are V4/V3 seeded-path p95
at most 1.00, full-537 wall time at most 1.25, peak RSS at most 1.25, and declared
NumPy/native numerical parity.

<!-- V4_PERFORMANCE_RESULTS_BEGIN
STATUS: COMPLETE
RUN_UTC: 2026-08-25T21:41:04Z
SCIENTIFIC_RECEIPT_SHA256: 6a24d63afa47da7a897bce3d7248a7d7bd6f3976a48bbdaa72a147fe0cce0a2e
SCIENTIFIC_RECEIPT_INTERNAL_DIGEST: sha256:ecc873e30fe763aaf04a608f5f2f7b12e6a459677fe161895a377a8b29d37c9f
PERFORMANCE_RECEIPT_SHA256: 88aacfc6bf67da50e33601d77c22f8b31a21d01d3559cbe07244540d5c4d2175
ISOLATED_V3_RECEIPT_SHA256: 85b1a1d8a7758ec6e8e6126e1d42a65e644475bbab7a4b764bfaec16d0425f18
ISOLATED_V4_RECEIPT_SHA256: f5675405e2f765044b9413e21f446ac65e20c756af0013c82ef7f39a1a3c4ddb
SEEDED_PATH_ROW_COUNT: 311
SEEDED_PATH_P95_V3_S: 0.4205717735
SEEDED_PATH_P95_V4_S: 0.2539927155
SEEDED_PATH_P95_V4_OVER_V3: 0.6039224016064406 (required <= 1.00)
FULL_537_WALL_V3_S: 208.582676574
FULL_537_WALL_V4_S: 146.733289532
FULL_537_WALL_V4_OVER_V3: 0.7034778340278064 (required <= 1.25)
PEAK_RSS_V3_BYTES: 601354240
PEAK_RSS_V4_BYTES: 601190400
PEAK_RSS_V4_OVER_V3: 0.9997275482750401 (required <= 1.25)
NUMPY_NATIVE_PARITY: pass (3/3 rows; 0 argmax mismatches; maximum absolute score delta 1.8485213360008856e-14)
OVERALL_PERFORMANCE_GATE: pass
SCIENTIFIC_RECEIPT_LINK: figures/2026_08_25_150802_pnt_kalman_v4_experimental/scientific-receipt.json
PERFORMANCE_RECEIPT_LINK: figures/2026_08_25_150802_pnt_kalman_v4_experimental/performance-receipt.json
ISOLATED_V3_RECEIPT_LINK: figures/2026_08_25_150802_pnt_kalman_v4_experimental/isolated-v3-worker-receipt.json
ISOLATED_V4_RECEIPT_LINK: figures/2026_08_25_150802_pnt_kalman_v4_experimental/isolated-v4-worker-receipt.json
V4_PERFORMANCE_RESULTS_END -->

All four exit checks passed on the complete population.  The isolated workers
used identical bound rows and fresh interpreters; analyzer timing excludes
receipt construction.  V4's seeded-path p95 was 39.6% lower than V3, full-wall
time was 29.7% lower, and peak RSS was effectively equal.  Native AVX2/FMA and
NumPy proposal grids agreed on all three declared parity rows at `1e-12`
absolute and relative tolerances.

Machine-readable evidence: [scientific receipt](figures/2026_08_25_150802_pnt_kalman_v4_experimental/scientific-receipt.json),
[performance receipt](figures/2026_08_25_150802_pnt_kalman_v4_experimental/performance-receipt.json),
[isolated V3 receipt](figures/2026_08_25_150802_pnt_kalman_v4_experimental/isolated-v3-worker-receipt.json),
and [isolated V4 receipt](figures/2026_08_25_150802_pnt_kalman_v4_experimental/isolated-v4-worker-receipt.json).

## Scientific limits and promotion gates

Although both Experimental gates pass, V4 remains candidate-only.  The current
thresholds are descriptive and were developed against this capture; the canary
is not an untouched calibration set.  Phase remains modulo pi and
receiver/channel-relative, timing remains receiver-relative edge-subcarrier
delay, and the frame-CFO discriminator is a scoring reference rather than
ground truth.  Multiple acquisition modes are not satellite identifications.

Promotion remains staged:

- **Experimental V4** requires the complete 537-window canary and isolated
  performance/parity gates above to pass without changing thresholds.
- **Research candidate** additionally requires a frozen configuration,
  calibrated synthetic/adversarial controls, and at least ten untouched,
  same-release, estimable dwells compared with V3 and the causal trailing-20-ms
  line on identical masks.
- **Standard proposal** additionally requires an authoritative labeled real-IQ
  absence corpus, preregistered evaluation, innovation/NIS checks, scientific
  review, and a new versioned Standard contract/release.  For an event-rate
  target no larger than 0.001, zero events require at least 2,995 genuinely
  independent null units for a one-sided 95% bound.

Prior V3 evidence will not be rewritten, phase thresholds will not be relaxed,
and newly passing phase cases will be reviewed individually rather than
automatically promoted.

## Supporting reports

- [Additive V4 correction plan](2026_08_25_pnt_kalman_v4_correction_plan.md)
- [V3 acquisition-model audit](2026_08_25_150802_v3_acquisition_model_audit.md)
- [V3 missing-signal investigation](2026_08_25_150802_v3_missing_signal_investigation.md)
- [Full-dwell V3 replay](2026_08_25_150802_v3_full_dwell.md)
- [V3 comprehensive review](2026_08_25_pnt_kalman_v3_comprehensive_review.md)

# DSX01 scan 1: tracks 4–6

This continues the [ordered review](../scan1_track_review/README.md), after
[T004 and T011](../first_track_join_checks_v2/README.md). GPS remains fixed at
the supplied evaluation position. Original Graph membership, observation times,
receiver/band calibration and candidate identities are preserved in the main
review. The tests below are conditional diagnostics, not new location estimates.

## Individual tracks

| Order | RX1/CH1 track | Time, seconds | Points | Candidate | Polynomial RMS, Hz | Doppler RMS, Hz | Residual slope, Hz/s | Result |
|---|---|---|---:|---:|---:|---:|---:|---|
| 4 | T005 | 52.53–73.10 | 30 | 69433 | 125.7 | 123.4 | -1.74 | Pass; measured curvature qualifies |
| 5 | T000 | 74.52–92.98 | 25 | 60372 | 84.9 | 114.2 | +10.33 | Pass current screen; trend merits scrutiny |
| 6 | T012 | 90.85–102.91 | 16 | 64936 | 98.7 | 149.8 | -30.87 | Reject: constant exceeds 3,000 Hz |

![T005 GLRT and residuals](../scan1_track_review/S01-RX1-CH1-T005.png)
![T000 GLRT and residuals](../scan1_track_review/S01-RX1-CH1-T000.png)
![T012 GLRT and residuals](../scan1_track_review/S01-RX1-CH1-T012.png)

T000's cubic polynomial label does not qualify it to calibrate: its observed
span is below the frozen 20-second minimum. T012 is also unqualified despite
its quadratic label. Their residual trends are not removed. Passing the current
screen is not evidence of perfectly white residuals; T000 remains provisional.

## Can curved peers explain the phase without these targets voting?

For each supported candidate, we profile one phase on the same bounded causal
prior grid in both c arms. Only prequalified curved peers vote. The review target
is excluded. Hardware is frozen; each peer retains its Gaussian component
constant. Effective fragment weights are capped at 50 and the phase prior is
charged once. This diagnostic omits the full engine's conditional phase-volume
penalty and does not reassign other satellites. Anchor labels are held fixed
to the fitted-c proposals in both arms, so it is a conditional comparison.

| Target | Curved phase anchors | Original phase fitted-c, s | Anchor-only phase, s | Target RMS after transfer, Hz |
|---|---|---:|---:|---:|
| T005 / 69433 | RX1/CH2/T002 | -2.496 | -2.406 | 127.1 |
| T000 / 60372 | RX2/CH5/T002; RX2/CH6/T002 | +0.487 | +0.485 | 114.2 |
| T012 / 64936 | None | 0 | No usable estimate | Not admitted |

T005 remains compatible when its phase is selected from the longer overlapping
CH2 track alone. T000 inherits a phase supported by two later curved RX2 tracks,
but still has a +10.3 Hz/s residual slope. The c=0 transfer gives the same
qualitative conclusions. This is not fully independent validation: hardware was
originally learned using reviewed curved tracks. It also does not authenticate
the anchor satellite labels.

## Shared-constant cross-channel checks

All 1,707 candidates are considered with existing hardware and phases. A join
must share one component constant, retain original aliases and all observations,
pass every member's noise tests and pass the pooled time-ordered noise tests.

| Pair | Points | Joint RMS c=0 / fitted-c, Hz | c=0 result | Fitted-c result |
|---|---:|---:|---|---|
| T005 + RX1/CH2/T002 | 68 | 134.0 / 126.7 | Pooled quadratic BIC gain 10.58 exceeds limit 10 | Sole passing candidate 69433; favors one constant |
| T000 + RX1/CH3/T008 | 37 | 141.6 / 110.7 | CH3 residual mean fails | Sole passing candidate 60372; favors one constant |

These are checks of the frozen fits, not newly added associations. They show
that a small change in total association coverage can coexist with a change in
cross-channel consistency. The first c=0 failure is close to the gate boundary.
The T000 fitted-c pooled slope test is also close to its limit (z=2.91 versus 3),
so its passing result should not be treated as strong evidence of white noise.
No position accuracy improvement follows from these in-sample frequency results.

## T012: could an unmodeled orbital phase explain the offset?

T012 needs a +3,892 Hz constant under phase zero, exceeding the unchanged
3,000 Hz bound. Seven fragments across RX1 channels 1, 2, 3, 4, 7 and 8 nominate
64936, totalling 118 points from 74.57 to 119.01 seconds. None qualifies as an
individual measured-curvature anchor. They cannot select a usable calibration.

We tested all 81 qualified curved fragments elsewhere in S01 over 81 phase
samples spanning the causal prior bound of ±5.163 seconds. None passes the
current frequency, constant and noise gates for 64936 in either c arm. This is
a bounded grid diagnostic, not a proof over continuous phase or different
hardware models. There is currently no qualified curved support for this phase.

As an explicitly unsupported counterfactual, we allowed the seven short
fragments to select one phase and one constant together. In fitted-c they prefer
-0.774 seconds with constant +1,937 Hz and pooled RMS 167.7 Hz. The pooled noise
screen passes, but multiple individual means and structure checks fail:

![Counterfactual residuals](unsupported_family_residuals.png)

The channel means cancel in the pooled result. For example, T012 has -167 Hz
mean residual while CH3/T009 has +149 Hz. We therefore do not admit the family,
relax the offset limit or promote the counterfactual phase. The c=0
counterfactual also fails, including the pooled screen. No arbitrary track
slopes or new hardware drifts are introduced.

## Are GLRT frequency estimates causing the residual structure?

We replay the previously completed known-pilot measurements on the exact
original observation IDs. Qualification used no satellite identity or position.
Unsupported or ambiguous points retain their original GLRT CFO. Hardware,
satellite phase, labels, points, times and measurement weights are fixed; only
qualified CFO values and the penalized fragment constant change.

| Track | Qualified updates | RMS original → qualified, Hz | Slope original → qualified, Hz/s | Qualified constant, Hz |
|---|---:|---:|---:|---:|
| T005 | 29/30 | 123.4 → 127.1 | -1.74 → -1.71 | +468 |
| T000 | 25/25 | 114.2 → 131.0 | +10.33 → +7.22 | -1,058 |
| T012 | 16/16 | 149.8 → 154.0 | -30.87 → -30.32 | +3,903 |

![Matched measurement comparison](measurement_residuals.png)

The trends remain under a different qualified frequency estimator. This test
does not establish which physical effect causes them, nor which estimator is
more accurate. It does show that this particular measurement refinement does
not remove the T000 trend or T012 offset failure. The c=0 arm yields the same
qualitative outcome. No newly accepted points or better position are claimed.

## Validation and files

Twenty-eight focused tests passed: curved-only phase selection, a single phase
prior, vote caps, empty-anchor rejection, preservation of observed residual
slopes and aliases, component-constant profiling, pooled merge checks,
measurement replay and residual-screen parity. Original single-track RMS values
reproduce the frozen fits within 0.00001 Hz in both c arms. Every reviewed point
is retained. Phase grids, point memberships, nomination labels, priors and
budgets are matched across c arms.

`summary.json` holds phase/merge checks; `measurement_summary.json` holds the
controlled CFO comparison. Full per-arm grids and residuals are in `c0/` and
`fitted_c/`. `protocol.json` and `measurement_protocol.json` record provenance
and limitations. The next RX1/CH1 fragment is T013 (120.30–138.40 seconds), whose
current candidate fails slope and curvature checks.

# DS1 iteration 25: fixed-coordinate source-admission evaluation

## Decision

**The predeclared gate fails. Do not design or run a prospective geographic
basin.** The source-admitted model improves the zero-rate control in all 12
HELD sessions, but it is worse than both iteration 23 all-source rate controls
in each group and in the pooled equal-session result. Pooled HELD capped loss
is `0.086163`, versus `0.149297` at zero rate, `0.070167` for the all-source
`+/-0.25 s/hour` arm, and `0.066283` for the all-source `+/-1 s/hour` arm.

This was a separately sealed fixed-coordinate evaluation. The 65 admitted
group sources, their iteration 23 full-TRAIN `+/-1 s/hour` rates, the 186 exact
zeros, coordinates, taus, comparators, and gate were fixed before the run.
Each group's candidate HELD rows were scored once after fitting one CFO per
track from TRAIN rows. HELD did not change membership, rates, coordinates,
tau, preprocessing, diagnostics, gate, or any model choice. No truth or
reference position was used, and no geographic search was run.

## Frozen model and support

| Group | Latitude | Longitude | Tau (s) | Enabled / zero sources | Enabled tracks | Enabled TRAIN obs. | Enabled HELD obs. | Enabled occupied-second weight |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `20260921_00` | 37.903710 | -122.412040 | -0.3 | 40 / 76 | 319 | 3,526 | 2,551 | 5,516 |
| `20260921_16` | 37.845404 | -122.461842 | -1.1 | 25 / 110 | 103 | 2,544 | 1,768 | 2,344 |
| **Total** | — | — | — | **65 / 186** | **422** | **6,070** | **4,319** | **7,860** |

An admitted source is exactly an iteration 24 support-eligible source that
passed every cross-fit gate. Its rate is exactly its iteration 23 full-TRAIN
diagnostic winner at `+/-1 s/hour`. Every other source is exactly zero. This
differs deliberately from iteration 24's broader prospective mapping, which
retained rates for all 80 eligible sources: iteration 25 admits only the 65
cross-fit passers requested by this evaluation.

## Equal-session capped losses

The loss is occupied-second weighted within each session, caps each track at
one using `800 Hz`, and gives every session equal weight. TRAIN is diagnostic
only and did not control the evaluation decision.

| Group | Arm | TRAIN loss | HELD loss | Candidate minus arm, HELD |
|---|---|---:|---:|---:|
| `20260921_00` | source-admitted candidate | 0.048602 | 0.064186 | — |
|  | zero rate | 0.130075 | 0.154682 | -0.090496 |
|  | all-source `+/-0.25` | 0.044743 | 0.059842 | +0.004344 |
|  | all-source `+/-1` | 0.038970 | 0.053686 | +0.010500 |
| `20260921_16` | source-admitted candidate | 0.099120 | 0.108140 | — |
|  | zero rate | 0.136759 | 0.143913 | -0.035773 |
|  | all-source `+/-0.25` | 0.076588 | 0.080491 | +0.027649 |
|  | all-source `+/-1` | 0.072499 | 0.078879 | +0.029261 |
| **Pooled 12 sessions** | **source-admitted candidate** | **0.073861** | **0.086163** | **—** |
|  | zero rate | 0.133417 | 0.149297 | **-0.063134** |
|  | all-source `+/-0.25` | 0.060665 | 0.070167 | **+0.015996** |
|  | all-source `+/-1` | 0.055735 | 0.066283 | **+0.019880** |

The all-source `+/-1` arm remains the best of these fixed-coordinate arms on
pooled HELD loss. Source admission recovers much of its improvement over zero,
but removing the 15 eligible cross-fit failures and the 171 sparse ineligible
sources also removes predictive benefit that the iteration 24 TRAIN-only rule
did not capture.

## Per-session HELD changes

Negative changes favor the admitted candidate. It improves zero rate in every
session, so the session-breadth and `0.05` regression guards pass. It beats the
all-source arms only in the first `20260921_00` session; all other changes
against those controls are positive.

| Group | Session | Candidate loss | Minus zero | Minus all `+/-0.25` | Minus all `+/-1` |
|---|---|---:|---:|---:|---:|
| `20260921_00` | `24ad6788936de72f` | 0.051705 | -0.102164 | -0.036244 | +0.000692 |
|  | `30ff691861c6bb53` | 0.116942 | -0.051350 | +0.026684 | +0.026684 |
|  | `75ec9d92534c0293` | 0.029602 | -0.043585 | +0.000722 | +0.000722 |
|  | `79cca97e97a1541c` | 0.092854 | -0.214268 | +0.020730 | +0.020730 |
|  | `85afa91453f8847b` | 0.065279 | -0.110118 | +0.012331 | +0.012331 |
|  | `f749f13b64256b8d` | 0.028733 | -0.021491 | +0.001838 | +0.001838 |
| `20260921_16` | `0dcc48743f9f5487` | 0.081534 | -0.045398 | +0.008921 | +0.008921 |
|  | `2ea5bcf9b18778cc` | 0.165095 | -0.011600 | +0.041883 | +0.044161 |
|  | `5f69c606f9bb3a8f` | 0.102239 | -0.026932 | +0.058795 | +0.060325 |
|  | `d026d3a5a705523e` | 0.048526 | -0.052176 | +0.015764 | +0.015764 |
|  | `e1422297a1ff6598` | 0.161186 | -0.044074 | +0.015651 | +0.021514 |
|  | `f354f1c88a654681` | 0.090260 | -0.034458 | +0.024880 | +0.024880 |

## NORAD 68739 contribution and sensitivity

NORAD 68739 is admitted in group `20260921_16` at its frozen iteration 23 rate
of `+0.593621 s/hour`. It contributes five tracks, 134 TRAIN observations, 94
HELD observations, and 120 occupied-second units, all in session
`e1422297a1ff6598`.

The leave-68739-at-zero sensitivity is reconstructed exactly from the
candidate and sealed zero-rate track scores. No second candidate HELD score was
run. With 68739 enabled, group HELD loss is `0.108140`; with only 68739 returned
to zero it is `0.107376`. Thus 68739 worsens the group equal-session HELD loss
by `+0.000764`, despite improving TRAIN loss from `0.100673` to `0.099120`.

Its track behavior is mixed. Three tracks improve their HELD capped
contribution relative to zero rate, while two worsen. The two worsening tracks
have candidate/zero HELD RMS pairs of `1446.6/94.1 Hz` and `1752.6/67.3 Hz`;
their capped penalties outweigh the net gain from the other three tracks.
This is consistent with iteration 24's finding that 68739 has a stable positive
TRAIN basin but does not improve every omitted track.

## Exact replay and gate

| Group | Replayed observations | RMS error (Hz) | P99 absolute (Hz) | Maximum absolute (Hz) | Gate |
|---|---:|---:|---:|---:|---|
| `20260921_00` | 8,285 | 0.0000066 | 0.0000311 | 0.0001346 | pass |
| `20260921_16` | 9,686 | 0.0000344 | 0.0001690 | 0.0006609 | pass |

Both are far inside the predeclared `0.2 Hz` tolerance. The replay fixes Earth
rotation at receive time plus the global tau and applies the per-source rate
only as causal orbit phase.

| Predeclared criterion | Result |
|---|---|
| Exact replay passes in both groups | pass |
| Candidate beats all three controls in each group | **fail** |
| Candidate beats all three controls pooled | **fail** |
| At least four of six sessions improve zero in each group | pass (6/6 and 6/6) |
| No session regresses from zero by more than 0.05 | pass (none regress) |
| **Overall** | **fail** |

## What worked, failed, and was learned

**Worked.** The sealed source policy reproduced the required 65/186 split,
the one-score-per-group evaluation completed in 46.3 seconds, all 12 sessions
improved on zero rate, and direct SGP4 replay passed by more than two orders of
magnitude. The numerical implementation is not the limiting factor.

**Failed.** Source admission did not beat either all-source rate arm in either
group or pooled. The failure is broad across sessions and already visible on
TRAIN, so it is not a single-session HELD accident. NORAD 68739 also contributes
a small adverse HELD change even though its aggregate omitted-TRAIN-track gate
passed in iteration 24.

**Learned.** Iteration 24's strict per-source cross-fit gate identifies rates
that are stable and better than zero under its TRAIN loss, but it is not a
successful admission rule for the fixed-coordinate predictive model. Sparse
and cross-fit-failing sources collectively carry useful held prediction in the
all-source fits. A per-source aggregate TRAIN gate also does not guarantee
benefit after occupied-second capping and equal-session aggregation.

**Precise next step.** Stop this binary source-admission geographic path here.
Do not design or run a geographic basin from this model, and do not tune the
admission rule on these now-consumed HELD rows. Keep the iteration 23
all-source `+/-1 s/hour` arm as the best fixed-coordinate diagnostic result.
Other truthful DS1 objectives remain open. Any renewed source-admission claim
would need a new TRAIN-only rule and a new untouched prospective split; new RF
collection would require separate user authorization.

## Reproduction and sealed artifacts

`plan.json` was sealed before the evaluation. `evaluation.json` and its
adjacent SHA-256 seal contain the complete frozen rates and membership, all
candidate track and session scores, comparator changes, support, 68739
sensitivity, exact replay, bindings, and gate result.

```bash
.venv/bin/pytest -q \
  reports/2026_09_25_ds1_iteration25_source_admission/test_run.py

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python \
  reports/2026_09_25_ds1_iteration25_source_admission/run.py \
  --output reports/2026_09_25_ds1_iteration25_source_admission/evaluation.json
```

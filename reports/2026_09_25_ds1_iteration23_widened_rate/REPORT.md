# DS1 iteration 23: widened TRAIN-only per-NORAD rate audit

## Decision

**No-go for a prospective geographic basin using the predeclared
`+/-0.50 s/hour` rate arm.** Group `20260921_16` retains one active-boundary
fit, NORAD 68739 at exactly `+0.500000 s/hour`, and has two predeclared
best/second ambiguity flags. Group `20260921_00` passes every prospective gate.
The `+/-1.0 s/hour` diagnostic removes all active boundaries in both groups,
with NORAD 68739 settling at `+0.593621 s/hour`, but that arm is 10.9 times the
regularization sigma and was predeclared diagnostic-only. It cannot authorize a
basin after inspection.

This is a TRAIN-side decision. Randomized HELD rows affected no coordinate,
tau, identity, source membership, CFO, rate, optimizer call, bound, stopping
rule, ambiguity rule, or go/no control flow. No reference truth was used and no
geographic search was run.

## Frozen experiment

The audit replays the original sealed `shared_time` points:

| Group | Latitude | Longitude | Tau (s) | TRAIN / HELD | Sources | Tracks |
|---|---:|---:|---:|---:|---:|---:|
| `20260921_00` | 37.903710 | -122.412040 | -0.3 | 4,785 / 3,500 | 116 | 476 |
| `20260921_16` | 37.845404 | -122.461842 | -1.1 | 5,692 / 3,994 | 135 | 298 |

Every source is profiled at all three predeclared symmetric bounds. The scalar
objective uses TRAIN observations and TRAIN-profiled per-track CFOs only. For
each source and bound, the coarse rate spacing is chosen so
`max(abs(TRAIN age_h)) * delta_rate <= 0.05 s`; an interleaved half-step scan
then verifies coverage. Every local minimum on that combined grid is refined,
and endpoints and zero are explicit candidates. The lowest TRAIN objective wins
with deterministic tie breaks. The historical single whole-interval bounded
optimizer is recorded only as a comparator.

## Equal-session capped losses

| Group | Bound (s/h) | TRAIN loss | HELD loss | HELD delta vs zero | HELD delta vs 0.25 |
|---|---:|---:|---:|---:|---:|
| `00` | zero | 0.130075 | 0.154682 | 0 | — |
| `00` | 0.25 | 0.044743 | 0.059842 | -0.094840 | 0 |
| `00` | 0.50 | 0.038970 | 0.053686 | -0.100996 | -0.006156 |
| `00` | 1.00 diagnostic | 0.038970 | 0.053686 | -0.100996 | -0.006156 |
| `16` | zero | 0.136759 | 0.143913 | 0 | — |
| `16` | 0.25 | 0.076588 | 0.080491 | -0.063422 | 0 |
| `16` | 0.50 | 0.077416 | 0.082566 | -0.061346 | +0.002076 |
| `16` | 1.00 diagnostic | 0.072499 | 0.078879 | -0.065034 | -0.001612 |

All 12 sessions improve against zero rate under every fitted bound. Widening
from 0.25 to 0.50 improves group `00`, but slightly worsens group `16` under
the capped-RMS report metric. This does not change the bound or decision: the
fit minimizes the frozen robust TRAIN objective, while capped RMS is a separate
reported score and HELD is evaluation-only.

## Per-session randomized HELD changes

Each parenthesized value is the fitted arm minus that session's zero-rate HELD
loss. Negative is better.

| Group / session | Zero | 0.25 | 0.50 | 1.00 diagnostic |
|---|---:|---:|---:|---:|
| `00` / `24ad6788936de72f` | 0.153870 | 0.087949 (-0.065920) | 0.051013 (-0.102857) | 0.051013 (-0.102857) |
| `00` / `30ff691861c6bb53` | 0.168292 | 0.090258 (-0.078034) | 0.090258 (-0.078034) | 0.090258 (-0.078034) |
| `00` / `75ec9d92534c0293` | 0.073187 | 0.028880 (-0.044307) | 0.028880 (-0.044307) | 0.028880 (-0.044307) |
| `00` / `79cca97e97a1541c` | 0.307122 | 0.072124 (-0.234998) | 0.072124 (-0.234998) | 0.072124 (-0.234998) |
| `00` / `85afa91453f8847b` | 0.175397 | 0.052948 (-0.122449) | 0.052948 (-0.122449) | 0.052948 (-0.122449) |
| `00` / `f749f13b64256b8d` | 0.050224 | 0.026895 (-0.023329) | 0.026895 (-0.023329) | 0.026895 (-0.023329) |
| `16` / `0dcc48743f9f5487` | 0.126932 | 0.072613 (-0.054318) | 0.072613 (-0.054318) | 0.072613 (-0.054318) |
| `16` / `2ea5bcf9b18778cc` | 0.176695 | 0.123211 (-0.053483) | 0.120934 (-0.055761) | 0.120934 (-0.055761) |
| `16` / `5f69c606f9bb3a8f` | 0.129171 | 0.043444 (-0.085727) | 0.041914 (-0.087257) | 0.041914 (-0.087257) |
| `16` / `d026d3a5a705523e` | 0.100702 | 0.032762 (-0.067940) | 0.032762 (-0.067940) | 0.032762 (-0.067940) |
| `16` / `e1422297a1ff6598` | 0.205260 | 0.145535 (-0.059725) | 0.161795 (-0.043464) | 0.139672 (-0.065588) |
| `16` / `f354f1c88a654681` | 0.124717 | 0.065380 (-0.059337) | 0.065380 (-0.059337) | 0.065380 (-0.059337) |

## Optimization and rate distributions

All local refinements converged and every half-step verification passed. A fit
is called active when its distance from the bound is at most
`max(5*xatol, 32*machine_epsilon*max(1,bound))`, which is `1e-6 s/hour` here.

| Group | Bound | Min | q05 | Median | q95 | Max | SD | Active | Ambiguous | Global/legacy discrepancies |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `00` | 0.25 | -0.200560 | -0.081911 | 0.006684 | 0.063634 | 0.250000 | 0.053006 | 1 | 0 | 0 |
| `00` | 0.50 | -0.200560 | -0.081911 | 0.006684 | 0.063634 | 0.397627 | 0.060192 | 0 | 0 | 0 |
| `00` | 1.00 | -0.200561 | -0.081911 | 0.006684 | 0.063634 | 0.397627 | 0.060192 | 0 | 0 | 0 |
| `16` | 0.25 | -0.250000 | -0.071590 | 0.009129 | 0.109254 | 0.250000 | 0.065381 | 4 | 2 | 1 |
| `16` | 0.50 | -0.336961 | -0.071590 | 0.009129 | 0.109254 | 0.500000 | 0.079292 | 1 | 2 | 1 |
| `16` | 1.00 | -0.336961 | -0.071590 | 0.009129 | 0.109254 | 0.593621 | 0.083820 | 0 | 2 | 1 |

The consequential global/legacy discrepancy is NORAD 68739. At 0.50, the
global profile selects the positive endpoint with TRAIN objective `360.910`;
the legacy bounded call selects the other local basin at `-0.222435` with
objective `499.539`. The winning source has 134 TRAIN observations across five
tracks, a best/second gap of `138.629`, and a maximum fitted phase of `9.470 s`.
At the diagnostic 1.00 bound it has two local minima and settles at `+0.593621`
with objective `319.785`; the second basin remains near `-0.222435` and the gap
widens to `179.754`.

The two ambiguity flags are NORADs 57248 and 58683. Each has only four TRAIN
observations in one track. Their fitted rates are respectively `9.53e-5` and
`1.28e-4 s/hour`; the second candidate is zero, with objective gaps
`6.40e-7` and `9.51e-7` against the predeclared `1e-6` ambiguity threshold.
Audit-only exact-SGP4 TRAIN scoring preserves the same preference and nearly
identical gaps. It is recorded in `smoke.json` but does not resolve the flags or
affect selection or the prospective gate.

## Exact SGP4 replay

| Group | Zero max error (Hz) | 0.25 | 0.50 | 1.00 diagnostic | Largest fitted phase (s) |
|---|---:|---:|---:|---:|---:|
| `00` | 0 | 0.0000422 | 0.0001366 | 0.0001346 | 7.576 |
| `16` | 0 | 0.0000757 | 0.0003271 | 0.0006609 | 11.243 |

Every arm passes the frozen `0.2 Hz` maximum-error gate by a wide margin. Earth
rotation remains fixed at receive time plus global tau while exact SGP4 orbit
time receives the fitted phase shift. The machine-readable records use the
`exact_sgp4_gate` key and schema `ds1-causal-rate-exact-sgp4-gate/v1`.

## What worked, what failed, and what was learned

The widened global profile worked as an audit mechanism. It eliminated the
false unimodality assumption, reproduced stable rates where the legacy search
was adequate, exposed its wrong-basin result for 68739, bounded phase coverage
per source, and completed in about 92 seconds for both groups. The 0.50 arm
also removes every active fit in group `00` and passes all replay checks.

The prospective arm failed its declared gate. One well-supported group-16
source still wants a rate beyond 0.50, and two extremely sparse sources fail
the ambiguity rule. The 1.00 diagnostic shows that a numerical widening alone
can remove the boundary, but adopting that scale after seeing the result would
weaken the physical prior and violate the frozen gate. The global result also
shows why the old bounded optimizer was unsafe: a successful convergence flag
did not mean that it found the best one-dimensional basin.

The next iteration should remain at fixed coordinates and diagnose NORAD 68739
before any geographic basin. It should test whether the positive-rate basin is
stable under predeclared TRAIN-only support perturbations and use a declared
sparse-source policy for profiles backed by only one four-observation track.
Only after those model/support rules are frozen should a new prospective bound
and basin gate be proposed. Randomized HELD should remain report-only, and no
new RF collection is needed.

## Reproduction and sealed artifacts

`plan.json` and `smoke.json` have adjacent SHA-256 seals. The smoke artifact
contains every source profile, best/second support and gap, legacy comparator,
rate distribution, optimizer boundary audit, exact replay gate, per-track
score, and per-session change.

```bash
.venv/bin/pytest -q \
  reports/2026_09_25_ds1_iteration23_widened_rate/test_run.py

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python \
  reports/2026_09_25_ds1_iteration23_widened_rate/run.py \
  --output reports/2026_09_25_ds1_iteration23_widened_rate/smoke.json
```

# Fixed satellite families: phase clipping and the remaining position bias

Holding the blind candidate families fixed identifies a concrete S01 failure:
the three measured-curved arcs nominated as NORAD 100320 need about -3.7 s of
shared orbital phase at GPS, outside the old -3 s limit. With hardware and all
other satellite phases frozen, this adds 173 compatible points, 141 curved and
32 on linear tracks, without losing or relabelling existing assignments. A
1,707-candidate grid audit finds only 100320 passing all three arcs in each c arm.
This remains conditional frequency compatibility, not authenticated identity.

Independent fixed-family position searches improve S01 to 6.36 km. DS22's fixed
families give 2.14 km, worse than the earlier 1.89 km fitted-c result. No new
sub-0.5 km result or full-corpus validation is established.

## Immutable-family transport

The common population and labels come only from the earlier blind **c=0** result
in each dataset. Both c arms use identical source observations, original IDs,
candidate labels, hardware/phase initializers, causal banks, priors and budgets.
S01 has 1,519 points on 43 individually measured-curved fragments; DS22 has
1,123 points on 29. Linear fragments are excluded even from component constants
and all calibration/state ranking. Gaussian fitting includes every selected
observation and never drops a failing member or switches NORAD. Native aliases
remain discrete whole-fragment profile branches; no extra track slope is fitted.

We compare separate fragment constants with the existing blind merged-family
shared constants, after removing all linear members from calibration. S01
reduces 43 constants to 36; DS22 stays at 29 because its selected curved members
were not joined. All fits use exact nonlinear phase geometry, two initial phase
states, up to six relinearizations and monotonic tangent/nonlinear steps.
Receiver/band offsets remain scan-local; drift prior sigma is 0.5 Hz/s, default
bound 1 Hz/s. Original per-satellite Gaussian phase priors are retained.

The cap of 50 points per component changes weights after merging. Accordingly,
scores across shared/separate models are not directly comparable; raw RMS,
residual compatibility and actual position error are reported separately.

| Dataset | c arm | Constants | Position | RMS Hz | Member points / all | Family points |
|---|---|---|---|---:|---:|---:|
| DS22-001 | c=0 | Shared | blind_source | 81.5 | 1071 / 1123 | 1071 |
| DS22-001 | c=0 | Shared | supplied_gps | 82.5 | 1016 / 1123 | 1016 |
| DS22-001 | fitted-c | Shared | blind_source | 81.5 | 1071 / 1123 | 1071 |
| DS22-001 | fitted-c | Shared | supplied_gps | 82.5 | 1016 / 1123 | 1016 |
| DS22-001 | c=0 | Separate | blind_source | 81.5 | 1071 / 1123 | 1071 |
| DS22-001 | c=0 | Separate | supplied_gps | 82.5 | 1016 / 1123 | 1016 |
| DS22-001 | fitted-c | Separate | blind_source | 81.5 | 1071 / 1123 | 1071 |
| DS22-001 | fitted-c | Separate | supplied_gps | 82.5 | 1016 / 1123 | 1016 |
| DSX01-S01 | c=0 | Shared | blind_source | 122.8 | 1496 / 1519 | 1496 |
| DSX01-S01 | c=0 | Shared | supplied_gps | 148.1 | 1029 / 1519 | 963 |
| DSX01-S01 | fitted-c | Shared | blind_source | 122.6 | 1496 / 1519 | 1496 |
| DSX01-S01 | fitted-c | Shared | supplied_gps | 147.8 | 1029 / 1519 | 963 |
| DSX01-S01 | c=0 | Separate | blind_source | 122.3 | 1496 / 1519 | 1496 |
| DSX01-S01 | c=0 | Separate | supplied_gps | 148.1 | 1029 / 1519 | 1029 |
| DSX01-S01 | fitted-c | Separate | blind_source | 122.3 | 1496 / 1519 | 1496 |
| DSX01-S01 | fitted-c | Separate | supplied_gps | 148.1 | 1029 / 1519 | 1029 |

The fixed blind position is the same earlier c=0 coordinate for both c arms.
The GPS diagnostic uses 37.849061591561885, -122.48574968092912, height 0 m.
Compatibility uses the unchanged 450 Hz RMS, 3,000 Hz constant and member
mean/slope/quadratic/step/lag-1 screens; shared families additionally need the
pooled residual screen. Failed observations remain fully costed in these
diagnostic fits and cannot be called newly qualified calibration evidence.

## Bound sensitivity separates two effects

At GPS, NORAD 100320 hits its -3 s phase limit and two S01 receiver drifts hit
+1 Hz/s. We independently release the phase box to at least +/-15 s, the drift
box to +/-5 Hz/s, or both. **Gaussian priors do not change.** These are diagnostic
stress tests, not evidence that physical drifts should have larger priors.

| Released bound | c arm | GPS raw RMS Hz | Passing member points / 1519 |
|---|---|---:|---:|
| both | c=0 | 132.1 | 1129 |
| both | fitted-c | 132.1 | 1129 |
| drift5 | c=0 | 147.1 | 1003 |
| drift5 | fitted-c | 147.1 | 1003 |
| phase15 | c=0 | 132.1 | 1129 |
| phase15 | fitted-c | 132.1 | 1129 |

The phase release restores all three 100320 curved members: 25, 43 and 73
points. Their shared phase is -3.717 s in the joint transfer fit. Drift release
alone barely helps and leaves that satellite clipped. Releasing both gives
about 132 Hz pooled RMS versus 148 Hz under default boxes, but other families
still fail. Clipping is a demonstrated local association failure, not a full
explanation of the geographic bias.

## Frozen-hardware phase repair and candidate competition

For the actual association update we freeze the earlier known-GPS hardware and
all other satellite phases. Only the reviewed satellite phase is profiled, with
its original sigma=1 s Gaussian prior, on 601 exact phase states from -15 to
+15 s in 0.05 s steps. Every one of the same 141 curved observations contributes.
No linear track calibrates this phase. The passing grid interval is -3.90 to
-3.60 s in both c arms; this is a residual-gate interval, not a confidence level.

![Clipped phase profile](clipped_family_phase.png)

The full causal bank competition forces one common candidate and phase to
explain all three arcs. Already-supported satellite phases stay fixed; other
candidates receive the same 601-state grid and their own unchanged Gaussian
phase prior. Each candidate model pays that phase prior once. Ranking occurs
after every member's visibility, constant, RMS and residual checks.

| c arm | Candidates | Phase grid size | Passing candidates | NORADs |
|---|---:|---:|---:|---|
| c0 | 1707 | 601 | 1 | 100320 |
| fitted_c | 1707 | 601 | 1 | 100320 |

The finite grid does not prove uniqueness over every continuous phase or model.
The three arcs and frozen hardware were selected using the same dataset; the
audit is not external identity truth or a calibrated false-discovery rate.
All 601 scalar phase costs and passing flags for 100320 agree with the full
candidate-vector computation, checked numerically in both c arms.

| c arm | Phase s | Before | After | % all raw GLRT | Gained | Lost / relabelled | Merged tracks |
|---|---:|---:|---:|---:|---:|---:|---:|
| c0 | -3.70 | 2009 | 2182 | 45.49% | 173 | 0 / 0 | 74 |
| fitted_c | -3.70 | 2009 | 2182 | 45.49% | 173 | 0 / 0 | 70 |

The denominator is all 4,797 S01 GLRT detections, including observations outside
the original 4,487-point Graph catalogue. The 2,009-point baseline already uses
candidate-after-gates ranking, which adds eight points to the earlier 2,001-point
repaired baseline. The **additional 173** are attributable to this one phase
change. All new points nominate 100320, including two 16-point linear fragments
on RX2 CH7 and CH8. All original IDs and the T009 background endpoint remain
accounted for. Re-evaluation has zero losses and zero relabels in both arms.

| Fragment | Points | Time span s | RMS Hz, c=0 | Curved phase calibration |
|---|---:|---|---:|---|
| RX2-CH1-T002 | 25 | 121.01–149.04 | 135.7 | Yes |
| RX2-CH2-T001 | 43 | 120.35–149.08 | 143.4 | Yes |
| RX2-CH4-T000 | 73 | 110.50–172.60 | 131.8 | Yes |
| RX2-CH7-T005 | 16 | 135.47–149.30 | 132.5 | No |
| RX2-CH8-T002 | 16 | 137.64–157.51 | 157.9 | No |

![Known-position association gain](known_position_gain.png)

## Independent local position searches

Separate searches read only the prior blind c=0 family labels and initial state;
they never read GPS transport/phase-repair outputs. The Gaussian criterion keeps
all selected curved observations in the fit. Both c arms use the same 3x3
+/-16 km grid and binary scales 8, 4, 2, 1, 0.5, 0.25, 0.125, 0.0625 km,
two axial sweeps per scale, at most 73 unique locations. Every location gets
exact nonlinear phase fitting. A synthetic two-axis minimum test checks that
the schedule can actually reach fine resolution; dropping scale by four with
only two sweeps can stop early even on a smooth quadratic surface.

Each endpoint is saved and hash-bound before GPS is used for error evaluation.
Full-bank association is then a post-fit extension with hardware/position fixed,
unestimated satellite phases set to zero, and the usual curved-support and
lossless member/pooled merge checks. It has no feedback into fixed-family
position fitting. No source curved fragment changes NORAD in those extensions.

| Dataset | c arm | Constants | Box floor s | Error km | Curved / fitted | Associated | Tracks |
|---|---|---|---:|---:|---:|---:|---:|
| DS22-001 | c=0 | Separate | 0 | 2.139 | 1016 / 1123 | 1515 | 47 |
| DS22-001 | fitted-c | Separate | 0 | 2.139 | 1016 / 1123 | 1515 | 47 |
| DSX01-S01 | c=0 | Shared | 0 | 6.479 | 1446 / 1519 | 2436 | 68 |
| DSX01-S01 | fitted-c | Shared | 0 | 6.479 | 1446 / 1519 | 2392 | 67 |
| DSX01-S01 | c=0 | Separate | 0 | 6.356 | 1446 / 1519 | 2436 | 64 |
| DSX01-S01 | fitted-c | Separate | 0 | 6.356 | 1446 / 1519 | 2436 | 64 |
| DSX01-S01 | c=0 | Separate | 15 | 6.356 | 1446 / 1519 | 2436 | 64 |
| DSX01-S01 | fitted-c | Separate | 15 | 6.356 | 1446 / 1519 | 2436 | 64 |

S01's optimum is unchanged by widening the phase box alone. Merging slightly
changes its endpoint rather than resolving the remaining error. DS22's shared
curved groups are identical to the separate groups, so duplicated merged
searches were not run. Some fitted curved members fail the final screens; these
are exploratory, not fully qualified location results. The earlier 1.895 km
DS22 result remains better than this fixed-family variant. More associated
points, lower Gaussian cost and improved geographic accuracy remain distinct.

## Validation and next work

Forty-four focused tests pass, including an independent dense point solve,
immutable labels and point costs, linear-member exclusion, per-candidate phase
prior accounting and bounded two-axis geographic refinement. Final handwritten
sources pass Ruff. The exact audit-run source is archived separately; its later
lint-only change explicitly binds synchronous loop callback variables and has
no numerical effect. Default-bound source snapshots and protocol hashes retain
the versions used for the early transport fits. Earlier sealed reports are intact.

The demonstrated phase-clipping pattern can now be audited on other scans,
requiring shared support from multiple measured-curved arcs and preserving old
assignments. The remaining position discrepancy needs investigation of the
physical frequency inputs and shared residual structure, not an inference that
noise screens alone authenticate a satellite. Independently verify RF/timing
metadata before adding per-track nuisance terms that could erase localization
information. No new RF was collected, and no QNAP path was modified.

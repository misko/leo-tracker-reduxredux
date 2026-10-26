# CFO and precision feedback have different effects in the two scans

All 16 conditional-Gaussian factorial fits completed. DS24-0010's movement is
mostly retained when changing CFO with precision fixed. DS24-0011's movement is
mostly associated with the full precision packet. This distinction holds in
both c arms. It qualifies the preceding raw position gains: they cannot all be
attributed to more accurate physical CFO. Operational references remain unchanged.

![Signed factorial vectors](rf_report/factorial_vectors.png)

## Frozen comparison and posterior checks

The four cells are 00=original CFO/original packet, 10=refined CFO/original
packet, 01=original CFO/refined packet and 11=refined CFO/refined packet.
All use the previous 159-ID correction vector with identical candidates, graph
ownership, aliases, masks, nominal noise, likelihood powers and causal prior
centres/scales. No detector, IQ, new association or geographic selection occurs.

A packet freezes **both** fragment noise precision and full coefficient prior
precision from that case/arm's saved original/refined VI endpoint. This includes
the phase-prior conditional precision, not only observation weighting. Nuisance
means, covariance, phase references and position are solved afresh. Inactive
noise zeros are preserved; only active groups must be positive. Fitted-c slot8
is required to be exactly unit precision before deleting/reinserting it for the
legacy helper. The full same-arm packet and column map replay exactly.

The original predictive wrapper is unchanged: DS24-0010 retains all 615
predictive IDs with shared curved-posterior uncertainty, sigma*sqrt(2) noise and
independent 300 Hz fragment constants. DS24-0011 has no predictive likelihood.
The conditional-Gaussian objective with volume_weight=1 is **not the VI ELBO**;
the legacy interface's field name does not make those numbers interchangeable.
Fractional likelihood powers also make this a generalized objective.

Before fitting, all eight diagonal controls at the saved last input phase
reference and endpoint pass: maximum coefficient difference 3.61e-9, conditional
residual difference 1.67e-7 Hz, predictive raw-residual difference 1.45e-7 Hz and
predictive-objective difference 5.38e-10. Exact value, native-ID, alias, packet,
layout and zero-delta checks also pass. Six owned fixtures cover mapping/refusal,
physical units, normal equations/density, mean refitting and factorial arithmetic.
See [compact preparation](compact/preparation_summary.json).

Each of the 16 fits starts at zero position/phase reference and uses five outer
refreshes by 48 iterations in the same 25x25 km regional box. There are no warm
starts, rescues, retries or larger budgets. All packets remain exact throughout.
Frozen Gamma has no Gamma-convergence claim; final phase changes and optimizer
histories are retained. The maximum final phase change is 1.66e-5 s, below .01 s.

## Signed mechanism decomposition

For endpoint vector x, report CFO effects x10−x00 and x11−x01, packet effects
x01−x00 and x11−x10, and interaction x11−x10−x01+x00. Averaging each factor's
two effects gives the symmetric decomposition below. Components are **signed
east/north metres**, not additive displacement norms or causal percentages.

| Scan / arm | Symmetric CFO vector (m) | Symmetric packet vector (m) | Total x11−x00 (m) | Interaction (m) |
|---|---:|---:|---:|---:|
| 0010, c=0 | (−80.066, +104.478) | (−17.173, −5.663) | (−97.240, +98.815) | (−7.995, −11.595) |
| 0010, fitted c | (−77.202, +104.327) | (−13.818, −1.687) | (−91.021, +102.640) | (−7.413, −11.778) |
| 0011, c=0 | (−21.076, −6.032) | (−54.734, −61.717) | (−75.810, −67.749) | (+0.022, −24.979) |
| 0011, fitted c | (−21.166, −4.626) | (−57.126, −65.237) | (−78.292, −69.862) | (+2.564, −22.627) |

The vector sums close exactly in saved arithmetic. CFO/packet vector norms are
131.63/18.08 m and 129.79/13.92 m in DS24-0010, versus 21.92/82.49 m and
21.67/86.71 m in DS24-0011. Interaction norms are about 14 m and 23–25 m,
respectively. [All factor-level contrasts](rf_report/contrasts.json) retain
the changes in direction and cancellation rather than adding norms.

Noise and prior precision both change between packets. Active noise ratios
reach 0.594 in DS24-0010 and 0.164 in DS24-0011; full prior ratios span about
0.980–1.035 across these arms. Packet effects therefore include conditional prior
precision as well as observation precision. The packets were learned at different
VI endpoints, so this does not establish true physical noise or identify a
uniquely correct weighting policy.

## Geographic evaluation and distinction from VI

The evaluator was frozen before results. It runs only after the RF seal,
independent terminal PASS and explicit root release, using the same known-site
coordinate and haversine distance as the prior comparison. All completed raw
errors are retained separately from the unchanged original VI operational error.

| Scan / arm | 00 error (km) | 10 error (km) | 01 error (km) | 11 error (km) | CFO gain at old/refined packet (m) |
|---|---:|---:|---:|---:|---:|
| 0010, c=0 | 1.237204 | 1.104368 | 1.231146 | 1.105605 | 132.836 / 125.542 |
| 0010, fitted c | 1.243988 | 1.111407 | 1.234750 | 1.107660 | 132.580 / 127.089 |
| 0011, c=0 | 1.727732 | 1.709973 | 1.660151 | 1.634415 | 17.759 / 25.736 |
| 0011, fitted c | 1.567030 | 1.546597 | 1.498937 | 1.476454 | 20.433 / 22.484 |

![All sixteen position errors](geographic/factorial_position_errors.png)

Fixed-state diagonal posterior closure does not require conditional-Gaussian
optimized endpoints to equal VI endpoints. DS24-0010's cell00 differs from the
old original VI endpoint by 5.52/3.22 m and cell11 differs from the refined VI
endpoint by 2.49/1.15 m. Its predictive term depends on the Gamma-derived curved
posterior/covariance, so optimizing with Gamma frozen changes the objective's
position dependence. DS24-0011 diagonal differences are below .008 m. These are
reported model/optimizer consequences, not failed preparation controls. No
old VI ELBO is subtracted from a conditional-Gaussian objective to choose a cell.

## Gates and coverage use each cell's actual conditional posterior

All 16 original active residual/owner gates and final phase limits pass.
Membership is computed directly from that same conditional p using the original
retained_metrics, summary and extend_associations. No helper rebuilds a VI model
for the gates. Likelihood IDs remain exactly 2571 curved+615 predictive in
DS24-0010 and 2241 curved+0 predictive in DS24-0011.

DS24-0010 retains all 3186 accepted IDs in every cell and both arms; all four
cells meet the old paired residual/phase/retention checks as research diagnostics.
DS24-0011 c=0 loses 0/36/21/57 original postfit-only IDs in cells00/10/01/11;
fitted-c loses none. Thus only cell00 retains complete original IDs in both arms.
The altered cells fail paired retention despite passing fitted-data gates.
Original GLRT denominators remain 4268 and 3754. Postfit coverage is distinct
from the fixed likelihood; no fitted observation is dropped. All raw results
remain diagnostics and no cell is adopted operationally.

## Scope and artifacts

This is a two-scan exposed development mechanism test, not validation or proof
of physical CFO accuracy. The strong DS24-0010 within-packet CFO effect survives
precision freezing; the DS24-0011 result warns that a similar raw position gain
can mainly reflect precision feedback. It motivates preserving this distinction
in later bounded transfer tests, not tuning weights on these geographic errors.

All 16 outcomes complete in 29.082741 cumulative numerical worker-seconds,
including 8.064566 seconds of preparation/tests, under the unchanged 600-second
cap and 30-second per-fit cap. There were no failed slots, retries or extensions.
Full data/packet definitions are in [PROTOCOL.md](PROTOCOL.md),
[protocol.json](protocol.json), [packets.json](packets.json), [model.py](model.py)
and [run.py](run.py). The [RF table](rf_report/outcomes.csv),
[geographic table](geographic/outcomes.csv), [RF seal](RF_seal.json),
[RF report seal](rf_report/seal.json), [geographic seal](geographic/seal.json),
and independent [preflight](../audit/preflight.json) / [terminal](../audit/terminal.json)
preserve the complete denominator and evaluation sequence.
[lean_publication.json](lean_publication.json) includes compact endpoints,
packet identities, gates, coverage and histories while binding the larger raw
parent/residual/diagonal arrays at their original absolute paths. Full replay
requires those declared inputs; no alternative detector or calibration is used.

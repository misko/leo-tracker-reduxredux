# DS21-039: timing compensates the saved weak-direction displacement

For the **prescribed ±1 km displacements along each saved weak position direction**, restoring the fitted satellite timing accounts for **99.5–99.9%** of the geography-only NLL increase. Receiver calibration alone has a much smaller effect, and its benefit substantially overlaps timing compensation. This is finite evidence of position/timing confounding in the original model, not a timing error diagnosis or a new localization result. The remaining refined minus/plus asymmetry is mostly a likelihood effect with mixed receiver/band/block contributions; visibility and sampling-integer changes do not explain it.

The [prespecified protocol](TIMING_CALIBRATION_FACTORIAL_PROTOCOL.md) makes **18 original objective/gradient evaluations and zero fits**: two saved endpoint replays, plus four nuisance combinations at each of the four saved [fixed-geography profiles](FIXED_GEOGRAPHY_TIMING_PROFILE_RESULTS.md). Every cell retains the same displaced geography, all **2,798 training windows / 3,714 native candidates / 43 satellites**, fitted common `c`, original priors, neutral singleton likelihood and exact native timestamps. Geography uses endpoint calibration/timing; calibration and timing cells each restore the corresponding saved fitted block; full restores both. No reference or held data are read, no new position is estimated, and no alternative prior or direction is selected.

## Finite main effects and interaction

The table uses NLL differences. Calibration, timing and full columns compare to the geography-only cell at that same fixed point. Interaction is `full − calibration − timing + geography`; positive interaction means the separate improvements overlap rather than add independently.

| Saved endpoint / sign | Geography − endpoint | Calibration − geography | Timing − geography | Interaction | Full − endpoint |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original / minus | +7063.356 | −207.291 | −7037.738 | +187.002 | +5.328 |
| Original / plus | +7386.776 | −306.838 | −7349.692 | +273.174 | +3.420 |
| Refined / minus | +7735.340 | −71.395 | −7717.165 | +60.161 | +6.940 |
| Refined / plus | +8059.185 | −30.012 | −8050.917 | +24.267 | +2.523 |

Timing-only recovery is **99.637 / 99.498%** for the original minus/plus points and **99.765 / 99.897%** for the refined points. Adding calibration after timing lowers NLL by only **20.289 / 33.664** and **11.234 / 5.745**, respectively. These percentages apply to these saved weak-direction displacements, not arbitrary geographic moves. All mixed states pass original domain checks; they are diagnostic states, not stationary contenders or separately optimized minima.

The original common/relative timing and group-offset priors are separable across this factorial. Their interaction closes to zero within **2.84e−14**; complete-objective interaction therefore agrees with likelihood interaction. Relative to the saved endpoints, full-profile objective changes are **+4.496 / +4.222** original and **+6.504 / +3.004** refined. The refined plus-minus difference is **−4.417 NLL / −3.501 objective**, preserving the previously observed local asymmetry without introducing another fit.

## Assignment and support changes

Restoring timing from geography-only produces roughly **1,000–1,150 satellite/clutter MAP changes**, while the full saved nuisance profile is much closer to its original endpoint:

| Full versus original endpoint | Joint native/satellite TV sum | Satellite/clutter MAP changes | Native-candidate/clutter MAP changes |
| --- | ---: | ---: | ---: |
| Original / minus | 19.954 | 25 | 2 |
| Original / plus | 17.420 | 29 | 2 |
| Refined / minus | 12.618 | 15 | 6 |
| Refined / plus | 16.523 | 28 | 10 |

The large geography-only comparison counts describe the deliberately uncompensated cell. They must not be relabeled endpoint instability. Joint TV preserves native candidate×satellite responsibilities; candidate TV/MAP first marginalizes satellites, and satellite TV/MAP first marginalizes candidates. MAP categories are model allocations, not measured transmitter identities.

There are **zero sampling-integer changes in every comparison**. Full versus endpoint also has **zero native visibility changes**. Across nuisance factorial cells, changed visibility affects only **2 / 1 / 3 / 1 windows**, contributing **+0.110 / +0.488 / −0.054 / +0.176** to the respective interactions. Almost all interaction remains on unchanged visibility support. Timing changes **69,486 / 67,983 / 74,667 / 74,677 native×satellite interpolation cells**; calibration alone changes none. These are transition counts across saved timing queries, not counts of faulty windows. Uniform-bank interpolation can change cells continuously; this diagnostic does not establish an interpolation defect.

## Concentration and limits

The refined full-profile plus-minus NLL difference has opposite signed contributions from RX0/RX1 (**−18.033 / +13.616**) and low/high bands (**+3.974 / −8.391**), yielding net **−4.417**. The original low/high signs reverse (**−4.196 / +2.287**). Refined blocks also cancel: blocks 4/7 contribute **−5.625 / −6.232**, while blocks 13/14 contribute **+6.144 / +3.584**. No universal receiver or band fault follows from these allocations.

Interaction is likewise mixed. Refined minus interaction has **+56.686 RX0 / +3.476 RX1**, with block 5 at **+35.582** and block 14 at **−43.227**. Refined plus has **+40.291 RX0 / −16.024 RX1**. Every original window and every counter-defined training block, receiver, channel and band remain in the persisted attribution, including opposite-signed and changed-support contributions. These descriptive counts/masses do not establish independent samples or significance.

Independent saved-array audit checked **344 live/archive sources**, the unchanged **340-source** fixed-profile subset and ancestor archives, exact state assembly, all 18 launch/result/termination records and native NPZs, and the **79-file final seal** plus outer completion. All six endpoint/full saved scalar replays are **exactly zero**. Probability closure is within **4.44e−16**, per-window NLL closure **7.28e−12**, prior closure **6.28e−12**, and interaction closure **8.57e−12**. Native/satellite/candidate TV and MAP changes, visibility/alias/cell transition counts, and all grouped sums were independently reconstructed from saved arrays. No new scientific evaluator was called. [Compact audit and hashes](TIMING_CALIBRATION_FACTORIAL_AUDIT.json) retain all four profiles and signed group summaries; full responsibilities remain in immutable local NPZ receipts.

The inner diagnostic completed in **18.760 seconds**, with **18.845 seconds** recorded by the outer attempt, within **90 / 105 / 110 seconds internal / TERM / KILL**. Frozen sources are unchanged. The result supports conditional timing compensation of these weak-direction moves and rules out visibility/sampling-integer transitions as the dominant aggregate explanation here. It does not establish wrong TLEs, a justified replacement timing prior, global nuisance minima, hardware truth or improved position accuracy. No timing-prior sweep or reference-derived intervention is justified by this audit.

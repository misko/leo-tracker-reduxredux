# Scientific interpretation review

This review uses sealed outputs only. The numerical snapshot had 23 primary attempts: 18
`converged_local_mode`, five `unresolved`, and 41 of the planned 64 scans not yet attempted.
It is an interim regression-panel diagnostic, not a final accuracy result or holdout test.

Among the 18 accepted local modes, roof-reference errors range from 659 m to 9.11 km with a
median of 1.64 km; three are below 1 km and 16 are below 5 km. Every accepted fit consumed
all planned factors. All current fitted means are inside the intended 250 km disk (their
Sacramento-centered radii are 112–121 km), and the examined clock and satellite epoch means
remain below 5 seconds in magnitude. These checks remove an obvious boundary or partial-data
explanation for this snapshot, but they do not establish global optimality, calibrated
uncertainty, or correct satellite identities.

Only three currently accepted T4 scans also have an accepted original-greedy error. Their T4
versus original errors are 2.881 vs 2.737 km, 1.648 vs 0.906 km, and 1.437 vs 2.195 km. This
matched subset is too small and selected by both methods succeeding. Medians over it are not
a defensible superiority estimate. Original failures must remain in the all-64 denominator.

The original geographic gates had conservative failure semantics. A position-support failure
meant that at least one retained Gaussian's mean-plus-five-sigma bound crossed 489 km; many
such triggers carried little mixture weight. A center-boundary failure meant at least one
component mean crossed 250 km. Neither means the highest-weight point itself was outside the
region. Original errors and orbit-interpolation exceptions were also excluded from accepted
error summaries. Therefore an increase in the number of accepted T4 points can reflect
changed failure mechanics as well as better localization.

Fixing height alone was unlikely to cure the localization problem. The old prior centered
ellipsoid height at 0 km with 0.1 km standard deviation. The specified 30.48 m MSL height
converts through GEOID18 to ellipsoid heights of only a few metres around this region (about
-2.0 m at the roof), already near the old prior center relative to its 100 m scale. Fixing
height removes a weakly identified degree of freedom and prevents kilometre-scale height
excursions, but it does not resolve wrong satellite assignments. The isolated sequential
development runs support that distinction: after extended orbit coverage allowed DS10 and
DS11 to process all tracks, their errors remained about 312 km and 306 km; the completed DS9
height-only result was about 264 km away.

T4 is not a height-only comparison with the original greedy arm. Besides fixed MSL height and
longer orbit coverage, it changes the Gaussian likelihood to a normalized Student-t model,
uses a 1,024-point all-track spatial proposal, refines multiple basins, jointly reassigns all
tracks, and selects the lowest objective among three local fits. The old greedy method made
sequential irreversible association choices from a 32-Gaussian disk approximation. Any T4
accuracy change is the effect of this package and cannot be attributed to height.

The nominal horizontal prior is also not an exact matched computational representation. Both
declare a Sacramento-centered 250 km uniform disk, but the old filter uses 32 Gaussian cell
moments with documented tail mass, while T4 uses in-disk proposal seeds followed by bounded
local displacement. A final T4 mode could in principle move outside 250 km unless evaluation
checks it explicitly. None in the current snapshot does.

The current denominator handling is honest only if final reporting keeps all 64 planned scans
and separates local numerical convergence from accepted error. The evaluator already withholds
publication before 64 primary attempts and gives unresolved or launch-only failures no accepted
error. As a defensive final check, primary acceptance should also require a valid seal, launcher
completion with return code zero, and runtime within the frozen 90-second budget; all current
accepted rows satisfy those conditions. Continuation acceptance now separately requires a
sealed converged native result, successful launcher, and combined runtime no greater than 180
seconds. Conditional error distributions should be accompanied by all-planned convergence and
threshold-success fractions.

The strongest supported statement is that fixed height and extended orbit support repair two
specific numerical pathologies, while the joint robust search often finds a local mode near the
roof on the partial regression panel. The fixed-height sequential controls show that those two
repairs alone do not cure localization. The full 64-scan accounting is needed to quantify how
often the complete T4 method converges and how often its sealed point is accurate.


# DS22 C conditional and propensity matched profiles

This bounded prototype compares conditional native likelihood with conditional native likelihood plus learned satellite mixture propensities on DS22-019 and DS22-075. Both use the original full-training bank, native branch evidence and calibration frame. The original C has no common receiver clock; none is added. The orthonormal zero-sum propensity coordinates have standard-normal prior, bounds ±2 and solver scale 0.5. Existing physical timing/group priors remain unchanged. The original raw C result is historical context, not a fallback in either new selector.

Each case uses three prespecified training-selected geographies from its original C-all, C-low and C-high results. Only XY differs between initial profile states; all other physical and group nuisance coordinates come from the original C-all winner, and propensity coordinates start at zero. These are shared-discovery half controls, not independent half discoveries. Each geography retains its own original winning 25 km disk:

| Case | Geography provenance | Original start | Original disk center (km) |
|---|---|---:|---|
| 019 | all | 0 | (31.25, 18.75) |
| 019 | low / high | 5 / 5 | (82.7611343494, 71.5781121691) |
| 075 | all / high | 2 / 2 | (-25, -125) |
| 075 | low | 4 | (-105.9405074436, -106.7058963118) |

Before fitting, actual wrapper qualification checks the original objective and full gradients/posterior against the legacy wrapper; conditional mass identity and zero-tail nesting at all three starts; every nonzero propensity-coordinate derivative at the all start; and fixed/free feasibility at all starts. Initializer changes above 1e-12 stop qualification and retain failure. Exact objective counts are 81/95 (caps 85/100), with 120 seconds internal, 135 TERM and 140 KILL. The source and protocol are frozen before preparation.

The matched experiment has 12 fixed-geography profiles: two arms × three positions × two cases. Both profile-arm units for a case must finish before any release. Only accepted profiles are released in their own original disks, giving at most 12 additional calls and 24 total. Each case/arm/stage unit has at most three calls and a 180-second internal, 195-second TERM and 200-second KILL bound. At most four single-thread workers run. Each fit uses the existing solver's 20-second and 600-iteration limits; 600 is not an objective-evaluation cap. Independent replay/domain/KKT auditing occurs after optimizer return and outside that 20-second optimizer budget. Fixed profiles must preserve XY exactly, and the existing strict KKT threshold remains 0.001 for all physical and nuisance coordinates. No gradient finisher or threshold relaxation is introduced.

Durable claims precede fits. Failed or nonstationary outcomes remain explicit; rejected profiles receive no release, and calls are not retried. Within each arm, select the accepted free release with lowest own training objective, breaking ties by all/low/high order. No accepted release means unavailable. Objectives are not ranked across different priors/arms to choose a model. Both cases must seal completely before a separate configured-reference comparison; no held or locked data is accessed. A successful fit would remain an extra-budget prototype, not a cohort promotion.

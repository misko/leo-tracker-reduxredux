# Joint stationary-position inference across all 43 DS6 scans

This experiment is complete. The all-43 joint station estimate is **772 m**
from the operator reference. Both prespecified complementary random scan
subsets also produce sub-kilometre estimates:

| Fit | Scans | Horizontal error (m) | Held log-score change vs independent fits |
|---|---:|---:|---:|
| All DS6 | 43 | 772.34 | -2875.48 |
| Random subset A | 22 | 941.20 | -1741.54 |
| Random subset B | 21 | 639.57 | -1090.97 |

The two subset locations are 594.16 m apart. All three selected estimates
converge inside their search bounds. Exact propagation differs from interpolated
prediction by at most 0.0204 Hz. Four validation tests pass, including full
membership, complementary seeded splits, training-only selection, and the real
exact-propagation audits.

The frozen protocol defines an all-43 fit and two complementary whole-scan
subsets assigned by a recorded random seed before their outcomes were scored.
Each included scan retains its original randomized whole-visit training/held
partition. The model fits a single station position and separate scan timing
offsets, with fixed 100 Hz Student-t4 errors and per-track frequency offsets.

This asks whether additional satellite geometries across the complete night
support a common station location. It does **not** claim to solve independent
five-minute scan positioning. Those errors remain available in the full CFO
baseline, whose median is 2.425 km and whose sub-kilometre count is 6/43.

The implementation evaluates sparse numerical gradients: each scan depends on
two shared position parameters and its own timing parameter. Synthetic tests
verify equality with full numerical differentiation, recovery of known common
geometry with distinct clocks, and held-score isolation. These tests do not
establish convergence or accuracy on real DS6 data.

Two starts were defined in advance for each fit. Training likelihood alone
selects the winner. Exact propagation audits every included scan after fitting.
`all.json`, `A.json`, and `B.json` contain the completed fits and audits.
The fitting script does not load the operator reference coordinate. Local
search limits and inherited approximate catalogue shortlists remain explicit
limitations; no blind global-localization claim is made.

Held prediction is worse than fitting scans independently. A stationary site
constraint can average location errors while leaving systematic scan-dependent
errors unresolved. These results establish sub-kilometre **joint estimates on
this dataset**, not sub-kilometre independent-scan performance, surveyed error
bounds, or generalization to another physical station. The operator reference
has no supplied survey uncertainty. The broader per-scan goal remains unmet.

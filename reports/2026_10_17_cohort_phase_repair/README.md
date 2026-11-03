# All-scan curved-family phase repair and input-model checks

The phase-clipping repair generalizes across DSX01: 5 jointly supported
families add **504 / 504 points** in c=0 / fitted-c,
including 400 / 400 curved and
104 / 104 linear points. Old losses are
0 / 0; no retained old point changes identity.
Totals are **10,909 / 20,084
(54.32%)** for c=0 and
**10,890 / 20,084
(54.22%)** for fitted-c.
All figures here distinguish known-position association from blind accuracy.
The authoritative phase outputs are in `curved_only/`. Parent-level phase
outputs are preserved as superseded: they incorrectly locked competing phases
with linear-only support. RF/prior sensitivity and input audits are separate
experiments and remain at the parent level.

## Conservative nominations and candidate competition

Every scan retains its own four receiver/band offsets and small linear drifts.
Hardware stays frozen. A satellite keeps its phase only if an admitted curved
fragment supports it in either c arm. Linear-only matches cannot lock or veto
a phase. A common c0 nomination pool uses only curved fragments unassociated
in both arms, each independently measured-curved, and requires at
least two fragments whose nominated phase hit its old bound. Linear fragments
cannot nominate, estimate, rank or lock a phase. Eight families qualify: four in S01,
three in S03, one in S04; S02/S05 have none under this rule.

A 601-state -15…+15 s profile retains the original Gaussian phase priors and
all raw CFOs, times, RFs and IDs. Every nominated curved member must pass the
visibility, bias, RMS and mean/slope/quadratic/step/lag-1 checks at one common
candidate/phase. Five families pass; three remain rejected (S01 62052 / 63474,
S03 59547). No fragment is discarded to manufacture an all-member pass.

For each passing family, every candidate in its prepared causal bank competes;
only candidates with admitted curved support retain their established phases. The nominated
satellite is the sole passing candidate on the tested grid in both c arms.
Gaussian bias/phase/conditional-volume penalties remain; one candidate model
pays its phase prior once, rather than once per fragment or competing satellite.

| Scan | NORAD | c arm | Curved fragments / points | Candidates | Phase s | Passing grid range s |
|---|---:|---|---:|---:|---:|---|
| DSX01-S01 | 100320 | c=0 | 3 / 141 | 1707 | -3.70 | -3.90…-3.60 |
| DSX01-S01 | 100320 | fitted-c | 3 / 141 | 1707 | -3.70 | -3.90…-3.60 |
| DSX01-S01 | 69546 | c=0 | 2 / 54 | 1707 | -0.70 | -2.10…-0.70 |
| DSX01-S01 | 69546 | fitted-c | 2 / 54 | 1707 | -0.70 | -2.10…-0.70 |
| DSX01-S03 | 59552 | c=0 | 2 / 41 | 1422 | -0.75 | -1.80…-0.70 |
| DSX01-S03 | 59552 | fitted-c | 2 / 41 | 1422 | -0.75 | -1.80…-0.70 |
| DSX01-S03 | 64112 | c=0 | 2 / 76 | 1422 | -0.65 | -0.95…-0.60 |
| DSX01-S03 | 64112 | fitted-c | 2 / 76 | 1422 | -0.65 | -0.95…-0.60 |
| DSX01-S04 | 61912 | c=0 | 2 / 88 | 1427 | -1.40 | -1.45…-1.40 |
| DSX01-S04 | 61912 | fitted-c | 2 / 88 | 1427 | -1.40 | -1.45…-1.40 |

Ranges are gate-passing grid samples, not confidence intervals. Some selected
phases lie at a gate boundary because the retained prior is strong; this should
not be presented as precise orbit calibration. Uniqueness is conditional on the
prepared candidate bank, same-data nominations, frozen hardware and finite grid;
it is not external identity truth or a calibrated false-discovery guarantee.

## Association with old and jointly vetted labels preserved

The final evaluation binds old accepted identities and the newly vetted
curved-family identities, then evaluates every candidate for remaining tracks.
Fixed labels still require every physical/residual/support gate. Preserving a
family label does not allow a bad residual through. This avoids breaking an
overdetermined common-family result by selecting a different candidate for an
individual member. A new narrow association port supports these bindings;
default association is unchanged. Linear fragments associate only afterward.
Old linear matches are rechecked under the curved-learned phases and can fail;
their survival is never used to select or veto a phase.

| Scan | c arm | Before → after | % raw GLRT | New curved / linear | Merged tracks | Points/track |
|---|---|---:|---:|---:|---:|---:|
| DSX01-S01 | c0 | 2009 → 2291 | 47.76% | 195 / 87 | 80 | 28.6 |
| DSX01-S01 | fitted_c | 2009 → 2291 | 47.76% | 195 / 87 | 73 | 31.4 |
| DSX01-S02 | c0 | 1868 → 1868 | 53.01% | 0 / 0 | 56 | 33.4 |
| DSX01-S02 | fitted_c | 1857 → 1857 | 52.70% | 0 / 0 | 56 | 33.2 |
| DSX01-S03 | c0 | 2674 → 2791 | 69.98% | 117 / 0 | 78 | 35.8 |
| DSX01-S03 | fitted_c | 2649 → 2766 | 69.36% | 117 / 0 | 66 | 41.9 |
| DSX01-S04 | c0 | 1978 → 2083 | 56.01% | 88 / 17 | 61 | 34.1 |
| DSX01-S04 | fitted_c | 1995 → 2100 | 56.47% | 88 / 17 | 57 | 36.8 |
| DSX01-S05 | c0 | 1876 → 1876 | 46.25% | 0 / 0 | 60 | 31.3 |
| DSX01-S05 | fitted_c | 1876 → 1876 | 46.25% | 0 / 0 | 60 | 31.3 |

The denominator includes all 20,084 raw GLRT detections, including marks outside
the original 18,338-point Graph catalogue. The original T009 and S02 background
points remain explicit and unassociated. Baselines include the earlier robust
partition and candidate-after-gates ordering; S01 starts at 2,009 rather than
the older 2,001. Old curved-supported phases and retained accepted NORADs stay fixed.
Shared-constant joining retains all admitted IDs and identities and applies
member and pooled residual checks with a 30 s maximum gap.

![All-scan coverage](cohort_association.png)

![GLRT point associations](cohort_glrt.png)

## RF and timing input audit

All 18,338 original DSX01 Graph points exactly preserve frozen source RF and
counter-derived times; every unwrapped CFO differs from the original mark by
an integer native alias. Orbit-bank origins match the source/adapter UTC anchors.
Lower/upper source IDs agree with their different RF edge lattices. The 230.625
MHz difference between the S01 lower edge and DS22 upper edge is therefore not
an adapter unit error. This checks exported metadata, not physical LO metrology.

For DS22-001 the original 14.7 MB public source snapshot is hash-verified and
all 4,039 published winning marks reproduce exactly. All 3,510 Graph points
retain their original time/RF/alias binding. Its nominal rate is 2.5 MS/s,
20 ms probes; the adapter uses device-counter elapsed time plus a half-probe
midpoint, with a 0.124731 s UTC half-bracket. Source RF authority remains
`hypothesis`. Absolute RF calibration or unmodelled UTC latency is not proven.
DSX01's original live input files are locally unreadable; its sealed source and
context exports provide the audited authority. This did not block the analysis.

`input_audit/` preserves all checks and hashes. No RF, CFO, timestamp or original
contract was silently corrected.

## Explicit RF-reference sensitivities are rejected as repairs

Using fixed earlier blind c0 families and initial states in both c arms, three
predeclared Doppler coefficients were tested: sampled edge, the midpoint of the
paired recorded edge settings, and twice the deviation from that midpoint.
Only the Doppler coefficient changes; actual RF metadata and the hardware c
feature remain unchanged. Every hypothesis gets the same exact-geometry binary
search cap of 73 locations and the same priors, points, labels and initializers.
GPS is used only after saving each independent endpoint, then in a separate
fixed-position frequency diagnostic. These are exploratory coefficient tests,
not new RF calibration authority. Original phase boxes are used in this table.

| Dataset | c arm | Coefficient hypothesis | Error km | Endpoint RMS Hz | Passing curved / fitted |
|---|---|---|---:|---:|---:|
| DS22-001 | c=0 | double_edge_offset | 5.751 | 292.4 | 72 / 1123 |
| DS22-001 | fitted-c | double_edge_offset | 5.561 | 291.5 | 45 / 1123 |
| DS22-001 | c=0 | edge_midpoint | 0.978 | 278.6 | 111 / 1123 |
| DS22-001 | fitted-c | edge_midpoint | 0.937 | 278.4 | 84 / 1123 |
| DS22-001 | c=0 | sampled_edge | 2.139 | 81.1 | 1016 / 1123 |
| DS22-001 | fitted-c | sampled_edge | 2.139 | 81.1 | 1016 / 1123 |
| DSX01-S01 | c=0 | double_edge_offset | 2.347 | 277.1 | 247 / 1519 |
| DSX01-S01 | fitted-c | double_edge_offset | 2.354 | 277.0 | 247 / 1519 |
| DSX01-S01 | c=0 | edge_midpoint | 13.412 | 284.1 | 276 / 1519 |
| DSX01-S01 | fitted-c | edge_midpoint | 13.412 | 284.1 | 276 / 1519 |
| DSX01-S01 | c=0 | sampled_edge | 6.356 | 122.5 | 1446 / 1519 |
| DSX01-S01 | fitted-c | sampled_edge | 6.356 | 122.5 | 1446 / 1519 |

The sampled-edge controls exactly reproduce the previous endpoints. Alternative
coefficients substantially worsen RMS and lose most residual-compatible curved
points. A midpoint DS22 estimate happens to be nearer GPS (~0.94 km), and the
double-deviation S01 estimate is also nearer, while their frequency fits fail.
Neither is adopted or counted as a localization improvement. A smaller error
alone cannot justify changing the physical model.

![RF-reference frequency-fit checks](rf_reference_sensitivity.png)

## Separate phase-prior sensitivity

These runs use the original sampled-edge RF, identical blind families, initial
states and budgets, and hold every phase box at +/-15 s. The original uncalibrated
successive-TLE-disagreement prior is compared with sigma floors of 1 and 3 s.
Thus prior strength changes separately from clipping. Gaussian volume terms
are retained. These floors are sensitivity assumptions, not calibrated orbital
covariances or adopted defaults. There is no linear calibration or point pruning.

| Dataset | c arm | Phase sigma floor s | Error km | Passing curved / fitted |
|---|---|---:|---:|---:|
| DS22-001 | c=0 | 0 | 2.139 | 1016 / 1123 |
| DS22-001 | fitted-c | 0 | 2.139 | 1016 / 1123 |
| DS22-001 | c=0 | 1 | 2.139 | 1016 / 1123 |
| DS22-001 | fitted-c | 1 | 2.139 | 1016 / 1123 |
| DS22-001 | c=0 | 3 | 2.440 | 1071 / 1123 |
| DS22-001 | fitted-c | 3 | 2.424 | 1071 / 1123 |
| DSX01-S01 | c=0 | 0 | 6.356 | 1446 / 1519 |
| DSX01-S01 | fitted-c | 0 | 6.356 | 1446 / 1519 |
| DSX01-S01 | c=0 | 1 | 6.143 | 1427 / 1519 |
| DSX01-S01 | fitted-c | 1 | 6.143 | 1427 / 1519 |
| DSX01-S01 | c=0 | 3 | 6.019 | 1347 / 1519 |
| DSX01-S01 | fitted-c | 3 | 5.966 | 1347 / 1519 |

The location bias persists: S01 stays roughly 6 km away; DS22 stays roughly
2.1–2.4 km away. Some fitted members fail final screens. These fixed-family
Gaussian searches are exploratory; the earlier 1.895 km DS22 result remains
better under the accepted RF model. No <0.5 km result, whole-DS22 validation or
new independent position result for S02–S05 is established by this report.

## Validation and next evidence

65 focused tests pass for nominations, linear exclusion, fixed-label gates,
independent dense fits, RF-reference/hardware-feature separation and original
point binding. Default RF statistics are bitwise unchanged in the synthetic
oracle and reproduced real-data control endpoints exactly. All handwritten
current sources pass Ruff. Source snapshots, numerical matrices, evaluations,
point IDs, source hashes and unchanged earlier seals accompany the report.
No new RF collection or QNAP mutation occurred.

The next useful position experiment is a nuisance-projected information audit
and then a common-position multi-scan fit with scan-local hardware. This should
test how much accuracy is lost to orbital phase, receiver drift and component
constants, before adding parameters or tuning on GPS. The three rejected phase
families can separately be examined for coherent curved subsets with explicit
clutter costs; their all-member failure is not permission to force them together.

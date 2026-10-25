# DS24: bounded recovery of two additional curved families

The existing support-aware control admits one new active curved model family
on each RF information-ranked scan: **49 RX1 CH5 observations assigned to
65500 on DS24-0095**, and **43 RX2 CH7 observations assigned to 57752 on
DS24-0087**. Both c arms pass the original physical/residual gates and preserve
every accepted parent observation and every active incumbent nuisance/mode
definition. These are model assignments, not independently verified emitter
identities. Geographic evaluation belongs to the separate evaluator and is not
used in this report.

Ordinary graph reentry rejects all seven whole-source combinations on each
scan. Its policy therefore remains the exact saved baseline. The support-aware
result is a separately named existing control, with at most two predeclared
failed proposals per scan; it is not merged with graph additions or the RX1
receiver-correction candidate. No native temporal paths, raw IQ processing,
new RF collection, stationary pooling or ALGO promotion occurred.

## Frozen population and evidence roles

Descending saved c=0 curved weak-axis scale, with case ID as tie-break, selected
0095 (0.971883476 km) and 0087 (0.928412460 km). This ranking is conditional
on the existing RF model and its fitted nuisance/noise state; it is not a
calibrated uncertainty ranking or untouched geographic validation. All DS24
geographic outcomes had already been examined in earlier work. The two-case
pilot is development evidence and does not justify a cohort accuracy claim.

The baseline is the saved fresh ALGO02-v1 plus qualified causal signed phase
prior and equal-assignment-prior family cavity under
`/srv/bulk/leo/research/ds25-20261024`. Inputs were reconstructed without
calling `ds24_engine.context()` or executing signed-prior position refits.
Source/input hashes, full target IDs, original-label controls and hypothesis
ordering were frozen before new recovery fits.

Counts below are identical in c=0 and fitted c. “Compatible” includes accepted
post-fit-only associations. “Position likelihood” is the disjoint unique union
of curved calibration and explicit predictive IDs. Both use the unchanged
original winning-GLRT denominator; there are no added native secondary peaks.

| Scan / separately reported policy | Compatible original GLRT | Compatible % | Curved calibration | Predictive likelihood | Position likelihood / GLRT | Likelihood % | Post-fit-only IDs | Active curved families |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0095 baseline / ordinary graph fallback | 2671 / 4050 | 65.9506 | 2262 | 0 | 2262 / 4050 | 55.8519 | 409 | 15 |
| 0095 support-aware control | 2735 / 4050 | 67.5309 | 2311 | 0 | 2311 / 4050 | 57.0617 | 424 | 16 |
| 0087 baseline / ordinary graph fallback | 3601 / 4401 | 81.8223 | 2957 | 644 | 3601 / 4401 | 81.8223 | 0 | 22 |
| 0087 support-aware control | 3665 / 4401 | 83.2765 | 3000 | 644 | 3644 / 4401 | 82.7994 | 21 | 23 |

Thus each control adds 64 compatible original observations, but only 49 and
43 enter curved calibration. The remaining 15 and 21 additions are post-fit
associations and do not enter position. Predictive likelihood membership is
unchanged. Every parent compatible ID and every parent likelihood ID survives.
Each newly active family currently has one receiver/channel owner; this does
not create a second geolocation station or establish independent cross-owner
support for that new family.

## What the unchanged gates reject

The three longest wholly unassociated actively curved sources per scan were
screened against the entire original causal catalogue, refining at most eight
identities including the original. The target source never calibrated its
nomination. Whole-source observations, aliases, other priors, masks and budgets
were matched between c arms, with no residual-based point trimming. All best
nominees in this pilot retain their original nominated identities.

On 0095, the 62-point RX2 CH2 source assigned to 66886 and the 49-point RX1
CH5 source assigned to 65500 have clean conditional residuals under the ordinary
three-orbit-mode layout, but their one-owner support fails the final support
rule. The existing support-aware control disables only each newly active
one-owner family's three shape coordinates, retaining its phase coordinate and
all protected incumbent definitions. The 65500 source then passes both arms.
The 66886 source instead shows structured residuals: fitted-c profile RMS
112.954 Hz, slope z=6.597, quadratic BIC gain=39.575, maximum step z=6.762 and
lag-one correlation=0.851. It remains rejected despite its RMS being below
450 Hz. Low RMS alone does not establish compatibility.

The other 0095 graph target, 40 RX2 CH5 points assigned to existing family
68382, triggers the original near-feasible constrained rescue: ordinary minimum
slacks are -0.0021203692 and -0.0077740502. After the original five rounds of
up to 40 constrained steps, the paired gates still fail. Retained sources can
fail structured-residual checks after the joint refit; low-frequency RMS does
not excuse losing their compatibility. Every ordinary and rescued endpoint is
saved separately. No extra rescue was added.

On 0087, the 43-point RX2 CH7 source assigned to 57752 passes individual
residual checks under ordinary graph reentry but fails its one-owner shape-mode
support rule. It passes the support-aware control. The separate 22-point RX1
CH8 source nominated to the same family fails the frequency residual gate even
after that simplification: fitted-c profile RMS is 1824.585 Hz. The 18-point
RX2 CH5 source nominated to existing family 64421 fails strongly, with ordinary
fitted-c profile RMS 2424.865 Hz and conditional mean about -8757 Hz. Adding
these sources together does not repair them. All seven combinations remain
in the original graph results; no 0087 constrained rescue was eligible.

## Frequency fit and conditional information

| Scan | c arm | Full curved RMS, baseline → support control (Hz) | Curved weak-axis scale, baseline → support control (km) |
| --- | --- | ---: | ---: |
| 0095 | 0 | 50.335935 → 50.772435 | 0.971883 → 0.897091 |
| 0095 | fitted | 50.169146 → 50.643690 | 0.964220 → 0.891557 |
| 0087 | 0 | 65.428736 → 65.010114 | 0.928412 → 0.877835 |
| 0087 | fitted | 65.367178 → 64.944785 | 0.923341 → 0.875979 |

The information calculation uses curved observations only, fixed selected
labels and fitted Gamma precisions, and nuisance-prior elimination. Position
derivatives agree at 20 m and 10 m steps. These scales are local model
sensitivities, not calibrated confidence intervals or achieved position errors.
Baseline and candidate endpoints/noise states differ, so the before/after
scale change is not a fixed-state causal decomposition of the added points.

At the support endpoint, removing the newly active family and reprojecting
nuisances reduces information along that endpoint's weak axis by
0.164739 km^-2 on 0095 and 0.129480 km^-2 on 0087 in fitted c. These are
fixed-position, fixed-noise, fixed-prior family influence diagnostics; no
family-deletion position fit was run. Family contributions are not additive,
and the saved residual-only directional derivative is not the derivative of
the complete marginal objective. Geographic accuracy must be assessed
separately from association percentage, frequency RMS and conditional information.

## Runtime, technical repairs and preserved controls

The two ordinary graph stages took 54.063578930 and 56.635566083 seconds.
The frozen stage caps remain 600 seconds for graph and 240 seconds for support
per case, one numerical worker with one BLAS/OMP/MKL thread, and an unchanged
1800-second overall pilot cap. All ordinary fits start independently at [0,0]
in the original 25 x 25 km box centered at 37.906, -122.545; the inherited
constrained rescue continues the ordinary endpoint and phase reference.
Ordinary recovery uses
five phase rounds x 48 steps; the original near-feasible rescue additionally
allows five x 40 under its original constraints. There is no budget reset.

Three technical/reporting corrections are explicit and versioned:

1. **Support replay context (`repair01`).** The fitter correctly used the
   original parent protection set, but the first post-fit reader recomputed
   it from an augmented mask and replayed a different model. Both original
   support stages failed that numerical check and retained baseline. Their
   first fitted pairs were not serialized before the exception; their errors,
   timings and failed policies remain immutable, and that missing endpoint
   detail is a provenance limitation. The coordinator authorized repeating
   only the original support proposals after an independent fixed-position
   precheck matched all eight case/proposal/arm objectives and designs exactly.
   Repaired arms are checkpointed before replay. Previously spent support
   time, 6.740075590 and 8.771051498 seconds, counts against the same caps.
2. **Dormant-coordinate eligibility (`eligibility02`).** The strict reader
   required every parent `supported` coordinate, including dormant nominees,
   to survive. That wrongly rejected the existing support control's explicitly
   permitted simplification. A symmetric no-refit correction on all four
   sealed support trials uses `parent.supported intersect original_protected`.
   It verifies that every disabled family is newly active with one owner;
   all protected phase/orbit/hardware/smooth/active-fragment feature definitions,
   original values, aliases, sigmas, RF, active IDs and phase priors are
   preserved. Original and corrected controls are both retained. The strict
   layout control remains baseline on both scans.
3. **Native CFO plots (`report_native03`).** The initial DBG01 figures mixed
   native scatter with alias-wrapped source CFO. Those six files remain only
   as explicitly superseded provenance. The replacement maps all 15,749 plotted
   source observations by canonical ID directly to native measured CFO/time,
   with exact zero coordinate differences. It breaks alias/gap connections,
   labels observed sources rather than polynomial predictions, highlights
   the recovered source, and separates compatible from likelihood counts.
   Residual and information outputs were unaffected. Both scans were visually
   reviewed after correction.

The support replay took another 31.820500211 seconds. Scientific active time
including the failed original attempt is 158.406606665 seconds; wall time from
the original scientific launch to repaired support completion is 412.277282031
seconds. Total support times, including the original attempts, are
21.640771643 and 25.604937631 seconds. No graph fit was repeated. The no-refit
eligibility correction and reporting do not add position searches.

There are 28 ordinary graph arm fits, two constrained arm refinements, eight
completed repaired support arm fits, and four earlier support arm fits repeated
because of the failed reader/checkpoint path. All statistical failures and
original stage failures remain visible. Twenty-six inference/adapter tests and
two native-report tests pass, including existing negative controls for shared
calibration covariance, whole-source original-label controls, incumbent mode
protection, alias preservation and tamper/no-overwrite behavior. The independent
recovery artifact audit passes with maximum replay objective difference zero.

## Artifact guide

- Original frozen sources, protocol and targets: `recovery.py`, `protocol.json`,
  `prepared_seal.json`, `<case>/parent.json`, `<case>/inventory.json`.
- Original ordinary/rescued fits and rejected nominations:
  `<case>/graph/`; original failed support stages: `<case>/support/`.
- Repaired, checkpointed support fits: `repair01/<case>/`; strict policies and
  scientific seal remain in that version.
- Corrected no-refit eligibility and separately named support policies:
  `eligibility02/<case>/result.json`, `eligibility02/scientific_seal.json`.
- **Primary DBG01 figures and coordinate CSVs:** `report_native03/<case>/`;
  use its `manifest.json` supersession list. Do not publish the old mixed-branch
  DBG01 figures as primary evidence.
- Residual CSVs/figures, both-arm curved information and family influence:
  `diagnostics_repair01/<case>/`, with `summary.json` and `seal.json`.
- Independent audit: `../audit/recovery_artifacts.json`, plus the original and
  repair preflight receipts. The evaluator adds geographic comparisons only
  after these RF results and eligibility decisions are sealed.

Direct raw-manifest access for these two recordings was unavailable in the
planning environment. No attempt was made to change access or substitute new
IQ. Further evidence or receiver/IQ interventions require their separately
frozen comparisons; this pilot does not combine them or expand to more scans.

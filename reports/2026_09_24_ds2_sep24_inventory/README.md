# DS2 Sep 24 inventory and leakage-free execution manifest

## Scope and evidence boundary

This is an analysis-first inventory of the complete on-disk **eligible** DS2
corpus for 2026-09-24 UTC.  It reads the sealed whole-corpus manifest, its 20
V14 tracking receipts, the DS2 quality tables, and the existing model registry.
It does not open IQ, contact the radio service, write QNAP, queue analysis, or
run a positioning model.  `manifest.json` is a compact, machine-readable
index of the same result.

The retained set has 20 completed, receipt-backed 300-s captures from
00:00:02.155440Z through 15:30:02.535971Z.  It contains 43,730 retained visits,
441 V14 tracklets, 12,694 tracklet observations, 319 candidate reviews, and
11,449 review observations.  Every included tracking product is complete,
schema V14, and has an individual receipt.  These are candidate-only products;
they do not constitute satellite-identity labels for a geographic model.

| Cohort | Captures | Joint ordinary model | Geometry/cone model |
| --- | ---: | --- | --- |
| `radio_pluto_19f2`, 15 MS/s | 1 | single-session only | conditional: 1 |
| `radio_pluto_19f2`, 2.5 MS/s | 2 | yes | conditional: 2 |
| `radio_pluto_5d4d`, 2.5 MS/s | 17 | yes | no capture-time binding |

The raw same-day inventory contains 22 captures.  Two completed captures,
`scan-fw-294be7850b76a34d` (01:02:55Z) and
`scan-fw-ff02a0ba4200d0dc` (01:10:11Z), cannot yet enter a DS2 model.  Their
local `/srv/bulk/leo` archives are sealed schema-12 variable-dwell captures;
all 2,217 and 2,219 declared chunks respectively are present, every file size
matches its manifest, and both receipts report zero device-dropped events and
qualified UTC timing.  They have no metrics product, queue job, or V14
directory.  This is a provenance/readiness exclusion, not a negative RF
result.  The earlier inventory also ended at a 15:43:30Z cutoff; the
receipt-backed set below is the later whole-corpus closure and is the
appropriate currently analyzable DS2 source here.

The missing analysis is an explicit software boundary.  Both captures carry
`AdaptiveHopReceiptV6`; the V14 precursor still attempts to validate that
receipt as `EdgeAdaptiveAnalysisBindingV4`, whose contract accepts receipt V2.
The reconciliation release at Git revision
`c528e9a2d01e0cc9329c479a6f7f5667920b4ec2` therefore deliberately skips V6
receipts before queue insertion.  A forced queue insertion would not be a
valid backfill: the deployed analysis workers at revision
`51701a6ba364bd20170cbc167c1ee0db8c640483` also cannot decode the schema-12
capture manifest.

A safe bounded backfill requires a new immutable V6 metrics binding and visit,
reference, manifest, presentation, and input-source variants, followed by
component tests for 120/240/360-ms visits and retained-index accounting.  The
runner must then separate its roots: read captures through
`AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)`, publish metrics to
a fresh report-local `AdaptiveHopAnalysisStore`, load them through
`ScannerTrackingInputStore(Path("/srv/bulk/leo"),
adaptive_analysis_root=output_root)`, and publish V14 through a report-local
`ScannerTrackingStore`.  Each invocation must keep the existing limits of at
most 2 metric workers, 2,500 visits, 560 seconds per slice, one session, and
560 seconds of tracking.  The current CLIs bind input and output to the same
`--bulk-root`, so there is no existing command that both produces the missing
products and confines writes to a new report area.  No backfill was attempted,
and neither `/srv/bulk/leo` nor `/mnt/qnap01` was modified by this audit.

## Scan inventory

`visits`, `tracks`, `track observations`, and `reviews` are copied from the
sealed quality/receipt products.  All rows are 300-s adaptive captures and
have RX0/RX1 tracking configuration.  `geometry` means an explicit
capture-time binding, not a radio-identity inference.

| Scan suffix (`scan-fw-`) | UTC start | Radio/rate | Visits | Tracks / observations | Reviews / observations | Geometry |
| --- | --- | --- | ---: | ---: | ---: | --- |
| f3ce5fe73aa40506 | 00:00:02 | 19f2 / 15 MS/s | 1,624 | 7 / 189 | 5 / 166 | LT3D-001A, conditional |
| 9f3d5067d149118e | 00:10:02 | 19f2 / 2.5 MS/s | 2,212 | 14 / 296 | 10 / 251 | LT3D-001A, conditional |
| cfcf667726e80735 | 00:20:01 | 19f2 / 2.5 MS/s | 2,221 | 12 / 295 | 7 / 245 | LT3D-001A, conditional |
| 8d1424f9297d34fb | 12:50:02 | 5d4d / 2.5 MS/s | 2,216 | 17 / 662 | 14 / 634 | unavailable |
| 573f6201b09f5ba4 | 13:00:02 | 5d4d / 2.5 MS/s | 2,217 | 17 / 393 | 13 / 351 | unavailable |
| d30c80bd75815223 | 13:10:03 | 5d4d / 2.5 MS/s | 2,217 | 17 / 547 | 13 / 499 | unavailable |
| b6659f13921e711b | 13:20:02 | 5d4d / 2.5 MS/s | 2,216 | 26 / 716 | 20 / 658 | unavailable |
| af33f52c96a606b7 | 13:30:02 | 5d4d / 2.5 MS/s | 2,214 | 13 / 373 | 8 / 326 | unavailable |
| 412a75e0665c8e93 | 13:40:02 | 5d4d / 2.5 MS/s | 2,213 | 20 / 578 | 12 / 491 | unavailable |
| 7fc0a2494f8caa5d | 13:50:02 | 5d4d / 2.5 MS/s | 2,220 | 29 / 1,052 | 26 / 1,012 | unavailable |
| 51dadc5c6aa0e74b | 14:00:02 | 5d4d / 2.5 MS/s | 2,216 | 15 / 426 | 8 / 364 | unavailable |
| 524e4ca2638f3601 | 14:10:02 | 5d4d / 2.5 MS/s | 2,218 | 27 / 757 | 19 / 675 | unavailable |
| 8634c361a1e38331 | 14:20:42 | 5d4d / 2.5 MS/s | 2,216 | 29 / 744 | 19 / 637 | unavailable |
| 3e1fe8de00bd8065 | 14:30:02 | 5d4d / 2.5 MS/s | 2,212 | 15 / 458 | 11 / 420 | unavailable |
| d8925d2a4c00a806 | 14:40:02 | 5d4d / 2.5 MS/s | 2,216 | 26 / 817 | 20 / 756 | unavailable |
| 12cb866cbc37adb9 | 14:50:02 | 5d4d / 2.5 MS/s | 2,215 | 30 / 896 | 22 / 818 | unavailable |
| 98fb8c5147c1c77b | 15:00:02 | 5d4d / 2.5 MS/s | 2,221 | 27 / 733 | 20 / 668 | unavailable |
| 32ebdbd20401472f | 15:10:02 | 5d4d / 2.5 MS/s | 2,217 | 31 / 842 | 23 / 755 | unavailable |
| b97ce25ed1ac630f | 15:20:02 | 5d4d / 2.5 MS/s | 2,217 | 33 / 906 | 25 / 825 | unavailable |
| d16389a0c7b4a70f | 15:30:02 | 5d4d / 2.5 MS/s | 2,212 | 36 / 1,014 | 24 / 898 | unavailable |

## RX and geometry availability

All 20 receipts bind the same V14 tracking configuration and dual-RX
processing, but only the first three 19f2 captures have an explicit
capture-time LT3D-001A authority.  It describes mount reference axes 20°
apart; it does **not** provide calibrated RF phase centres or boresights.  Its
RX0→negative-x and RX1→positive-x cable assignment is provisional.  Any
geometry, hard-cone, or fitted-cone calculation must marginalize both mapping
symmetries and treat the result as conditional.  The 17 5d4d captures must not
inherit that fixture from radio identity and are ordinary-Doppler-only.

## Proposed leakage-free DS2 manifest

Use all 20 completed sessions only as a development corpus.  Keep every scan,
its two RX streams, and its tracklets together in a single independent group;
never make chronological or within-track holdouts.  Before inference, freeze
the receipt digests, TLE/candidate-policy digest, reference-free prior, search
grid, rate/timing priors, group weights, candidate and exact-finalist budgets,
and a deterministic **whole-session randomized** outer partition (record the
seed and assignments).  Fit scaling/other preprocessing on the training groups
only.  Recompute candidate predictions at each location; saved review leaders
and any coordinate from another model cannot be labels or seeds unless declared
before the partition is examined.  Add the surveyed coordinate only to a
separate post-seal evaluator.

For joint ordinary positioning, use the two 2.5-MS/s cohorts separately or a
predeclared equal-whole-session combination with radio/sample-rate strata; do
not silently resample the lone 15-MS/s capture or let observation density set
session weight.  Cone diagnostics use exactly the three conditional 19f2
sessions and remain separate from the all-20 ordinary model result.

## Earlier-model matrix and reusable assets

| Family / registry models | DS2 role | Required gate or disposition |
| --- | --- | --- |
| Baseline Doppler; shared global receive time; causal per-NORAD rate; equal-weight joint multiscan | primary comparators | receipt-bound causal predictions; fresh candidate reassociation at every cell; exact SGP4 gate for rate variants |
| Regularized per-scan time; rate-aware joint screen; consistent cap-800; shared-NORAD rate; repaired common+session scale | conditional | freeze priors/matched controls; shared-NORAD only with measured overlap; guard/convergence checks for scale |
| Independent per-track time; soft identity mixture; robust residual rerank | diagnostic | retain unassigned component for soft mixture; do not promote timing-boundary or rerank outcomes to primary location |
| Learned pointing quantiles; fixed hard cone; staged full-FOV sweep; local fitted full-FOV cone | geometry diagnostic | only the three bound 19f2 sessions; both RX mappings; all-track unmatched penalty; local fitted sweep is secondary |
| Legacy joint-session L-BFGS-B | rejected | do not rerun; all earlier candidates failed convergence |

Existing reusable evidence is the final manifest/receipt index in
`../2026_09_24_ds2_final_manifest/`, the per-session quality tables in
`../2026_09_24_ds2_quality/`, the registry in
`../2026_09_24_ds2_model_registry/`, and the parameterized portable runner in
`../2026_09_24_ds2_portable_evaluation/` (`build.py`, `execute.py`,
`refine_joint.py`, `refine_joint_fine.py`, and `evaluate_postseal.py`).  The
receipt/quality adapters are `build_manifest.py` and `build_quality_report.py`
in their respective source packages.  The complete cone work is in
`../2026_09_24_ds2_geometry_cone_evaluation/`: full FOV 10/20/25/30/40/50/60/
70/80/90°, fixed half-angle 10/15/20/30°, and local fitted FOV
10/20/25/30/40/50°.  Reuse its receipt-bound RX-label join and mapping
marginalization, not saved candidate identities.

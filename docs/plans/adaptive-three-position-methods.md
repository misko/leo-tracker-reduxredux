# Automatic baseline, T1AT and V16 positioning

## Required delivered behavior

Every future adaptive scan must automatically acquire three separately visible
positioning results: the existing Sacramento baseline, T1AT/C0, and V16. Each
method must have a verified PNG in the recording detail WebUI, showing its
Sacramento search, selected estimate, evaluation-only reference, and horizontal
reference error. Missing scientific support must produce an explicit diagnostic
status and figure, never an invented position or a silently omitted method.

The user authorized implementation, tests, deployment, and merge to remote main.
No new RF capture is needed or authorized by this analysis change. Qualification
uses the existing on-disk recordings. The existing baseline remains published
independently of progress or failure in the added methods.

## Scientific protocol

- Additional IQ/GLRT refinement is **off**. Select the highest original margin
  candidate per passing physical window; tie-break by rank then candidate ID.
- The inference domain is Sacramento (38.5816, -121.4944), radius 250 km, altitude
  0 m. The reference coordinates are absent from inference contracts. Error is
  computed after selecting the result, using explicitly bound evaluation metadata.
- Reuse the baseline's 100/50/25/12.5 km best-first cell geometry. T1AT and V16
  have their own objective-directed priorities. Point and iteration budgets must
  be frozen in the eventual configuration; measured runtime informs those bounds.
- Every original top-one window enters every geographical score. Unassigned
  windows contribute clutter likelihood. Changing the number of scored windows
  between locations would invalidate the comparison.
- Bootstrap track shapes at trial locations, then fit receiver/timing/RF nuisance
  parameters there. No roof-conditioned calibration or satellite whitelist is
  permitted. A conservative horizon screen covers the entire prior disk.
- Regional bootstrap samples at most 12 observations per proposed track for
  initialization only. All windows enter subsequent likelihood fits. Overlapping
  orbit-blind tracklet proposals can share initialization rows; likelihood rows
  remain unique.
- C0 settings are sigma=200 Hz, detection budget=0.8, clutter=2, common timing
  sigma=10 s, relative timing sigma=1 s. V16 uses 125 Hz, 1.6, 0.5, 3 s, 0.15 s.
  Common timing is bounded to +/-10 s, total satellite timing to +/-20 s, and
  the RF coefficient to +/-5000 Hz/GHz. RF uses actual per-window frequencies.
- Full-data C0 calibration at promising regional hypotheses includes the small
  regularized, piecewise-linear receiver correction. Its knot grid removes
  constant and linear components. Convergence and receiver support are required
  before using that calibration for T1-AT discovery.
- T1-AT full-bank absolute timing discovery and greedy/replacement select a
  common fitted-c association at each retained hypothesis. Both final scores
  receive the same windows, candidate bank, and frozen receiver baseline.
- Every final score has fitted-c and c=0 arms with matched other priors, starts,
  observations, candidate sets, and budgets. This is a final-score ablation;
  upstream calibration/selection remain fitted-c and must be labeled accordingly.
- Continuous fits start in multiple distinct promising regions. Local domains
  must cover their parent cells, rather than reusing the research 4 km roof disk.
  Report local/prior boundary hits and checked stationarity separately from search
  exhaustion. A bounded best-first search is not a global-optimality certificate.
- Raw C0/V16 likelihood values are not cross-model accuracy metrics. Report
  frequency RMS, support, convergence, runtime, and reference error separately.

This is a versioned Sacramento adaptation. Historical research results were
conditional on known-roof calibration and associated-window selection. Mathematical
score parity does not establish regional-search accuracy or end-to-end parity.

## Implementation state (first increment)

Implementation branch: `codex/adaptive-three-position-methods`, based on remote
main `7b22e3fec3233ad23f1628771616dee6f56deda0`. It imports the tested opt-in T1-AT
implementation from `2fcacc87d` without changing its published V1 contracts.

Implemented numerical components:

- `contracts/regional_position.py`: truth-free observations, prior, orbit bank,
  and score definitions.
- `analysis/regional_position_score.py`: C0/V16 probability, parameter gauge,
  actual-RF ECEF Doppler prediction, and derivatives.
- `analysis/regional_position_fit.py`: bounded constrained fits and independent
  stationarity checks, including the zero-c constraint.
- `analysis/regional_position_search.py`: unit-neutral best-first cell search.
- `analysis/regional_position_bank.py`: bounded propagation and whole-prior
  conservative geometric screening.
- `analysis/regional_position_bootstrap.py`: trial-location shape bootstrap and
  shared receiver-line initialization.
- `analysis/regional_position_calibration.py`: converged full-window nuisance
  calibration and receiver correction.
- `analysis/regional_position_association.py`: location-independent T1-AT ports
  for full-bank discovery and shared discrete selection.
- `application/regional_position_inputs.py`: public-port input preparation from
  existing GLRT products, without opening raw IQ.

Validation evidence so far:

- Independent probability and full-gradient tests for both scores, explicit RF
  constraints, physical input validation, timing/disk bounds, support accounting,
  and calibration/association tests.
- The scalar search reproduces the baseline's cell-evaluation sequence under an
  identical scoring callback.
- All 64 archived N01-N16 C0/V16 fitted-c/zero-c objective checks agree within
  2.04e-10; posterior RMS agrees within 2.71e-11 Hz. These are fixed-state numerical
  checks on historical research inputs, not a new localization experiment.
- A bounded read-only replay of `scan-fw-4eaab4879fec576b` loaded 2,956 original
  windows, reconstructed 24 bootstrap tracks, and retained 846 regional orbit
  candidates. Input preparation took about 8 s and orbit preparation about 5 s.
  At Sacramento and the fixed (50,50) km trial point, bootstrap took about 1 s;
  both scores reached stationarity <=0.001 in about 1.5-2.4 s per fixed-point fit.
  No full regional result or production performance claim follows from two points.

## Remaining implementation and release gates

1. Compose the shared preparation, independent hierarchies, regional calibration,
   T1-AT association, and matched final fits. Persist configuration-bound cell and
   stage checkpoints so bounded workers resume without repeating completed work.
   Account for any branch-dependent receiver-correction penalty when comparing
   regional hypotheses; do not silently compare differently filtered datasets.
2. Add immutable result/manifest/status contracts and narrow storage ports, binding
   capture, original analysis, prior, TLE snapshot, inputs, and code/configuration.
   Keep all existing published baseline/T1-AT contracts unchanged.
3. Integrate prospective automatic queue admission and completion checks. Baseline
   publication remains independent. Cover every adaptive receipt family explicitly,
   including unsupported/insufficient evidence and missing prerequisite states.
   Historical replay/backfill remains separately bounded and deliberate.
4. Add per-method PNG rendering, read-only verified API routes, and automatically
   refreshing WebUI panels, including both RF arms and meaningful failure figures.
5. Run component-owned storage/API/UI/queue tests plus bounded real-scan replay.
   Verify actual PNG payloads, bindings, axes, score units, reference error, and
   browser display for all three methods. Measure memory/runtime under the chosen
   frozen work budgets, rather than assuming coarse-point timings extrapolate.
6. Create and attach a PR, run release-appropriate checks, deploy only the analysis
   and WebUI changes while preserving live worker fixes and capture services,
   verify automatic processing and all PNGs through the live API/WebUI, then merge
   to remote main and verify the deployed source against the merged revision.

At this checkpoint no new queue policy, API endpoint, WebUI panel, deployment,
remote push, or merge has been performed. The end-to-end goal remains active.

# Active goal checkpoint

The original goal remains active: satellite association over the new tracks,
DS22 association and position evaluation, <0.5 km error, and strong DSX01 results
with track merging. This iteration made concrete progress; it is not complete
or blocked. All scientific processes from this iteration have ended.

## Full original membership now evaluated

- All 68 adaptive products exported through the current same-repository public
  ScannerTrackingInputStore. No RF collection or GLRT re-analysis. All 68
  exports match the original sealed raw-manifest digests and UTC origins.
- Adaptive source rate is 10 MS/s. The pure adapter preserves hardware-counter
  gaps, within-visit offsets, probe midpoints, RF, channel and physical IDs.
  Graph lanes separate RX/channel/actual RF. Adaptive totals: 100,761 winning
  points, 80,977 Graph points, 3,367 Graph fragments, 3,309 hard components.
- DS22-137's later complete export contains fourteen segments, whereas the
  original seal contains four (2,048 windows). Initial full-set equality failed
  because the capture grew after the snapshot, not because its prefix changed.
  The original four digests match exactly. All 32 original index chunks were
  hash-verified; only their exact device-counter windows enter main totals.
  Those 2,094 processed receiver probes yield 948 winners and 861 Graph points
  in 26 fragments/components. The full extension remains under fast_recovered*
  and is excluded from original-corpus totals. No historical seal was changed.
- All 137 original entries completed eight matched fixed-site arms: grouping
  fragments/hard components × c0/fitted c × bias sigma0/1000 Hz. No failed or
  unavailable entry is silently dropped. Full totals: 344,794 gated winners,
  297,877 Graph points, 10,513 Graph fragments, 9,458 hard components.
- Native 1000-Hz bias, fragment admission plus lossless consolidation: c0
  35,305 points (10.24%), 1,850→1,689 groups; fitted c 35,278 points (10.23%),
  1,849→1,677 groups. All points and proposed identities preserved. These are
  frequency-compatible candidates, not authenticated satellite identities.

## Position and physical-model evidence

- Two response-blind adaptive pilots: first DS22-002 and most curved-point
  support DS22-058. Same uniform regional search, all Graph points, matched c
  budgets, GPS only after sealed fitting. Errors: DS22-002 5.861 km in both
  arms; DS22-058 4.750 km c0, 4.824 km fitted c. No pilot meets 0.5 km. Together
  with previous work, only three distinct DS22 entries have new blind regional
  position pilots; 134 remain unevaluated for position. DSX01 has one of five
  scans evaluated for blind position in this series, at ~5.8–6.1 km.
- Forty-eight diagnostic fits on DS22-001 / DSX01-S01: native versus
  RF-proportional component bias, c0/fitted c, two fixed scoring sites and three
  bounded UTC shifts. New RF bias is one Gaussian coefficient at 11.5 GHz,
  multiplied by each fragment's RF ratio. No component slope. Dense Gaussian
  covariance tests verify marginal quadratic/determinant. Neither carrier
  family nor allowed UTC bracket removes wrong-endpoint preference.
- A frozen-calibration cap sensitivity (150–900 Hz) also retains wrong-site
  preference. Do not relax residual gates or promote any fit gain as accuracy.
- Latest-vs-previous distinct causal TLE predictions differ substantially.
  DS22-001 compares 1,415 objects, DSX01-S01 1,656. Among fixed-site admitted
  candidate NORADs with both epochs, median position disagreement is 35.657 km
  and 7.050 km respectively. These are disagreement, not latest-TLE truth
  errors. Candidate NORADs remain unverified. All collections and epochs are
  causal. Original latest predictions were replayed against saved bank states.
- New orbit_phase_geometry separates orbital phase from receiver UTC: sample
  states at t+delta then rotate to Earth's orientation at observation time t.
  Zero delta exactly nests original geometry; circular-orbit tests distinguish
  a satellite phase error from a receiver clock shift. No phase correction has
  yet been estimated or used to claim improved position.

## Next scientific work

1. Implement a physically constrained per-NORAD orbital phase variable shared
   across **all** tracks assigned to that satellite. Retain shared per-scan
   RX/band offsets and small drifts, native alias branches and explicit carrier
   priors. Never grant independent phase corrections to each fragment.
2. Derive prior scales only from causal orbital information, not evaluation GPS.
   Successive TLE disagreement is a sensitivity proxy, not calibrated truth
   covariance. Keep c0/fitted-c observations, candidates, priors and budgets
   matched. Geographic initialization must remain blind to diagnostic GPS and
   states fitted there. Diagnose position/phase/hardware gauge and rank before
   claiming sub-km identifiability; compare actual held-reference errors.
3. The old baseline can retain seeded values for hardware groups with no
   observations (adaptive scans have only channels1–4). Such values are not
   measured calibration; a revised joint solver should fix unobserved drift
   parameters to their prior modes and exclude unsupported groups from
   confidence claims. Keep any corrected-model comparisons explicitly versioned.
4. Channel-dependent transmitter CFO corrections are another remaining physical
   hypothesis. The ION 2026 paper linked in the report motivates it but does not
   prove the mechanism in these data. Do not erase position information with
   unconstrained per-track polynomial or affine nuisance terms.
5. Complete broader position evaluation after the model has demonstrated a
   credible improvement on bounded pilots. The optional independent/joint-site
   scope question remains unanswered; individual work can continue. Any joint
   stationary-site analysis must state that assumption and keep scan calibration
   separate. No reference repository is a runtime dependency.

The report has complete case mapping, compressed frozen exports, exact sealed
membership projection, source snapshots, causal elements, figures and tables.
No production model was promoted. The full original objective is unachieved.

# Active research checkpoint

The satellite-association / sub-0.5-km localization goal remains active. It is
not complete or blocked. All scientific jobs from this iteration have ended.

The model has four independent scan-local offsets and four small linear drifts:
RX1 low/high and RX2 low/high. Only individually measured-curved fragments
calibrate. Linear fragments may be associated afterward. Native integer aliases
and a regularized whole-component constant bias remain; no component slope.

Completed work:

- All five DSX01 scans × zero / tight / baseline drift × c=0 / fitted c: 30
  fixed-site arms with matched points, groups, causal candidates, other priors
  and requested budgets within c pairs. Tight is sigma 0.5 Hz/s, bounds ±1;
  baseline is sigma 2 Hz/s, bounds ±5. These are hypotheses, not specifications.
- Compatible Graph points for c=0 zero/tight/baseline: 1,615 / 1,787 / 1,658;
  fitted c: 1,992 / 2,079 / 2,081, out of 18,338 Graph points. These hard-merged
  compatibility counts are not authenticated satellite identities.
- Offset/drift figures, tables and support counts. Scan 2 RX2 high has no
  qualifying curved support; scan 4 RX2 high has only one qualified curved
  component for c=0. Unsupported seeded parameters are not measurements.
- Exact diagnosis: supplied site scores much better than the former ~148-km
  DS22 endpoint, for full/subset observations and four/160 requested seeds.
  Neither diagnostic GPS nor its fitted state seeds the subsequent searches.
- Cached geometry agrees with original to ~1e-8 Hz; measured geometry queries
  are 4–5 times faster. An 81-point grid, three basins, all original points and
  eight full-budget finalists reduce DS22-001 error to 11.919 km (both c arms)
  with hard components, 11.987 km with fragments. Hard merges alone do not
  explain the remaining error. DSX01-S01 errors: 5.780 km c=0, 6.085 km fitted c.
- Initial DSX01 processes hit eight-minute limits. Hash-verified cached scores
  were replayed with unchanged policy and budgets. Both resumed fits sealed;
  a post-fit distance-call argument bug was corrected using the unchanged fits.
  The original footer is archived with the exact recorded source digest.
- A new read-only public-port probe loads DS22-002 adaptive inputs from the
  current same-repository publication checkout: 4,400 probes, qualified timing,
  four RFs, two receivers. This does not prove availability of all 68 adaptive
  inputs or bind them to the older sealed snapshot. The earlier report is intact.

Next distinguish hardware/transmitter/timing bias from candidate ambiguity.
Test native versus RF-proportional carrier bias with an explicit gauge and
matched c ablation. Qualify UTC authority and causal TLE error. Do not relax
residual gates or equate frequency fit with position accuracy. Bounds and
prior sensitivity undermine drift confidence; stable offsets are not intervals.

Inventory adaptive members through the current public ScannerTrackingInputStore,
then freeze observation/timing authorities, counter gaps, actual RF and IDs.
Preserve the full 137-member denominator. Reference repos cannot be dependencies.
The optional independent/joint-site scope question remains unanswered; any joint
experiment needs an explicit static-site assumption and scan-local calibration.

No RF was collected, QNAP mutated, or production model promoted. No scientific
job remains running. The 0.5-km goal and independent identity validation remain
unachieved. Next work can continue without user approval.

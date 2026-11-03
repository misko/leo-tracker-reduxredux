# Historical orbital-state forecast calibration, before DS11

Use only archive snapshots whose request and local last-write timestamps precede
the earliest DS11 capture by at least24hours. These timestamps are local evidence,
not independent publication attestations. Choose12 consecutive daily UTC centers,
ending at the last midnight at least48hours before that capture. At each center
select the latest eligible snapshot from each original provider at center-24h,
center and center+24h, then apply the original newest-per-object epoch rule.

For each center select at most256 STARLINK objects by SHA256(NORAD) order among
objects present in all three catalogues. Preserve missing counts. Propagate all
three element sets to the same center instant. The previous-to-current state
revision is the predictor; the current-to-later state difference is a reference
proxy, not actual orbit truth. Only strictly advancing previous/current and
current/later element epochs provide a calibration case; report all exclusions.
Unchanged later elements do not prove zero physical error.

The first8 centers and hash-even satellite IDs calibrate; the last4 centers and
hash-odd IDs validate. No radio residuals, station coordinates or DS11 geographic
errors enter. Training reference snapshots must be available by the first
validation center. This supplies both time and physical-object separation.

Test a single scalar multiplier of the previous revision, bounded[-1,1], with
the revision jointly limited to5km position and5m/s velocity norms. Fit the
scalar by robust position-vector error (soft-L1 scale1km). Compare zero correction
and full bounded last-revision repetition. Require>=5% lower validation median
and mean position-vector error than zero, a strict majority of source/window
wins, and no worse median velocity-vector error. Also report full-revision
control and all12 center summaries. No correction is promoted from DS11 errors.

Reference proxies can share systematic errors, contain maneuvers and have uneven
update cadence. A passing result would justify a separate bounded causal pilot,
not establish calibrated absolute ephemeris accuracy. No target-later orbit is
an input to causal positioning. Metadata/state propagation only; children<=90s,
at most three single-thread workers; no new RF collection.

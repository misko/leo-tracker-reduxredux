# Satellite-family influence and a broader blind DS22 pilot

This controlled expansion does not meet the position goal. Cold global
proposal generation remains unreliable; small residuals on a subset of tracks
do not establish the correct position. All ten bounded runs are complete.

## Conditional satellite influences

Fixed earlier blind c0 family assignments are used in both c arms. Every full
fit retains its complete curved population. Removing one satellite at a time is
an explicit tangent influence diagnostic, not a final estimator, a new holdout
policy or permission to discard difficult observations. The augmented Gaussian
solve refits nuisance terms with their priors; active bounds, volume derivatives
and nonlinear changes are excluded from the tangent interpretation.

S01's largest conditional influence is NORAD100320: deletion changes the local
step by1.30 /1.34km c0/fc. The next is57129 at0.77km. DS22-001's largest is
64020 at0.63 /0.58km, even though that family's RMS is only34Hz; it fails final
noise screens. Neither result identifies one satellite whose removal explains
the entire6.36km S01 or2.14km DS22 fixed-family error. Three component tests
verify the augmented solve against a dense oracle, nuisance-unit invariance and
invalid scientific weights.

## Fixed selection and causal inputs

The pilot selects **001,034,069,102,137** before its new searches: endpoints,
midpoint and adaptive-format entries adjacent to the quartiles. This covers
both capture formats; it is not a randomly selected untouched validation set.
The earlier DS22-137 sealed four-segment prefix is used, preserving the original
denominator948. No later extended capture enters these results.

Original prepared causal candidate banks are frozen durably. Selected elements,
collection times, epochs, RF metadata and observations are preserved. Rebuilt
expanded states reproduce every original bank state to1e-9km/km/s. Every
selected epoch and collection time is before its scan cutoff. A common explicit
phase sensitivity prior sigma1s /bound3s is used for all five scans. It is not a
calibrated orbital covariance, and differs from earlier successive-TLE-based
DS22-001 runs. The local archive is unreadable under the current user; no new
archive read or data collection is required for the verified frozen banks.

Each c pair has identical observations, candidates, radio-only starting offsets,
zero initial phases, other priors and geographic caps. Only measured-curved
fragments calibrate or rank states; linear tracks associate afterward. The
same four receiver/band offsets and small drifts (sigma0.5Hz/s, bound1Hz/s) apply.

The cold search covers a250km city-prior disk with125km spacing, then refines
three separated basins with equal ten-scale, four-neighbour budgets. Its cap
is133 discovery locations, followed by three exact finalists and up to12 exact
local neighbours. Discovery uses three hardware proposals; exact finalists
use eight and local neighbours four. Ground truth is used only after writing
each independent endpoint. These are bounded proposals, not proven global or
stationary optima. A component test verifies disk coverage, equal basin policy,
point deduplication and the cap.

## Actual results

| Scan | c arm | Error km | Associated / raw GLRT | Merged groups | Points/group |
|---|---|---:|---:|---:|---:|
| DS22-001 | c=0 |5.204|1594 /4039 (39.47%)|40|39.9|
| DS22-001 | fitted-c |22.556|855 /4039 (21.17%)|28|30.5|
| DS22-034 | c=0 |156.298|214 /1615 (13.25%)|8|26.8|
| DS22-034 | fitted-c |6.961|1057 /1615 (65.45%)|31|34.1|
| DS22-069 | c=0 |3.856|2331 /4138 (56.33%)|72|32.4|
| DS22-069 | fitted-c |247.269|422 /4138 (10.20%)|18|23.4|
| DS22-102 | c=0 |54.256|86 /1630 (5.28%)|3|28.7|
| DS22-102 | fitted-c |223.147|118 /1630 (7.24%)|4|29.5|
| DS22-137 | c=0 |203.285|247 /948 (26.05%)|5|49.4|
| DS22-137 | fitted-c |201.393|284 /948 (29.96%)|5|56.8|

Do not select only the best c arm per scan to claim robust accuracy. Many runs
settle far from the supplied position, despite frequency-compatible subsets.
Frequency-fit and position-accuracy effects remain separate. The earlier
1.895km DS22-001 local result remains better; no <0.5km or whole-137-scan
geographic validation is established.

DS22-069 c0's original process terminated with code143 after discovery and a
partial exact stage. Its terminal state was verified before an explicit resume.
The saved basin proposals were reused, not the regional discovery rerun. The
same exact stage was deterministically recomputed; input IDs and causal bank
are verified against the original protocol. This repeats computation but does
not expand the declared unique-proposal policy. Its reported elapsed_seconds
is the resumed stage only and must not be used as total runtime in a speed
comparison. Cause of the original termination is not established.

The large arm/basin disagreements suggest that hard whole-track noise gates
create a difficult cold proposal objective. This is a hypothesis for the next
experiment: use a smoother physical shape score for regional proposals and
retain strict original gates for exact final ranking and association. More
brute-force time or an in-sample score reduction alone would not prove accuracy.

The user's concurrent longest-track investigation is documented separately at
../2026_10_17_longest_unassociated_s01/. It finds a concrete phase-clipping and
family-membership issue and a231-point conditional compatibility gain at known
GPS, plus a pooled residual limitation. Those known-GPS findings did not seed
this blind pilot. Seventy focused tests and current-source Ruff checks pass.

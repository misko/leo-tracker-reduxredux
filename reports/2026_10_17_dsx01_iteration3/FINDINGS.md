# What the third iteration establishes

Frequency-width continuation now reaches 455/693 window associations, compared
with 434/693 for the expanded exact profile and 422/693 for its fixed-bank
starting point. Both continuation and expansion strongly restore seven windows,
but different sets. The new continuation loses more original full-scan support
and has only two strict raw endpoints out of five. It is a recovery lead, not
a validated overall improvement or a production candidate. All experiments
preserve the original observation denominators and do not choose a different
best method per window. The active recovery/generalization goal is not complete.

## Tighter timing alone is not a sufficient repair under this search protocol

The completed 60-receipt matrix consists of 40 new fits and 20 exactly bound
sigma-2 controls. Both fitted-c and c=0 have profile and continuation controls
at 1,000 complete-objective calls / 120 s, with orbit-projection counts separate.
The same original bank, observations, common 3 s prior and physical bounds apply.

| Relative timing prior | Fitted-c profile: window associations | Full-scan associations | Lost original full support |
|---|---:|---:|---:|
| 2 s | 422/693 | 13,784/20,084 | 742 |
| 1 s | 347/693 | 13,366/20,084 | 851 |
| 0.5 s | 339/693 | 12,302/20,084 | 1,177 |

Window 003 remains 0/27 in all three. A narrower fitted timing distribution
does not imply recovered evidence or better geography. Some endpoints exhaust
their allowances or remain nonstationary; these are bounded development
results, not a proof that all possible fits with stronger priors are inferior.
Total objectives differ between prior arms; likelihood and position are
reported separately in the [timing report](timing/README.md).

## Ephemeris choice matters, but does not repair a bad warm basin by itself

S02–S04 already used Space-Track; treating all originals as Hugging Face would
be incorrect. S01/S05 used Hugging Face elements, with matched-candidate median
element ages 18.96/26.75 h. Their latest causal Space-Track counterparts have
median ages 11.49/12.79 h. This is element age, not download age.

Holding candidate IDs, warm initialization, fixed band offsets and search
allowances unchanged, replacing those two snapshots yields 371/693 window
associations across all five recordings versus 422/693 for the original fixed
profile. S01 remains about 133 km from the configured reference. All four new
S01/S05 fitted-c/c=0 fits pass strict numerical audit. Better elements alone
do not force this warm optimizer into the appropriate geometry/calibration
basin. This experiment does not repeat end-to-end candidate discovery.

## Expansion losses are substantial changes in fit, not threshold flicker

Exact replay of original/fixed/expanded states shows:

- S01 fixed→expanded loses 314 assignments and gains 306. Only 12/314 lost
  points have a best-satellite-to-clutter posterior ratio between 0.8 and 1;
  278/314 fall below 0.5. Median absolute residual to their previous satellite
  grows from approximately 178 to 766 Hz. No previous satellite was removed
  or became invisible.
- In window 001, 35 assignments are lost and one is gained. The median lost
  point's residual to its previous satellite reaches about 1.1 kHz.
- S04 fixed→expanded loses 61 assignments and gains 124. Only five lost points
  are near threshold; median residual to their previous satellite increases
  from about 140 to 862 Hz. Again, visibility and candidate removal do not
  explain these losses.

Timing, common calibration and q change together. The geographic moves between
these particular fixed/expanded endpoints are small, so large residual changes
need not imply a large geographic move. Candidate-specific timing and shared
calibration adjustments can replace an entire supported trajectory. The
five-start complete-state/cross-state portfolio pilot does not improve the
fitted-c endpoints for S01/S04. Its full budget, branch failures and normalized
support metrics are retained in [support/README.md](support/README.md).

## Causal calibration has now been tested without a donor position

The public archive contains admissible, already-completed same-radio FAST
donors for S02–S05. Donor capture end and conservative completion timestamp
both precede target capture start. Hardware serial, sample rate, capture mode,
exact actual-RF map and stream family match. Generation tokens identify
separate acquisitions and are recorded rather than required to be equal.
Only learned band differences seed the fit; donor location, timings and
satellite identities are not transported. S01 has no admissible donor and
retains that unavailable status.

For the S03 early→late half split, matched 400-call donor/no-donor fitted-c
bootstraps both predict 237/1,994 held assignments. Both c=0 arms predict
248/1,994. Thus a causal donor seed does not fix the cold initialization.

A nine-point grid scaled only by the search-region radius, with training-only
calibration at every point, gives 242/1,994 held fitted-c assignments with the
donor and 226 without it at 1,000 total charged calls. Both endpoints remain
nonstationary. This is not a useful predictive recovery claim. Neither the
grid nor its ranking reads the configured station reference.

Older local-segment capsule evaluations are a different split: they remove
only 63/66 target probe groups from the 4,797-point S01 recording, leaving
training observations spanning its full duration. Their results cannot serve
as a matched baseline for withholding half a recording. A faithful original
production cold replay also includes substantial discovery work beyond the
final-fit objective counter; it requires its own bounded protocol.

## Additional GLRT peaks require a statistical model, not best-of counting

The original 20,084 winner groups contain 54,321 passed GLRT candidates. Under
the frozen fixed-profile fit, accepting any peak would increase apparent
window matches from 422 to 480. This is an opportunity diagnostic only and is
not included in recovery totals.

Window 003 illustrates the problem: its strongest-margin winners produce
0/27 associations; any-peak selection produces ten, but a deterministic
within-RX/channel time permutation produces fourteen. That does not support
claiming the ten as genuine recovery. Exact winner IDs, timestamps, CFOs,
assignments and residuals were checked against the frozen original inventory.
No peak was substituted and no model was fitted in this audit.

Next modeling work should marginalize a declared peak-identity variable with
normalized per-probe weights and an explicit clutter alternative. It must
retain the one-probe denominator, pay for the extra alternatives, reproduce
the original one-peak model exactly, and pass within-lane permutation and
held-data checks. It must not credit best-of-peak matches as recovered truth.
The alternative peak audit supplies evidence for testing this model, not
proof that it will improve localization.

## Frequency-width continuation finds additional basins, with tradeoffs

All five recordings now have matched raw continuation/annealing outcomes in
both c arms. Starting from the saved fixed profile, a 1000→500→250→125 Hz
schedule has an additional 1,000-objective/120-second allowance. Its matched
control spends that same extra allowance entirely at 125 Hz. Selection and
reported associations always use the unchanged 125 Hz objective; broader
intermediate widths are proposal aids, not the reported classifier.

For fitted-c, the matched control retains 422/693 window associations and
13,784/20,084 complete-scan associations. Width continuation reaches 455/693
and 14,173/20,084, with seven major windows rather than six. This adds 33 window
assignments and 389 complete-scan assignments relative to its matched control.
It nevertheless loses 1,037 original full-scan assignments, versus the fixed
profile's 742 or the expanded profile's 791. Three raw endpoints fail strict
KKT; separate finishing does not change hard memberships and does not qualify
the S02/S04 failures. Centred row arithmetic is tested separately in
[numerical/README.md](numerical/README.md), without changing scientific bounds
or acceptance thresholds.

The new strong-window set is 001/005/007/008/009/013/015, while expansion's set
is 005/007/008/009/013/014/015. Their union must not be reported as one eight-window
method. Window 003 remains 0/27. S05 configured-reference distance improves
4.71→2.75 km, but S02/S04 remain approximately 121/253 km away. There is no
validated geographic-generalization success.

These results justify three next controlled directions: width continuation
after generic candidate expansion; a normalized latent-peak observation model;
and a shared, constant-Hz satellite residual term with explicit shrinkage.
All three remain position-independent research hypotheses. They must preserve
the original winning-point evaluation, account for replaced support, and pass
predictive checks before any production change.

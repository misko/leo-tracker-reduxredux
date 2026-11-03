# Joint receiver association: implemented experiments, no promoted replacement

The user authorized completing and testing the design. [GOAL.md](GOAL.md)
records the full requirements and remaining work. The app goal is active.
The tested geometry variants fail their final positioning gates. The baseline
remains the default and the broader accuracy goal remains active.

The [extra donor eligibility audit](extra_donors/summary.json) now inspects four
chronologically selected earlier2.5MS/s recordings from the33 previously listed
candidates. Two match family0 and two family1 by exact RF/rate. All have64
retained trajectories,32 per receiver, and complete in under21seconds each.
Two selection tests and source/log bindings pass. This opens a way to address
the two acquisition settings missing separate calibration support while the
antenna altitude question is pending. Orbit support and analysis availability
still require verification; these are not yet calibration-ready donors and no
accuracy improvement follows from their track counts alone.

The subsequent [availability audit](extra_donors/availability.json) binds their
public analysis manifests and records finalization20.2–21.4hours before DS11.
Pinned orbit requests satisfy the505second guard, and file-write timestamps
precede the respective donor captures. These are recorded completion/file
evidence, not independent attestation. The [numerical export verification](extra_donors/numeric-summary.json)
passes all eight bounded track/bank jobs:64/61/58/58 numerical tracks and2995
candidate-track slots. Every bank has finite arrays and matches the expected
provider snapshots and observation digest. Four component tests pass; maximum
worker time is56.01seconds. Next is timing/source-geometry inference followed
by testing the frozen family0/1 receiver coefficients on these distinct donors.
No new coefficients or DS11 positions have been fitted yet.

The [frozen receiver-coefficient transfer](extra_donors/transfer-summary.json)
now passes on all four additional donors. All12 timing starts qualify at the
fixed N23 calibration location. Qualified training identities pass orbital
bank replay, and the original family0/1 receiver coefficients are scored
without refitting. Signed geometry beats receiver-only, elevation-only,
receiver-swap and within-RF permutation controls separately on each record:
source/RF wins are34/43,31/40,29/41 and27/35 (121/159 total). These are
distinct-record conditional retention tests; inferred labels are not decoded
IDs and some validation records precede the original coefficient-fitting
record. Six tests and568 recursive source bindings pass. No DS11 position has
changed. This permits a bounded positioning pilot for the two settings while
the full physical absence/clutter model remains uncalibrated.

The resulting [2.5MS/s positioning pilot](two5_position/summary.json) now fails
both family gates. All24 bounded starts finish, producing qualified selections
for10/12 model-record cells. Relative to the contemporaneous Doppler control:

| Setting | Record | Doppler error m | Receiver-informed error m |
|---|---|---:|---:|
| Family0 | Original15 |1360.9|1221.8|
| Family0 | Original30 |8308.8|7549.4|
| Family0 | Additional11 |6034.9|6052.3|
| Family1 | Original24 |5930.8|5791.0|
| Family1 | Original31 |8130.5|8359.1|
| Family1 | Additional9 |Unqualified|Unqualified|

Family0 wins2/3 but fails the median and separate-record requirements. Family1
has mixed errors and incomplete qualification. Original IID was also
unqualified on additional9; its absence is preserved rather than removed from
denominators. The six preflights verify exact-partition score parity to3.7e-12,
gradient parity to4.3e-11, and derivative discrepancies below5.7e-6. Four tests
pass. Selections were sealed from training score before geographic evaluation.
Neither setting is promoted. All eight acquisition settings now have conditional
receiver transfer evidence and geographic pilot coverage; the pilots have not
established a dependable replacement. This does not complete the full physical
absence/clutter likelihood or the accuracy goal.

`phase_gap/` tests the missing unanchored-source timing evidence, using only
existing DS10 donors16/17. A common quadratic clock per inferred satellite/RF
fits early training detections and predicts later held detections across both
receivers and fragments. All37/35 eligible groups qualify. The donor16 learned
tolerance is19.486us, exceeding the frozen1%-of-frame ceiling13.333us. At that
tolerance, donor17 median group hit rate is60%, below the80% requirement, versus
92.3% on donor16. Median evaluation gaps are6.54/8.06seconds, with maxima19.25/
91.71seconds; three shifted-phase controls have zero median hit rates. This
fails feasibility without changing any tolerances. It does not support using
phase extrapolation to declare source absence when neither RX retains an
anchor. Three tests cover wrapped extrapolation, held/late-training isolation,
and insufficient support. No DS11 positions or raw absence labels change.

A matched-support diagnostic now compares separate fragment clocks at exactly
the same source-group time boundaries and held candidates. All53/47 supported
fragment fits qualify, covering37/32 source/RF groups. Median group error changes
5.98→13.88us on donor16 and4.34→3.08us on donor17, with15/37 and11/32 group wins.
This does not show a consistent gain from separating fragments. The coverage
audit retains17/63 unmatched held candidates with median phase error313/182us;
only0%/9.5% lie within the frozen tolerance. On donor17 these unsupported points
are typically later (median16.34seconds after the boundary versus5.94seconds
for supported points). Better scores after excluding them cannot establish
transfer across missing support. Five phase-gap component tests pass, including
fixed-mask isolation; the original feasibility gate remains failed. These
diagnostics neither establish the cause of discontinuities nor justify source
absence labels or position corrections.

The subsequent independent historical state-revision forecast is complete in
`../historical_orbit_forecast/`. Its time/object-disjoint validation reduces
median orbit reference-proxy error16.9%, but mean error only3.3%; it fails the
predeclared requirement of at least5% for both. The fitted coefficient0.8080
uses921 training cases and no radio or DS11 geographic errors. Validation has
396 cases from120 different satellites and234 wins. Later elements are proxies,
not independent orbit truth. No forecast correction is applied to DS11. This
closes this bounded predictor experiment without establishing causal position
improvement or changing the retained baseline.

The new `detection_evidence/` audit separates raw detection from track retention:
10,210 of 40,479 receiver views with passing candidates have no retained track
in the eleven pilot inputs. This is not a source-specific missed-detection rate.
Frame-epoch metadata provides a further association cue. On family2 DS10 donor16
training visits, the 95th percentile of absolute wrapped epoch difference for
inferred same-source pairs is 0.032408 microseconds. Frozen at that threshold,
donor17 held visits accept 351/379 inferred same-source pairs and 0/228 inferred
different-source pairs. Labels are inferred from Doppler, not authenticated;
pairs share candidates/windows and include duplicate waveform candidates.
This is an initial feasibility result, not independent-trial accuracy or a DS11
position improvement. Unknown ownership stays unknown. Three component tests
pass in the original census/epoch export; two additional calibration tests pass.

The subsequent `epoch_position/` pilot implements a finite timing log-ratio
factor, averaging duplicate-adjusted events within windows and across a track
pair, then limiting the total edge weight per track. Satellite assignments and
candidate ownership remain exact sums; no hard identity constraint is imposed.
Zero-factor score parity is 3.64e-12, gradient parity 1.62e-12; the real-data
finite-difference discrepancy is 1.27e-6. Two component tests also pass.
All four family2 fits qualify, but both timing positions are unchanged from
Doppler: original0 765.072m, additional1 5972.687m. The frozen 5% improvement
gate fails, so the model is not expanded or promoted. Exact posterior diagnosis
finds all43 nonzero timing edges in each scan agree with original inferred
identities; maximum original-identity probability changes are 1.49e-6 and
2.90e-12 respectively. These measurements support timing as an association cue
without establishing a positioning gain. A distinct next hypothesis is whether
within-track frame-phase evolution supplies useful range-change evidence after
explicit clock-drift and phase-ambiguity treatment, first checked on DS10.

`frame_evolution/` now audits all59/62 selected donor16/17 tracks using integer
device-counter arithmetic and fractional epochs. All training-only robust clock
fits qualify. Direct approximate range/c plus a linear clock term performs worse
than clock-only: median track held absolute residual12.059 versus6.123us on
donor16 and9.186 versus5.125us on donor17. Reversing range curvature gives0.742
and0.605us, while an unconstrained per-track quadratic clock gives0.320 and
0.439us. The projection code adds epoch offsets to sample positions, so that
inspected stage contains no sign reversal; transmitter timing behavior is not
established by this check. Source-pooled curvature regression learned only on
donor16 gives orbital coefficient-0.845 and common curvature-0.0163us/s².
On donor17 its median curvature residual is0.01695 versus0.01870us/s² for a
constant-clock-curvature control, a much smaller advantage than the raw sign
comparison suggests. This is exploratory evidence with correlated, inferred
source labels and approximate propagation, not a calibrated ranging observable.
No phase-based DS11 position model is promoted. Further clock/source controls
must establish transferable information before treating phase curvature as
orbital range. Three component tests cover arithmetic, training isolation and
synthetic phase/curvature recovery.

`phase_transfer/` extends the frozen curvature test to five further acquisition
settings using ten metadata-selected DS10 recordings. All exports complete in
under25seconds each. Every family beats both its calibration-derived constant
clock-curvature control and its median cyclic source-shift control on a separate
validation recording by the specified5% margin. This supports a source-related
phase cue, but the local position sensitivity is weak: the measured calibration
scatter gives optimistic fixed-nuisance Gaussian principal standard deviations
of15–335km across these settings. These are diagnostic calculations, not valid
position uncertainty estimates. They argue against assigning this cue enough
weight to fix kilometre-scale errors without further evidence. Three new tests
cover coefficient fitting, validation isolation and the curvature projection.

The next practical use of epoch timing is recovering detection evidence omitted
by track retention. `detection_evidence/raw-partner-audit.json` applies only the
already-calibrated family2 threshold to its two preselected DS11 records.
Original0 has446 retained candidates with a passing timing-matched opposite-RX
candidate absent from retained tracks; additional1 has443. These span408/412
windows respectively. They are candidate counts, not verified new satellite
links or independent events. A source-specific visibility model should account
for these raw detections and timing false matches before interpreting an absent
retained track as receiver nonvisibility. The dedicated duplication test passes.

`raw_visibility/` now calibrates the probability of an opposite-RX raw epoch
match conditional on one retained anchor, using a deterministic unique anchor
per inferred source/window. Donor16/17 yield2282/2108 events, including510/356
raw-only matches. Fixed phase-shift controls produce zero matches, while51
training events have partners with conflicting inferred source ownership; zero
shift matches therefore do not establish zero real false-association probability.
The empirical model retains this uncertainty rather than asserting physical
visibility. Source-balanced signed geometry beats receiver-only, elevation,
RX-swap and source-permutation controls on donor17 held visits, with34/39 source
wins. Three component tests cover duplicate anchors and normalized likelihoods.

`raw_position/` implements an exact-assignment source-average geometry log-ratio
factor with those raw detections, candidate ownership and the same anchor rule.
The zero-factor parity check is3.64e-12 in score and1.62e-12 in gradient; the
finite-difference discrepancy is1.27e-6. Two source-subset tests pass. All four
family2 position fits qualify, but original0 error changes765.072→765.216m and
additional1 changes5972.687→5974.112m. The frozen improvement gate fails. This
conditional event model is not a complete visibility/clutter process and is not
promoted. Increasing its weight from the DS11 errors would be unsupported.
The next distinct hypothesis is whether frame-phase residuals predict
source-specific Doppler errors on earlier recordings, using independent
recording and source controls before any joint timing/frequency position fit.

`phase_doppler/` tests that hypothesis on all six earlier acquisition-family
pairs. Twelve bounded metadata exports and all six coefficient fits succeed;
none passes the frozen transfer gate. Validation median slope error changes
7.700→7.636,6.525→6.499,4.709→15.592,6.097→7.704,9.415→16.341 and
5.010→5.415Hz/s for families2–7 respectively. The first two small gains fail
the5% and control/source-win requirements; the other four worsen. No phase-based
Doppler correction is applied to DS11. Two tests verify training isolation and
fixed calibration coefficients under changes to validation responses.

The separately authorized offline orbit comparison is now frozen in
`../offline_orbit_pilot/PROTOCOL.md`. Its source-bound selection chooses original
indices22/23, the earliest scans with newer archived element epochs affecting
training-supported identities (21/20 tracks). Selection uses no reference errors.
This is a diagnostic of later orbit information, not a causal improvement claim.
The original state replay is now exact for both scans. All eight fixed-start
fits qualify, with no retries. Training-score selections were sealed before
geographic scoring. Offline error changes2812.785→2898.242m on22 and
3578.736→928.700m on23. Held Doppler log scores improve137.561 and100.555nats.
Four/eight MAP identities change, including four/seven initially>=.99 confident
assignments. These remain inferred identities, not authenticated corrections.
Replacement snapshots were requested about3.48/3.25hours after capture; no
causal availability claim is made. The reference is still unsurveyed. This
demonstrates a substantial offline gain on one scan, alongside a loss on the
other, and leaves the primary causal goal active. The next mechanism check must
separate changes in orbit states from changes in inferred identities before
designing another bounded causal orbit/association model.

That crossed mechanism ablation is complete in `../offline_orbit_ablation/`.
All16 fixed-label starts qualify, with training selections sealed before scoring.
For scan23, original states/original labels give3578.466m; original states/later
labels give3402.852m; later states/original labels give486.369m; later states/later
labels give920.371m. For scan22 the corresponding values are2794.696,2353.364,
3219.707 and2923.564m. Thus the large gain on23 survives retaining original
labels, while later labels alone make a much smaller difference. No cell is
promoted by geographic error, and later labels are not identity truth. The
fixed-label objectives differ from the earlier full candidate mixtures. This
supports independently calibrating bounded causal orbit-state corrections from
earlier archive history, rather than choosing another receiver-association weight
from these exposed DS11 results. Later TLEs would be reference proxies, not
surveyed orbit truth; all calibration information must predate each target scan.

## Implemented and tested

- Exact normalized marginalization over partial bipartite RX matchings. Every
  track can be unmatched or paired once; marginal probabilities retain ambiguity.
  A normalized matching prior prevents an arbitrary evidence reward from merely
  adding more matching configurations. Larger-than-budget components fail
  explicitly instead of silently pruning hypotheses.
- Shared physical-candidate identity factors for a pair, retaining separate
  profiled track CFOs. Candidate order is aligned by physical identity, not slot.
- Explicit ownership alternatives for acquisition candidates reused by tracks.
  Each observed candidate has one owner in a hypothesis. Alternatives are
  marginalized, with a stated uniform diagnostic prior.
- Normalized four-state receiver detection emissions with shared latent signal
  strength, unknown-view marginalization, nominal opposing boresights and a
  continuous-time two-state presence process. These primitives are tested but
  are not yet calibrated or connected to the DS11 objective.

All 34 unique component tests pass. Tests include brute-force matching and HMM oracles,
matching-score derivatives, permutation invariance, no-information parity,
probability normalization, physical identity ordering, missing-view handling,
quadrature convergence and held-data isolation in the presence filter.

## Real DS11 preparation and Doppler integration test

| Scan | Tracks | Paired opportunities | Possible track pairs | Reused acquisition detections | Doppler-only expected pairs |
|---|---:|---:|---:|---:|---:|
| 0 | 62 | 2218 | 42 | 2 | 17.9984 |
| 16 | 58 | 2217 | 42 | 1 | 15.9985 |

The public input join binds capture/analysis digests, exact receiver/RF/visit
and original track point IDs. Every retained track and paired opportunity is
present. Untracked raw candidates remain explicit and unidentified. Per-RF
ownership alternatives number 1/1/4/1 for scan 0 and 1/2/1/1 for scan 16.
Edges require common retained physical candidates and simultaneous training
support. This initial graph does not yet join non-overlapping temporal fragments.

Input preparation completes in 11.12s. The fixed-position Doppler integration
test completes in 2.81s, summing satellite, matching and ownership alternatives
at the original IID endpoints. Pair marginals satisfy both receiver exclusivity
constraints and ownership probabilities normalize on every lane. Its priors
are diagnostic rather than calibrated. Expected pairs are not verified source
identities. Because matching/ownership changes the objective, its absolute score
must not be compared directly to the old duplicated-track objective.

See [inputs](inputs.json), [Doppler pilot](doppler-pilot.json), [matching core](matching.py),
[receiver model](receiver_model.py) and the `test_*.py` files.

## Calibration support and next integration

A metadata-only inventory of the 24 existing DS10 numerical exports finds two
recordings matching both pilots' 5MS/s rate and all four exact RF centers:
`scan-fw-965c64b624fc1928` and `scan-fw-56e8d9636d969b28`. Both completed before
the first DS11 target; no reference error selected them. The other 22 exports
have incompatible rate/RF. This is not a census of all 187 DS10 captures.
See [calibration inventory](calibration-inventory.json).

Both donor exports now replay their original orbit states exactly. They contain
38 inferred satellite/RF sources each, respectively 59 and 61 confident tracks;
1 and 3 ambiguous tracks remain excluded. These are Doppler-inferred labels,
not verified satellite identities. The fixed donor geometry comes from a pooled
earlier DS10 fit, so validation is conditional on that geometry.

## Frozen conditional geometry calibration

The first donor calibrates a normalized three-state receiver model conditional
on at least one source-specific detection. It does not infer satellite absence
from empty probes. The second donor provides transfer validation. On its 852
held detected opportunities, receiver-only/elevation/signed log scores are
-945.805 / -838.794 / -596.446. Signed geometry improves 27/38 source groups.
Frozen swapped directions score -1792.891; seeded geometry permutation -4489.026.
The declared conditional screen passes. See [protocol](CONDITIONAL_PROTOCOL.md)
and [calibration result](conditional-fit.json).

## Two-scan conditional position pilot

The calibrated factors are coupled to Doppler, satellite mixtures, exact RX
matching and raw-detection ownership. Full-objective derivative discrepancies
are below 0.00002; zero-receiver scores reproduce both Doppler pilots exactly.
All ten fit/control cells converge and qualify, in 11–22 seconds each.

| Scan | Original IID m | Joint Doppler m | Receiver-only m | Signed geometry m | Swapped m | Permuted m |
|---|---:|---:|---:|---:|---:|---:|
| 0 | 765.1 | 765.1 | 765.1 | 682.8 | 922.6 | 941.1 |
| 16 | 2153.1 | 2152.8 | 2152.8 | 581.2 | 468.3 | 2079.0 |

Distances use the existing **unsurveyed roof reference**. The signed pilot passes
its frozen primary gate; swapped geometry also improves scan 16, despite much
worse reception scores, so that position improvement alone does not demonstrate
correct directional association. Pairing posteriors are nearly deterministic
even without geometry. These results do not establish verified association
accuracy. See [position protocol](POSITION_PROTOCOL.md) and
[all pilot results and ambiguity diagnostics](position-summary.json).

The attempted eight-scan extension stopped at the input compatibility assertion
after preparing scan 4. It ran no extension fits: scan 8 has a different sample
rate and RF set. A census finds only indices 0,4,9,16,19,20 compatible among the
32 original scans. All four remaining compatible scans completed the frozen
extension. All 30 development model/control fits qualified. Signed geometry wins
5/6 versus joint Doppler, median 2401.3 to 1600.8 m, P90 5438.8 to 5358.6 m.
The four new scans improve median only 3067.3 to 2870.2 m, with 3/4 wins.
See [extension protocol](COMPATIBLE_PROTOCOL.md) and
[complete results](compatible-summary.json).

Physical identity marginals replay every fitted objective and normalize within
1e-8. The MAP satellite changes on 26 tracks across six scans; this is an inferred
change, not verified correction. See [identity audit](identity-audit.json).

**Separate confirmation failed.** Exactly one of the preexisting additional 12
recordings matches calibration. Signed geometry worsens its error from 5972.7
to 6136.0 m. Four of its five fits qualify; receiver-only fails qualification.
No promotion is supported, and the baseline remains retained. See
[confirmation protocol](ADDITIONAL_PROTOCOL.md),
[all confirmation results](additional-summary.json), and
[comparison figure](position-comparison.png).

## Time-correlated receiver states

The next calibration fits a normalized refresh process on three receiver states,
conditional on source detection. The fitted persistence is about 6–8 seconds.
Fitting each arm's timescale improves aggregate transfer score, but only 14/38
sources beat temporal receiver-only; that frozen gate fails. A distinct ablation
holding every arm to the receiver-only timescale (7.898496 s) passes the same
transfer gate with 28/38 wins. See [first temporal gate](temporal-validation.json),
[common-timescale protocol](TEMPORAL_COMMON_PROTOCOL.md) and
[common-timescale calibration](temporal-common.json).

The resulting position solver marginalizes held reception states through the
filter. Its zero-correlation limit reproduces independent scores within 2e-12
and gradients within 2e-11 on real DS11 inputs; full numerical derivative checks
remain within 6e-5 across the sequence fits and controls. Synthetic component tests additionally verify held-CFO
isolation and the complete objective derivative.

All 28 time-aware fit processes complete within 31 seconds, with 26 qualified
fits. Receiver-only fails optimizer qualification on development 19 and the
additional recording; all signed fits qualify. The signed model improves only
3/7 versus joint Doppler, median 2649.8 to 2628.4 m, mean 3313.1 to 3346.0 m,
and P90 6540.8 to 6519.9 m. The additional recording still regresses, 5972.7 to
5992.6 m. The win-count, median-reduction and additional-record gates fail.
This follow-up uses already inspected recordings, not a new blind holdout.
See [frozen position protocol](SEQUENCE_POSITION_PROTOCOL.md),
[complete results](sequence-summary.json), and
[both variants compared](sequence-comparison.png).

Across both position experiments, 63 bounded model/control fits execute and
60 qualify. No failed cell is silently retried or dropped. A good reception
likelihood does not establish better geographical positioning.

## Exact whole-source assignment follow-up

Calibration groups all tracks with the same inferred NORAD and RF. Three donor-0
groups and four donor-1 groups contain more than two tracks. The position model
only pairs one track per receiver; MAP assignments in the six development scans
contain respectively 6,3,1,1,4,2 repeated same-NORAD/RF/receiver groups. Thus
fragmented source handling differs between calibration and the original
bipartite positioning model. These counts are inferred hypotheses, not
independently verified emitters.

The [whole-source follow-up](WHOLE_SOURCE_PROTOCOL.md) removes that restriction:
one physical satellite/RF can explain any subset of compatible tracks. Every
original candidate is retained, and every raw observation still has one owner.
A conservative candidate-removal bound proved insufficient for direct assignment
enumeration (some components retain >1e16 combinations), so it is **not used**.
Instead an exact subset DP sums every assignment. The 16-track/66-satellite
benchmark matches independent evidence and derivatives within 5e-14. Toy tests
also enumerate arbitrary three-fragment groupings and verify gradients.

The initial six-cell pilot includes one 90s timeout. A verified equivalent DP
orders sources and drops only structurally impossible partial assignments;
it reduces complete-objective evaluation from 4.48 to .85 seconds on scan 0,
2.10 to .46 seconds on scan 16, and 2.05 to .71 seconds on the additional scan.
Score/gradient replay differences stay below 5e-12. Only the timed-out scan is
retried, from the same seed with the same cap; it completes in 14.43 seconds.
The timeout receipt remains intact. See [runtime protocol](WHOLE_SOURCE_RUNTIME.md)
and [exact replay](whole-source-speed-check.json).

| Recording | Original IID m | Whole-source geometry m | Qualification |
|---|---:|---:|---|
| Development 0 | 765.1 | 682.7 | Pass after equivalent-engine retry |
| Development 16 | 2153.1 | 581.2 | Fails optimizer qualification |
| Additional 1 | 5972.7 | 6136.0 | Pass; accuracy regresses |

The additional Doppler-only control also fails optimizer qualification. Four of
six cells qualify after the explicit continuation; the frozen pilot gate fails.
Whole-source grouping repairs the implementation mismatch but does not explain
the failed accuracy transfer. See [all results](whole-source-summary.json).

## Calibration coverage and availability repair

The [full acquisition inventory](acquisition-calibration-inventory.json) covers
all 32 original and 12 additional records, across eight exact rate/RF settings.
Six settings have distinct earlier calibration/validation donors, covering
28 original and 10 additional records. Both 2.5MS/s settings currently have
only one donor satisfying the conservative global availability cutoff; this
needs more donor support or a separately validated transfer model. No RF/rate
setting was selected using DS11 reference error.

**Availability caveat for the preceding receiver experiments:** donor geometry
came from the pooled DS10 N24 fit. All its RF captures precede the first DS11
target, but DS10 index 23 finalized at 1790686752093682239 ns, after that target
started at 1790686628132675049 ns. Orbit states remain causal, but these are
retrospective orbit-causal experiments, not proof of fully online calibration
availability. Prior artifacts are retained rather than rewritten.

A new [availability-correct geometry protocol](CAUSAL_CALIBRATION_PROTOCOL.md)
uses exactly the 23 captured and finalized earlier inputs. Its seeds come only
from earlier available N8 fits, not the N24 parameters. The first fit stops
with gradient .01887 and remains unqualified. A documented tighter-tolerance
continuation preserves the same model and qualification gates; it qualifies
with gradient .0001262 and derivative discrepancy .00001541, in 29.93 seconds.
See [original failure](causal-calibration-geometry.json),
[continuation protocol](CAUSAL_CALIBRATION_POLISH.md) and
[qualified calibration geometry](causal-calibration-geometry.polished.json).
No DS11 reference coordinates or observations enter that fit. Historical
software/model publication before capture is still not claimed.

The [acquisition-specific rebuild](acquisition_calibration/summary.json) now
exports all 23 available donors against the corrected geometry. All 862
donor/source groups pass the public point binding and orbit replay audit;
selected orbital states replay exactly. Two initial export-audit implementation
failures are preserved, and no failed export produced an accepted data artifact.
Definite receiver hits now override ambiguous ownership independently of
iteration order. Full-scan 00 and unknown states remain saved, without claiming
that an unassigned detection proves physical satellite absence.

The [frozen receiver screen](acquisition_calibration/CONDITIONAL_PROTOCOL.md)
fits eight acquisition-specific models. All 24 selected arm fits qualify.
All six settings with distinct validation donors pass signed geometry versus
receiver-only, elevation-only, swapped-RX and source-permuted controls:

| Sample rate / RF family | Receiver-only held score | Signed held score | Source wins |
|---|---:|---:|---:|
| 5 MS/s low | -951.6 | -600.2 | 28/39 |
| 5 MS/s high | -713.3 | -626.3 | 19/31 |
| 7.5 MS/s low | -1139.1 | -724.4 | 28/35 |
| 7.5 MS/s high | -1657.2 | -1222.9 | 54/72 |
| 10 MS/s low | -2865.2 | -1744.2 | 95/116 |
| 10 MS/s high | -2118.0 | -1464.5 | 68/86 |

Higher scores are better. These are correlated receiver opportunities under
inferred source labels and pooled donor training geometry, not independent
position trials. Coverage is 28 original and 10 additional DS11 records.
Both 2.5 MS/s families remain unvalidated; a metadata-only inventory identifies
33 other available 2.5 MS/s recordings whose exact RF and usable tracks remain
unchecked. No failed or unsupported setting is silently discarded.

All 39 unique component tests pass, including five new ownership/gate tests.
These rebuilt coefficients were then tested in an eleven-record position pilot
spanning all six validated settings. Selection was the smallest plan index in
each family/cohort, fixed before scoring. Every public observation join passed;
exact Doppler partition parity was within 4e-12 and the signed gradient audit
within 1.1e-6. All 22 fit processes finished under 90 seconds, but only 11
qualified: the others reported line-search failure despite small gradients.
Those failures remain failures under the frozen rules.

| Cohort | Original IID median m | Joint geometry median m | Wins | Original / new P90 m |
|---|---:|---:|---:|---:|
| Six original records | 2291.6 | 2472.1 | 2/6 | 3445.2 / 3667.5 |
| Five additional records | 2568.4 | 2577.2 | 1/5 | 5133.3 / 5277.3 |

The accuracy gate fails independently of the numerical qualification problem.
No selective retries, control expansion or promotion follow. See the
[frozen position protocol](acquisition_position/PROTOCOL.md) and
[complete results](acquisition_position/summary.json). Better receiver-state
prediction is not sufficient evidence for better positioning.

A separate [association-only experiment](association_only/PROTOCOL.md) tested
whether freezing the approximate receiver geometry at the original IID estimate
removes harmful direct angular gradients while retaining its satellite-identity
evidence. It uses the identical panel and unchanged qualification/accuracy gates,
with an optimizer gradient stop inside the qualification threshold rather than
chasing floating-point-scale improvement. Its estimates are plug-in inference,
not fully joint angular measurements. It also fails:

| Cohort | Original IID median m | Frozen geometry median m | Wins | Original / new P90 m |
|---|---:|---:|---:|---:|
| Six original records | 2291.6 | 2517.8 | 1/6 | 3445.2 / 3537.7 |
| Five additional records | 2568.4 | 2567.4 | 2/5 | 5133.3 / 5221.0 |

All 22 processes finish and 21 qualify. Original index 2 signed fails its
finite-difference audit (.02975 versus .02), despite optimizer convergence;
it is retained and not reclassified. The frozen emissions match the original
calibrated probabilities at initialization and remain identical under position
updates. The full-objective initial derivative audit is within 1.1e-6.
See [all frozen-model results](association_only/summary.json).

Thus suppressing direct receiver angular gradients does not recover accuracy;
the broader failure cannot be attributed solely to that mechanism. Next inspect
candidate posterior changes and ambiguity relative to the original Doppler
associations before introducing another likelihood variant. The two failed
experiments add 44 complete fit receipts with no timeouts or selective retries.
Full-source absence/clutter/activity likelihood remains unresolved, and both
2.5 MS/s settings still need validation support. The baseline remains retained.

Current verification: 43 unique tests pass across the scientific components.
Components run in isolated processes because a historical reference test imports
another module named `test_model`; combined discovery encounters a Python name
collision. See [test receipts](component-tests-04.json). This test-runner issue
does not reclassify any numerical fit failure.

## Exact posterior and persistence diagnosis

The [posterior diagnostic](posterior_diagnostic/summary.json) evaluates all
eleven saved records without fitting new positions. Its zero-valued derivative
probes preserve the original partition score and expected source count exactly
on all runs, and match exhaustive small-case marginals and entropy.
Of 668 tracks, 639 originally have Doppler MAP probability at least .99.

| Saved model | Original identity loses majority | Of those, original confidence ≥.99 | Expected different identities |
|---|---:|---:|---:|
| Doppler refit | 4 | 0 | 5.82 |
| Joint receiver geometry | 40 | 24 | 40.59 |
| Frozen receiver geometry | 40 | 24 | 40.42 |

These are changes in inferred probabilities, not verified satellite corrections.
All fit qualifications remain attached. The maximum per-track difference
between joint and frozen original-identity probabilities is .0812; their
majority-loss counts agree in every recording. Combined with the failed position
tests, this motivates checking repeated-evidence strength instead of adding more
direct geometry influence.

A [calibration-only persistence screen](temporal_acquisition/summary.json)
keeps the rebuilt emission coefficients fixed and fits one shared refresh
timescale per family from receiver-only training data. An exact constant-emission
likelihood integrates missing observations; unit tests compare it with the
normalized forward filter and numerical derivatives. No DS11 reference error or
position fit enters the screen.

| Family / setting | Fitted tau s | Independent signed-minus-null held score | Temporal signed-minus-null | Gate |
|---|---:|---:|---:|---|
| 2 / 5MS/s low | 7.83 | 351.41 | 1.79 | Pass |
| 3 / 5MS/s high | 10.13 | 87.00 | -1.63 | Fail |
| 4 / 7.5MS/s low | 4.95 | 414.70 | 5.92 | Pass |
| 5 / 7.5MS/s high | 6.86 | 434.25 | -8.56 | Fail |
| 6 / 10MS/s low | 11.12 | 1120.98 | 3.19 | Pass |
| 7 / 10MS/s high | 9.69 | 653.45 | 2.55 | Pass |

All six timescale fits qualify. Four pass all signed-geometry controls and
source-majority requirements; two fail receiver-only comparison and stay failed.
The comparison supports modeling dependence, but neither proves a physical
correlation mechanism nor establishes that the changed satellite labels are
wrong. The emission parameters were not jointly refitted with persistence.

The [time-correlated whole-source implementation](temporal_whole/PROTOCOL.md)
now integrates those calibration timescales and retains failed settings through
Doppler fallback. Its 22 fit cells all finish and qualify. Tests cover missing
windows, zero-tau parity, finite differences and exhaustive multiple-fragment
assignments. Real-scan zero-tau score/gradient parity is exact, and the initial
temporal gradient audit differs by 1.6e-6. All three fallback results exactly
match their refitted Doppler controls.

| Cohort | Original IID median m | Temporal policy median m | Wins vs refitted Doppler | Original / new P90 m |
|---|---:|---:|---:|---:|
| Six original records | 2291.6 | 2351.8 | 1/6 | 3445.2 / 3817.6 |
| Five additional records | 2568.4 | 2585.0 | 1/5 | 5133.3 / 5217.5 |

The [accuracy gate fails](temporal_whole/summary.json); no selective extension
or promotion follows. Additional index3 improves 613.0→226.8m, but that isolated
result does not offset the broader regressions. All fallback records remain in
the comparison. Full absence/clutter/activity support remains open.

The [temporal posterior diagnosis](temporal_whole/posterior-summary.json) finds
19 original identities losing majority probability, including 10 initially
at ≥.99 Doppler probability, versus 40/24 in the independent receiver model.
This must not all be attributed to temporal modeling: on the eight active
temporal records the comparable counts are 23→18 and 13→10; the remaining
reduction comes from calibration-selected fallback. These remain inferred
identity probabilities, not verified satellite corrections.

A [fixed-position ablation](temporal_whole/fixed-position-ablation.json) then
evaluates Doppler-only, receiver/RF-only temporal emissions and signed temporal
emissions at identical saved temporal-policy positions. Original identities
lose majority probability in 6, 16 and 19 tracks respectively. Among identities
originally at ≥.99 probability, the counts are 0, 10 and 10; the two receiver
models change the same ten identities. No positions are refitted in this test.
Thus these high-confidence changes arise from the receiver/source-grouping
likelihood even when angular evidence is removed, not from the position change
alone. That does not prove any changed identity is incorrect.

The next targeted ablation is a calibrated geometry likelihood ratio against
the receiver-only model, with exact Doppler parity when numerator and denominator
match. This tests geometric information without the same uncalibrated preference
for grouping fragments. It must be described as a likelihood-ratio/composite
experiment rather than a completed generative detection model, and must pass
the existing position gates before promotion. The baseline stays retained.

That [geometry-ratio experiment](geometry_ratio/PROTOCOL.md) is now complete.
It subtracts the full receiver-only sequence log likelihood from the signed
sequence log likelihood inside each source factor, preserving exact assignment
summation and calibration-selected fallback. Equal numerator/denominator models
recover Doppler score/gradient within 4e-12 on the real scan. Tests include
ownership alternatives, held scoring, multi-fragment enumeration and gradient
checks; real-scan derivative discrepancy is 1.3e-6. All 22 fits qualify and finish
within the 90s caps, without retries.

| Cohort | Original IID median m | Ratio-policy median m | Wins vs refitted Doppler | Original / new P90 m |
|---|---:|---:|---:|---:|
| Six original records | 2291.6 | 2291.8 | 1/6 | 3445.2 / 3466.9 |
| Five additional records | 2568.4 | 2570.5 | 2/5 | 5133.3 / 5158.3 |

The [accuracy gate fails](geometry_ratio/summary.json). Additional index3 improves
613.0→448.9m, but the full cohort result does not justify promotion. The stored
held score is a composite likelihood-ratio score, not a normalized predictive
density. All fallback estimates match their Doppler controls exactly.

The [posterior audit](geometry_ratio/posterior-summary.json) finds seven original
identities losing majority probability and none originally at ≥.99 confidence,
versus19/10 under the temporal receiver likelihood. Thus the ratio removes the
diagnosed high-confidence changes without establishing lower position error.
These are inferred identities, not authenticated corrections or a demonstrated
accuracy floor. Repeating the already-failed causal orbit-revision uncertainty
pilot unchanged would also not address this result. Full missed-detection,
clutter and source-strength/selection modeling remain unresolved; further work
should inspect those measurement assumptions rather than retune this failed
ratio policy on its reference errors.

Full-scan absence, explicit clutter/catalogue-other support, time-dependent
presence calibration and bounded shared orbit
corrections remain unintegrated. The present conditional solver must not be
described as the completed generative discovery model or as validated across
all DS11 acquisition settings.

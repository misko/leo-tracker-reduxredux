# Bounded timing search recovers additional CH5–8 candidates

On the sealed twelve-recording development panel, timing search produces
**182 continuity-compatible confirmations versus45for matched point prediction**.
For CH5–8 the counts are**86versus18**, including**23original-absent native
owners**. All288paired windows/576receiver cells complete with original
historical candidate parity. The known-signal and conditional-null screens pass
for timing search. These are provisional RF candidates for coherence and causal
association review, not new accepted Doppler tracks or evidence of better
position accuracy. No validation outcomes or positions are opened here.

## Paired natural outcomes

| Channel,96cells each | Original full20ms | Matched point | Timing search | Search new original-absent |
|---|---:|---:|---:|---:|
| CH1 | 47 | 13 | 47 | 3 |
| CH4 | 49 | 14 | 49 | 4 |
| CH5 | 16 | 6 | 21 | 7 |
| CH6 | 16 | 5 | 20 | 7 |
| CH7 | 21 | 2 | 22 | 2 |
| CH8 | 16 | 5 | 23 | 7 |
| All | 165 | 45 | 182 | 30 |

Point and timing search use the same earlier mode bank and same random native
confirmation partition. Point selects the best zero-offset mode on nomination
samples; timing search adds a fixed +/-256sample bank and fine refinement.
Both seal their selection before confirmation. Search has139paired gains and
2losses versus point; CH5–8 has68gains and0losses. The original full20ms detector
is a separately labeled baseline context, with different search/data exposure.
Search retains152original-pass owners and misses13, while adding30previously
absent owners. Its182marks must not simply replace the original165.

There are190raw pilot confirmations but only182compatible with the selected
earlier CFO width. The8incompatible broad-CFO discoveries remain separate;
3are in CH5–8. A strong pilot can belong to a different frequency/identity.
All123no-donor cells remain in the576-cell denominator. Per-receiver/channel
counts, all margins, selected modes and support are in recorded_cells.csv and
recorded_summary.json. No selection uses a satellite identity or GPS.

The30new compatible owners are mostly sparse-history recoveries:15selected
one-donor modes,9two-donor modes,3three-donor modes and only3five-donor modes.
Only14/30selected the original primary mode. Confirmation margins span
0.0521–0.5010 with median0.2390, so these are not merely marginal threshold hits.
This matters for the next mechanism test: a conservative primary quadratic
forecast addresses timing curvature and compute, but cannot be assumed to
replace the sparse multimode search opportunities shown here. No ad hoc hybrid
is selected. These descriptive counts use the frozen candidate manifest only.

![Paired channel results](natural_paired_channel_results.png)

## Why timing search helps; why splitting is not the main failure here

Archived candidate timing/CFO is used only after operational selection, as an
evaluation-only positive control. All165original-pass anchors pass a public
full20ms rescore;161pass on the random search group and161on the confirmation
group. Of the four confirmation failures, three have insufficient complete
pilot blocks under the guarded partition and one loses the0.025gate. All165
owned all-frame/public scorer parity checks pass.

This separates timing-prediction failure from lost split power on this selected
panel. The split does discard samples and can lose weak or boundary support;
it cannot be assumed equally sensitive on arbitrary signals. Nevertheless,
161/165archived positives survive confirmation here, while only45point
predictions confirm compatibly. The large point/search gap is not explained by
a blanket inability of split groups to detect these original pilots.

The fixed timing domain is retained without outcome-based adjustment. Earlier
heuristic timing widths exceed256samples in497/3187modes and281cells;
95selected modes have such a width.214800nomination evaluations are retained,
including incomplete modes, coarse/fine duplicates and boundary choices. The
cap truncates some earlier uncertainty; it is not a calibrated probability
coverage claim. A separate32trial out-of-domain control at+/-280samples yields
zero admissions and zero correct timing recoveries.

![Archived-anchor power and timing domain](oracle_power_and_timing_domain.png)

## Known-truth and false-confirmation controls

All240in-domain signal trials use independent later Gaussian vectors, both
pilot edges, timing errors-256/-97/0/+97/+256samples, true frequency rates
-2000/+2000Hz/s across0.354s, donor CFO errors-200/+200Hz, and zero-rate fallback
versus deliberately correctly propagated-rate mechanism lanes. Target-midpoint
CFO truth is evaluated at0.364s after the earlier reference; timing drifts
at+/-100samples/s. Correct-rate controls demonstrate mechanism, not natural
predictor calibration. All truth stays outside the estimator.

| Independent signal trials | Point admitted /80 | Search admitted /80 | Search CFO within100Hz /80 | Within500Hz /80 |
|---|---:|---:|---:|---:|
| Strong -12dB | 16 | 80 | 40 | 80 |
| Moderate -18dB | 16 | 80 | 39 | 80 |
| Weak -24dB | 16 | 80 | 35 | 80 |

Every search-admitted in-domain trial has correct timing within2samples; no
admitted strong trial has a CFO error exceeding1kHz. Point's16confirmed strong
trials are accurate within500Hz; its low unconditional recovery is a timing
availability failure, not evidence that all point frequencies are biased.
The retained443.892Hz frequency grid and donor-relative grid origin limit fine
accuracy:500Hzsuccess must not be read as100Hzprecision. No uncertainty weight
is qualified. Ratios are digital pilot/background power, not antenna SNR;
Gaussian controls do not reproduce recorded interference.

Conditional nulls cover1and8earlier modes, the entire timing bank and selection,
both edges,32independent later vectors per edge/exposure stratum:128total.
Both methods have**0/32pilot confirmations and0/32admissions in every stratum**.
Each exact one-sided95%upper bound is**8.937%**. Point/search union is also zero.
These satisfy the frozen practical exploratory screen, not deployment FAR,
all-interference validity or a576-owner family-wise guarantee. Intermediate
mode counts are not separately calibrated. The upper bound is deliberately
reported despite zero observed events.

Wrong symbol-roll controls have3/32raw pilot confirmations for each method,
but0/32compatible admissions. This illustrates why the broad CFO winner and
earlier continuity must be reported separately. Recorded background pilots
can be real signals and are not labeled false merely because they disagree
with an injected donor. All32wrong controls and32out-of-domain controls remain.

![Known-signal and null controls](known_controls_and_nulls.png)

## Ownership and candidate handoff

Random native frame intervals are fixed by earlier primary timing and a stable
source/RX/native-counter owner. The same partition applies to every mode and
timing location. A pilot block enters a group only when every native sample
and interpolation guard lies inside that group's interval. A redaction test
changes all confirmation samples without changing nomination or its receipt.
Final verification checks1008control/natural results, all receipts, exposure
caps, selected native support, checkpoints and historical parity.

The unchanged512bin GLRT frequency estimator remains open over its full broad
residual domain. Earlier CFO rate is propagated to each frame and returned at
the common target-midpoint reference. Timing advances the earlier start epoch
to midpoint, then uses the explicitly declared constant-epoch approximation,
at most2samples within the20ms window at the predictor's rate bound. There is
no donor posterior penalty, truth locking or new confidence calibration.

candidate_manifest.json retains all190provisional pilot discoveries, including
their compatibility class, authoritative native generation/source/IQ digest,
donor ranks/counters, rates/reference counters, selected search/confirmation
blocks and receipt hash. Block envelopes in raw outcomes are native offsets
relative to target start; the handoff additionally supplies absolute half-open
native confirmation counters. Alternatives on existing owners are not automatic
replacements. Multiple modes, RX sharing, targets with shared donors and the
search/point controls are not independent new observations.

The manifest is ready for root/validation to test distinct-time coherence,
curvature and causal all-catalogue association. Exactly zero independent points
or positions have been admitted here. Four time fractions per channel are an
opportunity screen; coherent follow-up and matched c=0/fitted-c localization
remain separate dependent work. All recordings have prior study exposure;
development results are not unseen-location validation or a500mclaim.

## Runtime, verification and reproduction

Eight component tests pass. Verification confirms all frozen sources unchanged,
576unique native owners,288complete per-window outcome checkpoints, all paired
candidate parity, all selection receipts and guarded disjointness. No failed
raw windows, skipped cells, new RF, QNAP writes, production edits or git mutation.

Signal/null/boundary/wrong controls take38.18/26.98/7.93/10.85s. Each raw shard
takes57.04–64.47s, summing735.80process-seconds with two workers (about6minutes
elapsed). The inherited timer around repeated old production-GLRT parity sums
403.18s; it includes comparison and background materialization. The remaining
332.63s combines raw source reading/verification, new scoring, source checks,
oracle diagnostics and output/checkpoint writes. Separate native-reader and
new-scorer timers were not recorded; no finer split is inferred. Every shard
stays below its580s alarm. No extra timing campaign is run for measurement.

Use the repository .venv Python with the exact historical source PYTHONPATH
and BLAS variables1. Run `python -m unittest -v test_timing_search`.
The frozen harness commands are `study.py signal`, `boundary`, `null`, `wrong`,
and `recorded --case CASE`; root's run_authorization.json binds the protocol.
Restricted inherited source access uses existing read-only sudo -n. Outputs
are exclusive: reproduce in a separate copy, preserving originals. The first
pre-final source/checkpoint freeze is retained as protocol_pre_final_v1.json;
no outcomes preceded the final amended freeze. Source/seal hashes, all compact
trial/cell tables, figures and candidate ownership are publication artifacts.
Full compressed outcomes and selection/checkpoint receipts remain immutable
locally under the artifact seal; no raw IQ is included.

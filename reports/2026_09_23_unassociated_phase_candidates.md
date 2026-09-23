# Unassociated candidates for simultaneous-source phase research

The August 25 continuous recording retains candidate material that its final
tracks do not represent. This does not yet establish a second physical source,
receiver-drift cancellation, or improved satellite association. The purpose of
this metadata-only audit is to determine whether a bounded phase experiment
has adequate independent source support before opening saved IQ.

The recording is `cap-20260825T010019-89c2889553e0`, stream-1, analyzed by
`capture-34471d9087a94ec1b043951350de3956` at 2.5 MS/s. The preceding
[availability audit](2026_09_23_phase_authority_status.md) found no simultaneous
two-branch support on RX0 anywhere in its 60 seconds.

## What the trajectory bank retains

RX0's saved pilot scan contains 2,400 probes with ten candidates each: 24,000
GLRT64 candidate rows. The raw trajectory bank accounts for all 24,000 and
retains five trajectories with 717 observations at 717 different probe starts.
Retained observations include ranks 0–9. No trajectory truncation is reported.
Thus an acquisition winner-only policy, a rank-prefix cutoff, or final top-track
truncation does not explain this particular result.

The persisted residual-Hough configuration digest is
`sha256:6887330b106358061560521e528bb5fe65706f1c9f7db25e53fbe12cb1bf39ff`.
The RX0 raw trajectory product digest is
`sha256:4c6ae5737fa96664e750ba3ff5e6fc6459570c13a785fac3551f402297c66247`.
The initial Hough uses a 227,272.727 Hz alias period, 2,500 Hz residual gate,
minimum point weight 0.5, minimum support eight, and minimum span/maximum gap
0.75 s. Its later residual proposal gate is smaller: half an intercept bin,
227,272.727 / (2 × 512) = 221.946 Hz.

The [trajectory adapter](../src/leo/analysis/starlink/trajectory_feedback.py)
supplies candidate CFO/score rows without timing-source groups. Within each
proposed line, [the line fitter](../src/leo/analysis/cfo_lines.py) selects one
candidate per timestamp by evidence weight and residual. It then removes nearby
modulo-CFO support over the extracted line's span. Different timing hypotheses
inside that frequency support can therefore be collapsed or removed together.
Frequency-separated lines can still survive as separate tracks; there is no
global one-track-per-probe rule.

This mechanism explains why candidate count and track count are different
quantities. It does not establish that a real second emitter was removed.
Multiple candidates can be aliases or alternative timing hypotheses of the
same waveform. Changing production tracking on this evidence alone would not
demonstrate better association.

## Raw-candidate screen

The [reproducible metadata screen](figures/2026_09_23_independent_phase/geometry-sensitivity/build_raw_candidate_opportunities.py)
uses the `positive_margin = 0.05` value in each receiver's persisted
trajectory-accounting configuration. This is a retrospective exact-minus-control
screen, not the original pilot-scan ingestion gate. It groups nearby hypotheses
by connected components requiring both ≤2 sample modulo-frame epoch separation
and ≤2,500 Hz modulo-alias CFO separation. This grouping combines existing
diagnostic tolerances; it is not a published source-deduplication contract.

| Screen across 2,400 probes | RX0 | RX1 |
|---|---:|---:|
| Candidates with margin ≥0.05 | 1,150 | 6,887 |
| Probes with at least one passing candidate | 835 | 1,919 |
| Probes with at least two passing candidates | 308 | 1,716 |
| Probes with at least two separated components | 11 | 583 |

Only six probe starts retain two components on both receivers: **3.775, 19.025,
25.900, 26.400, 28.200, and 30.850 s**. At all six, exhaustive one-to-one
component matching finds a way for both receiver pairs to meet the two-sample
timing diagnostic. The [results](figures/2026_09_23_independent_phase/geometry-sensitivity/raw-candidate-opportunities.json)
retain every passing member and both component matchings, including failures;
no nearest-CFO or favorable-phase pairing is selected. Multiple aliases within
a component remain unresolved.

This provides concrete saved-data opportunities for a small source-isolation
experiment. It does not yet prove two emitters, a common receiver CFO between
the pairs, or temporal persistence. The six probes are isolated and cannot be
treated as a continuous phase arc. A future replay must use these outcomes as
discovery information and freeze its qualification protocol before inspecting
phase responses.

## Qualification boundary

Any candidate grouping below is a phase-blind diagnostic, not a satellite
identity label. A replay requires consistent one-to-one receiver matching,
separate known-pilot support, explicit carrier aliases, and common-time phase
references. Training and held data must use seeded random whole groups with no
overlapping sample support. Receiver calibration remains unverified, and a
short local phase result cannot by itself establish an orbit or position.

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

## Receiver-frequency consistency

The [closure enumeration](figures/2026_09_23_independent_phase/geometry-sensitivity/raw-candidate-cfo-closures.json)
retains all 71 timing-compatible candidate-member combinations. For each it
computes `dA = f1A − f0A`, `dB = f1B − f0B`, and closure `dB − dA`.
No nearest-frequency combination or per-probe alias is selected.

| Probe time (s) | Member combinations | Full-alias-wrapped closure range (Hz) |
|---:|---:|---:|
| 3.775 | 3 | +321 to +557 |
| 19.025 | 3 | −217 to −164 |
| 25.900 | 10 | −741 to −90 |
| 26.400 | 3 | +268 to +461 |
| 28.200 | 20 | −137 to +757 |
| 30.850 | 32 | −324 to +244 |

Wrapping at half the native alias period gives the same ranges. Raw closures
still differ by large alias shifts; the artifact preserves them. These ranges
are spreads over discrete candidate hypotheses, **not confidence intervals**.
The archived estimates do not supply the independent error model needed to
declare a statistical common-offset pass. The metadata is compatible enough
to motivate a bounded source-isolation replay; it does not resolve receiver
phase drift or prove shared-source identity. The [builder](figures/2026_09_23_independent_phase/geometry-sensitivity/build_candidate_cfo_closures.py)
binds the input artifact hash and needs no IQ access.

RX0's minimum source-component CFO separations modulo the native alias are
approximately 60.716, 30.738, 75.320, 75.181, 74.578, and 73.550 kHz in the
same time order. These six surviving pairs are outside the 2.5 kHz initial
Hough gate. Consequently, the general possibility of merging close-Doppler
signals described above is **not evidence that it caused the loss of these
specific six pairs**. Their isolated support must be investigated separately.

## Required source-isolation replay

Single-template correlations cannot establish that a weaker candidate is
independent of a stronger waveform. A useful next replay must fit both known
pilot templates jointly on the same saved mixed IQ, record their Gram-matrix
conditioning, and measure each template's incremental held response beyond the
other. Fixed rolled-pilot, wrong-carrier, and swapped-epoch controls must receive
the same fitting opportunity. Alias representatives, masks, and any timing
transport must be frozen using training data before held responses are read.

Random whole groups must share the same assignment across both sources and
receivers and have disjoint underlying sample support, including guards for
template and filter boundaries. Each source keeps its actual pilot epoch;
two-source differencing at different epochs requires supported transport with
uncertainty rather than silently assuming simultaneous receiver phase. A local
source-isolation pass would justify studying phase further, not an orbit or
receiver-position claim.

## Qualification boundary

Any candidate grouping below is a phase-blind diagnostic, not a satellite
identity label. A replay requires consistent one-to-one receiver matching,
separate known-pilot support, explicit carrier aliases, and common-time phase
references. Training and held data must use seeded random whole groups with no
overlapping sample support. Receiver calibration remains unverified, and a
short local phase result cannot by itself establish an orbit or position.

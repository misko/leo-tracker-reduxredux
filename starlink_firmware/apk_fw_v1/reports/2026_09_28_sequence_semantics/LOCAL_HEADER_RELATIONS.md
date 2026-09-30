# Held-out search for relationships between header positions

The changing header signs reproduce between receivers, but the strongest
pairwise relationships selected on early frames usually do not persist on later
frames. One candidate warrants further diagnosis; it is not a decoded field or
an established parity constraint.

`local_header_relations.py` uses the six qualifying cached visits and the
discovery/evaluation splits from `local_header_recovery.json`. Input cache hashes
are checked. For each visit, RX0 discovery frames select coordinates with
20–80% positive signs and the single pair having the strongest absolute centered
correlation of `real(z)/abs(z)`. The pair and its polarity are frozen before
evaluation on later frames, both receivers, and both cross-receiver directions.
There is no evaluation confidence gate or reselection. Only symbols 2–7 and
the intersection of available native carrier bins are searched.

| Visit | Discovery pairs searched | Discovery absolute correlation | Later RX0 oriented correlation | Later RX1 oriented correlation |
|---|---:|---:|---:|---:|
| S01 | 820 | .734 | −.053 | .413 |
| S02 | 990 | .701 | .072 | −.243 |
| S13 | 8,256 | .954 | −.169 | −.673 |
| S22 | 6,328 | .938 | .395 | .813 |
| S23 | 5,253 | .764 | .218 | −.203 |
| DS9-middle | 4,465 | .736 | −.328 | .006 |

The table demonstrates why large discovery correlations alone are insufficient:
thousands of pairs and short discovery sequences produce compelling accidental
matches. “Oriented” means the discovery polarity is applied; negative values
therefore contradict the selected relation.

## S22 candidate and transfer check

The S22 pair is OFDM symbol 2, native FFT bins 498 and 503, with equal polarity.
On 16 later frames, RX1 signs agree 14/16 times (87.5%), compared with a 53.1%
baseline from the marginal signs. RX0 agrees 11/16 times. The two cross-receiver
soft correlations are .425 and .542, so the effect is not confined entirely to
RX1, but it is much stronger there.

The exact coordinates and polarity were also evaluated in every other qualifying
visit covering those bins, using their reserved evaluation frames:

| Target visit | Frames | RX0 correlation | RX1 correlation | Cross-receiver correlations |
|---|---:|---:|---:|---|
| S13 | 10 | .139 | .879 | .376, .495 |
| S23 | 21 | .026 | −.111 | .061, .016 |

In S13, RX1 signs agree 9/10 times against a 50% marginal baseline. In S23,
the signs are predominantly positive, so 66.7–81.0% agreement across comparison
directions is not evidence of a strong relation: the corresponding independent
sign baselines are already 69.2–75.5%.

This candidate is inconsistent across visits and receiver strengths. Possible
explanations include a conditional signal structure or correlated calibration
error; no explanation is established. It does not justify merging these positions
as copies of one bit. The other five selected pairs also do not provide a stable
decoding rule in this test. More complex codes are not excluded by a pairwise test.

The detailed ignored `local/local_header_relations.json` contains all six
selected pairs and all 14 possible cross-visit transfers, not just this candidate.
It includes exploratory RX1 frame-permutation reference values. Those assume
exchangeable frames, do not account for temporal dependence, and must not be
interpreted as proof of coding; six candidate visits were examined. S22's nominal
value is .003. No frame-permutation value is used to assign bit meanings.

Two synthetic tests verify selection and held-out recovery of an inverted copy,
failure when that relation is removed, and exclusion of constant positions.
Tests and Ruff checks pass. No raw observations were added to Git and no new
recordings or downloads were made.

## Follow-up: common-phase diagnostic

`header_common_phase.py` estimates each frame's common phase from other carriers
in symbol 2. Reference carriers must have discovery mean unit-phasor magnitude
at least 0.5; bins 498 and 503 are always excluded. Reference phases and carrier
selection are frozen from discovery. The estimate is then applied to both target
carriers on evaluation frames. This is an exploratory diagnostic, not a change
to the native decoder or to the raw data.

| Visit / receiver | Other reference carriers | Correlation before | After common-phase removal |
|---|---:|---:|---:|
| S13 / RX0 | 9 | .139 | .361 |
| S13 / RX1 | 6 | .879 | .725 |
| S22 / RX0 | 8 | .395 | .495 |
| S22 / RX1 | 4 | .813 | .712 |
| S23 / RX0 | 14 | .026 | −.161 |
| S23 / RX1 | 13 | −.111 | −.188 |

The strong RX1 relationships in S13 and S22 survive this particular correction.
Thus this estimated common phase does not explain them completely. The
inconsistency across visits remains, and the references are not independently
known bits: their phase estimate can include real shared modulation or estimation
error. This does not establish that the candidate is a repeated bit, nor exclude
other calibration effects.

Relative-phase coherence between the pair is .466 and .509 for RX1 in S13 and
S22, respectively. It is unchanged by a common rotation, as expected. The
individual frame observations remain noisy; this is not a near-perfect equality
of complex symbols. S23 coherence is .285/.316 for RX0/RX1.

Details are saved in ignored `local/header_common_phase.json`, including hashes,
frame splits, reference carriers, marginal sign baselines, and phase quality.
A synthetic test verifies that neither target can affect the phase estimate and
that an injected common rotation is removed up to the discovery reference phase.
The test and Ruff checks pass. The candidate remains unresolved; do not combine
its two positions as if they were verified copies.

## Full-band reference rejects a universal copy rule

The existing 78-frame hard-reference cache provides an additional check without
new recording or download. `reference_header_candidate.py` checks the same
symbol-2 bins 498 and 503, using the published template rotations. All 78 frames
pass the hard-axis quality gate. The signs disagree in 17/78 frames. Agreement
is 78.21%, versus 78.73% expected from their marginal positive fractions
(79.49% and 98.72%); soft correlation is −.058.

Consequently these positions must not be combined as universal repeated bits.
Conditional or acquisition-specific relationships remain possible, but this
candidate does not supply a general header decoding rule. Detailed observations
and source hash are in ignored `local/reference_header_candidate.json`.

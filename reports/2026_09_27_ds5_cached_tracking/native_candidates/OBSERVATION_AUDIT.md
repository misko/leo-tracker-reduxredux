# Read-only observation audit

This audit uses only the serialized engine calls and outcomes in the three
completed development receipts. It did not load IQ or invoke a detector.

## Receipt integrity

| Stage | Cases | Receipt SHA-256 |
|---|---:|---|
| controls | 42 | `ef376ea394de0d328e6b43c10fe6bb26786cb3c2ba73a80f8f40ad5fcbc3847f` |
| diagnostic | 26 | `bd6258addc080dc637640ec1828b9f84d269d3d40f53a70ea371c14f8511c0ae` |
| real | 64 | `335a4bb946ede0c350511920641f5ee7b1ebe56e7768200f83ff3402f45aa1cb` |

All receipts are complete and report the common source lock SHA-256
`3c49f0e0f65659d500162fb57739498221fe0d481e4f2bfc65860847163796de`.

## Candidate-zero invariance

For every K1 blind observation, the audit matched the K2 observation with the
same receiver and probe and `candidate_index == 0`. It compared every
serialized science field exactly after excluding only `total_cpu_ms` and
`total_wall_ms`.

| Stage | K1 observations | K2 candidate-zero observations | Missing keys | Science mismatches |
|---|---:|---:|---:|---:|
| controls | 924 | 924 | 0 | 0 |
| diagnostic | 572 | 572 | 0 | 0 |
| real | 1,408 | 1,408 | 0 | 0 |

The serialized screen science also agrees exactly. The K2 build therefore
adds a hypothesis without perturbing the original hypothesis.

## Effect of candidate one

K2 produced one additional observation for every receiver/probe in these
receipts. The positive count below requires status zero, valid bounds, at least
two support frames, fractional completion, and margin at least 0.025.

| Stage | Added observations | Positive added observations | K2 blind pairs selecting candidate one |
|---|---:|---:|---:|
| controls | 924 | 25 | 0 |
| diagnostic | 572 | 69 | 3 |
| real | 1,408 | 261 | 5 |

All 52 active control pairs use candidate zero twice. K1 and K2 control pairs
are exactly identical, with 52/52 injected-pilot receiver outcomes associated
and 32/32 constructed-negative receivers inactive.

In the diagnostic set, K2 selects candidate one twice in each of three pairs.
Those pairs choose alternate injected trajectories, but remain associated to
both constructed truth and the application inventory. K2 recovers zero K1
reference losses and introduces zero new K1 reference losses.

In recorded data, K2 changes five K1 receiver decisions. Four changed pairs
remain associated to an application reference. The fifth change activates
`newdev-r2500000-scan-fw-40ebc07665464c7d-v001079` RX0, where K1 was inactive;
the new pair is unassociated and must remain unadjudicated because recorded
data has no physical truth. K2 blind therefore recovers zero K1 reference
identities and loses zero K1 reference identities. The extra candidate changes
pair selection, not the original candidate's score or coordinates.

## Remaining real reference losses

K2 blind retains 67 of 79 reference-positive receiver rows: 33/37 at 2.5 MHz
and 34/42 at 5 MHz. The audit enumerated every compatible pair among all
captured positive K2 observations for each of the 12 lost receiver rows, then
tested each pair against every application reference with the frozen 2 us and
8 kHz association tolerances.

None of the 12 rows contains a matching captured pair. Eleven have no
compatible positive native pair at all. The remaining row,
`newdev-r2500000-scan-fw-40ebc07665464c7d-v001101` RX1, has eight compatible
pairs, but its selected pair differs from the nearest reference by about
227 kHz despite sub-sample timing agreement. These are search/statistic misses;
the downstream pair selector did not discard a reference-matching K2 pair.

## Tracked identity loss

K2 tracking loses one identity and one visit relative to K2 blind:
`newdev-r5000000-scan-fw-e76c229e9dc498b3-v001091` RX1. The blind pair is a
reference match at about 20.6 kHz with timing errors 0.41 and 0.82 samples.
The tracked route accepts two guided point scores at about 63.3 kHz and local
epoch 1644 samples. They have margins 0.108 and 0.201, status zero, and 15
support frames, so the controller does not fall back to blind acquisition.
Against the blind pair, their circular timing differs by 424.5 and 424.6
samples and CFO by 42.6 and 42.7 kHz, well outside the frozen identity gates.

This state originated on an alternate K2 identity. On visit 1082 K2 selected
an approximately 68 kHz pair while K1 selected approximately 24 kHz; both
associated to the then-current application inventory. Guided visit 1083 kept
the 68 kHz identity. After a guided failure, visit 1089 re-established an
approximately 64 kHz state using a pair whose first observation was candidate
one. On visit 1091 that older identity still passed both guided scores, while
fresh K2 blind acquisition selected the approximately 20.6 kHz application
identity. The loss is therefore a causal identity-persistence ambiguity after
a successful guided confirmation, rather than a missing blind hypothesis.
Recorded IQ cannot adjudicate which physical signal should be preferred.

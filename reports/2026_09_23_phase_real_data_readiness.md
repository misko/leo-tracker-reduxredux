# Real-data phase integration readiness

## Decision

A narrow adapter cannot truthfully run a real phase-augmented association or
position comparison from the retained artifacts. The blocker is not simply the
absence of secure satellite labels: surveyed position can evaluate a latent
association model without revealing identity during fitting. The blocker is
that no position-evaluation population also contains candidate-specific,
source-bound geometric phase with capture-bound calibration authority.

This audit read metadata, reports, and existing result products only. It opened
no IQ, ran no optimizer, and collected no RF.

## Evidence matrix

| Required scorer input | 2.5/10/15 MS/s phase products | Position products | Integration status |
| --- | --- | --- | --- |
| Stable observation/session keys | Session and visit keys for 24 selected dwells | Track/episode keys for the 622-track benchmark; separate five-training/14-unseen-scan cohort; separate `cf510` coverage scan | No common frozen population or key map |
| Source-specific candidate membership | Explicitly unavailable; random phase summary says `source_binding: unavailable without candidate membership or isolation` | Candidate NORAD banks and mixture weights exist | Cannot attach measured phase to a candidate without inventing a join |
| Candidate-varying phase likelihood | All hypotheses asserting the same capture link receive identical phase weight | Candidate-varying Doppler likelihood exists | Existing phase factor cannot change candidate rank or position |
| Physical phase gauge | Per-dwell relative carrier and spectral response are removed; source-seeded product is one GLRT-seeded waveform hypothesis | SGP4 direction/Doppler predictions use physical time and site | Per-dwell nuisance absorbs constant geometric phase and rate |
| Same-time two-source DD | Not retained across the multirate population; products measure one-source cross-receiver coherence or local phase response | Not applicable | Unknown receiver terms cannot be cancelled for candidate scoring |
| Electrical baseline and phase-center orientation | Mechanical 8 cm scenario only; receiver mapping/orientation not capture-bound RF calibration | Position model has receiver coordinates, not dual-chain phase centers | Candidate geometric phase cannot be predicted |
| Frequency-dependent dual-chain transfer | No capture-bound calibrated phase-delay authority | Not modeled | Source-dependent chain phase is confounded with geometry |
| Phase authority/noise scale learned without evaluation leakage | Random group waveform gates exist within selected dwells | Random whole-pass/whole-scan evaluation exists | No shared outer training population on which to learn a transferable phase weight |
| Independent position reference | Not part of selected phase scans | Surveyed truth exists and is read only by the evaluator in the formal benchmark | Position validation is possible in principle, but not on the phase population |

The random phase-link replay has sound internal mechanics—seeded whole 20 ms
groups, held frequency-set prediction, wrong-group controls, and retained
abstentions—and supports 2/8, 7/8, and 6/8 selected dwells at 2.5, 10, and
15 MS/s. Its stated interpretation is capture-level common-waveform evidence.
Because every same-capture candidate receives the same phase weight, adapting
that scalar into the position solver would be a no-op for relative candidate
weights.

The source-seeded phase product has one training-selected GLRT waveform branch
per example and explicitly claims neither source binding nor orbit improvement.
Its phase-informed rate experiment gives no consistent held benefit. It cannot
be converted into candidate geometric phase by joining its visit time to a TLE
bank: nearest-time or best-Doppler matching would manufacture the association
the new feature is supposed to test.

The formal 622-track benchmark does provide surveyed truth held outside fitting
and randomized whole-pass subsets. That distinction matters: secure NORAD
labels are not universally required to test final position. A frozen latent
candidate-mixture estimator could be fit without truth and evaluated afterward
at the surveyed coordinate. But this cohort has no bound dual-source phase
observations, and the multirate phase scans are not members of its frozen input
population. The 14 unseen scans similarly test a fixed five-scan Doppler model
at one position and have no archived candidate-specific phase fields.

## Why an adapter would be scientifically false

An adapter could match timestamps, copy one phase factor to every candidate, or
interpret nuisance-removed phase as an angle. The first invents source identity,
the second cannot change inference, and the third restores information already
absorbed by independent carrier/response fits without knowing the removed gauge.
None constitutes a phase-augmented position test. The existing 2.5 MS/s
phase-rate diagnostic is also negative: phase augmentation did not improve held
prediction over its GLRT reference. Reusing it as a positive authority would be
outcome-driven.

Separate stream-0/stream-1 joint-pilot replays do contain several truthful
20 ms two-source waveform positives, and the stream-1 28.2 s development example
admits nearly compatible independent receiver offsets. Those are useful
isolation results, so “no isolated source exists” would be wrong. They do not
supply continuous multi-second gauge transport, calibrated dual-chain phase,
secure candidate membership, or overlap with the surveyed-position population.
The 100 microsecond follow-up also failed its held phase-stability gate. These
short examples therefore cannot populate the required real position comparison.

## Smallest input that unlocks the comparison

One externally calibrated, counter-continuous dual-receiver campaign is enough
in principle if it adds all of the following to a surveyed-position evaluation
population:

1. Capture-bound electrical phase-center baseline vector and receiver mapping.
2. Dual-chain phase/delay calibration versus RF over the observed channel edges,
   including uncertainty and validity interval.
3. At least two simultaneously isolated source branches at identical raw sample
   times, with frozen epochs, aliases, complex gauge transport, and candidate
   membership established independently of the tested phase residual.
4. A predeclared random whole-capture outer split. Training captures alone set
   phase authority, nuisance scale, and weight; held captures retain failures and
   cannot tune them.
5. A candidate-complete Doppler baseline and identical phase-augmented solver.
   Surveyed position is opened only after both fits and reports paired horizontal
   error, held predictive score, coverage, and abstentions.

Candidate membership need not be a secure decoded NORAD label if a frozen
candidate-mixture model carries every plausible identity and phase is computed
for each candidate/source assignment. It must, however, bind each measured
source branch to those assignments without using the held position reference.
For a supervised same/different-track claim, external identity labels remain
necessary; for latent position improvement, the held surveyed coordinate is a
sufficient endpoint once the phase measurement and candidate binding are valid.

No existing artifact supplies this minimum jointly. The next action is therefore
calibration and source-binding acquisition, followed by one frozen whole-capture
position comparison. Another adapter, static phase replay, or optimizer pass on
the current products cannot advance the real-data claim.

## Audited authorities

- [Random multirate phase association](2026_09_23_random_phase_association.md)
- [Source-seeded phase qualification](2026_09_23_source_seeded_phase.md)
- [Formal surveyed-position benchmark](2026_09_21_formal_position_benchmark.md)
- [Randomized `cf510` regional coverage](2026_09_23_cf510_randomized_track_coverage/README.md)
- [Frozen unseen-scan orbit validation](2026_09_23_unseen_scan_orbit_validation/FINDINGS.md)
- [Differential-phase observability](2026_09_23_differential_phase_observability.md)

# Randomized grouped rebuild: feasibility and next executable design

## Verified feasibility, not a new score result

The original transfer runner binds every shortlist/CFO to the old interleaved
training mask. It also uses frequency hyperparameters calibrated on all six
recordings. Merely replacing its temporal reserve split would therefore not
produce a fully training-only randomized validation.

`grouped_split.py` now assigns session-wide 10-second UTC blocks using seed
20260927 and a deterministic SHA-256 group hash. Shared source intervals,
physical-pair keys, and RX opportunities join blocks before assignment, even
when observations belong to different tracks. Assignment ignores frequency,
reception outcomes, original training labels, and location error. The complete
group membership is saved in `grouped-feasibility.json` with source/code hashes.

| Recording suffix | Total tracks | Three-part support | Two-part support |
|---|---:|---:|---:|
| 39ac2b14d1bb5f0f | 62 | 16 | 51 |
| 4c56320fb5ca6994 | 60 | 11 | 39 |
| 9d7b6a0db558703a | 57 | 10 | 38 |
| aa9770c66396e928 | 55 | 22 | 44 |
| c559f436d578c9bd | 52 | 21 | 42 |
| da2858f6cd2521b7 | 58 | 18 | 45 |
| **Total** | **344** | **98** | **259** |

Three-part support requires at least three training observations and at least
one observation in each of A/B. Two-part support merges A/B into one partition
and requires at least three observations on both sides. The grouping seed and
10-second width were fixed before this support check; neither was optimized for
support or outcomes. The two-part design was chosen after this metadata-only
feasibility check, not preregistered before that check.

This support calculation uses only the previously retained calibration tracks.
It does not make them fresh test recordings. Ten-second grouping prevents
fine-scale shuffling and audited raw overlap; it does not prove all longer-term
correlation has disappeared. Tracks and reciprocal predictions remain dependent.
Track construction itself used the original recording, so any subsequent score
must be described as conditional on reconstructed track selection unless that
construction is also rebuilt under the split.

## Rebuild design

1. Keep the same provenance groups. Map old generated label `train` to X and
   generated labels `A`/`B` to Y. These labels are newly generated group labels,
   not the historical interleaved training mask. Hash bucket probabilities are
   50% X / 50% Y. Retain the fixed minimum of three observations on each side;
   report every unsupported track rather than silently removing it.
2. For X→Y, use X alone for full-catalogue shortlist selection, constant CFO,
   and candidate likelihood weights. Predict Y with the X-fitted CFO. Reverse
   the procedure for Y→X; do not share fitted shortlists or CFOs between arms.
3. The conditioning frequency likelihood appears **once**: the training
   shortlist likelihood already contains X. Do not add the X likelihood again
   before the RX update. Use only X reception outcomes to update X identity
   probabilities; Y supplies only the held frequency likelihood.
4. Recompute candidate-specific reception directions and tensors for the new
   shortlisted identities and observations. Saved old-shortlist direction
   arrays cannot be relabeled. Fit feature normalization, frequency parameters,
   reception coefficients, and random-effect scales using training recordings
   only. A new evaluation recording outside the six-recording calibration can
   use the frozen full calibration; a replay on one of those six requires a
   nested refit or an explicit conditional-development label.
5. Primary geometry-free baseline: 50% new frequency posterior plus 50%
   uniform probability over its own training shortlist. Primary RX comparison:
   50% RX-updated new frequency posterior plus 50% the same uniform probability.
   This compares RX after matching the same support-preserving regularization.
   Include reversed orientation and candidate-independent null. Keep the
   unregularized frequency arm as a diagnostic, not the sole comparator.
6. Hold candidate identity common across the held block, marginalizing once.
   Use occupied seconds for the historical comparison, but summarize paired
   differences at recording level and never treat frames as independent tests.
   Do not select mixture weights using evaluation outcomes.

## Progression toward geographic resolution

Run a bounded numerical smoke test first with a development label. For a
subsequent test, freeze a randomized recording/group selection from eligible
unused corpus metadata before viewing outcomes. Existing DS6 development
recordings do not become untouched merely because the observation mask changes.
Require incremental normal-RX predictive benefit beyond the geometry-free and
reversed controls before a matched geographic comparison. Preserve independent
Sacramento/Reno candidate generation in any location search. Report both priors,
per-recording distance changes, search coverage, and uncertainty; predictive NLL
alone cannot satisfy the geographic-resolution objective.

## Tests and remaining work

The local suite has 17 passing tests, including ordering invariance, cross-track
raw-window union, pair grouping, seed behavior, ignored outcomes/old labels,
posterior-blend algebra, loss bounds, and stored-control reconstruction.
These tests establish implementation properties, not improved positioning.

Still required: the new full-catalogue/CFO/direction extraction adapter, nested
or recording-disjoint calibration, frozen evaluation membership, and the actual
predictive and geographic runs. No new RF acquisition is required or authorized.

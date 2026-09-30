# Lower-edge reliability profiles across visits

The added DS10 paired-receiver excerpts close a coverage gap in the earlier
DS7/DS8/DS9 pilot-distance study: its qualified lower-edge DS9 example had no
lower-edge peer. We can now test whether the locations of reproducibly varying
early-header signals transfer, even when the transmitted signs change.

This is a structural test, not a decoded satellite identity comparison. The
three DS10 visits share conditional candidate 63400; no identity is asserted
for the DS9 example here. A shared profile could also be universal framing,
channel response, or receiver processing.

## Frozen method and coverage

Use DS9-middle and DS10-F010 visits 1085, 1150, and 1162. Their earlier/later
frame counts are respectively 22/23, 22/23, 9/9, and 10/11. All source soft-array
hashes must match their existing receipts. Compare the common 24 nonpilot
carriers over symbols 2–7 (144 coordinate locations).

For each donor, select variable coordinates using only its earlier RX0 signs
(20–80% positive). Compute centered cross-receiver unit-phase correlation at
each coordinate in the earlier donor and later target frames. Use complex
phase and its real component as two separately reported metrics. No target
variability mask or target-based coordinate selection is used. Remove each
symbol/flank mean before correlating the coordinate profiles; this prevents
a broad difference between symbols or pilot flanks from driving the result.

Controls rotate target frequency coordinates within each pilot flank, keeping
the same shift across all six symbols. Enumerate all 144 flank-shift pairs,
including the unshifted observation in the rank calculation. These controls
preserve local adjacency except at wrap boundaries, but frequency exchangeability
is approximate. Apply Bonferroni correction across four donors × four targets
× two metrics. The recordings were inspected previously: the chronological
split is a computational holdout, not pristine prospective confirmation.

## Results

Complex-phase profile correlation across distinct visits ranges from −0.075
to +0.179. The same-visit chronological correlations are 0.240, 0.218, 0.072,
and 0.178 in the visit order above. No tested profile transfer survives the
32-comparison correction. The full results, including the real-phase metric,
controls and provenance, are in ignored `local/lower-profile-transfer.json`.

In particular, the two same-channel DS10 visits 1085 and 1162 give directed
complex-profile correlations of 0.075 and 0.153. Sharing a conditional satellite
candidate does not produce a convincing repeatable coordinate profile here.
This is weak negative evidence: the profiles themselves are noisy, especially
for visits with only 9–11 evaluation frames. It does not rule out sparse header
fields or information that requires correcting unknown coding or scrambling.

The proposed simple T-state clock/counter scan was not repeated: the earlier
[sequence report](../2026_09_28_sequence_semantics/README.md) already tested
held-out affine modulo-60 counters, state recurrences and revisit alignment
without useful prediction. No new independent constraint justified repeating it.

## Reproduction and validation

Run from the repository root:

```sh
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy python reports/2026_09_29_identity_resumption/lower_profile_transfer.py
uv run --no-project --with numpy --with pytest pytest -q reports/2026_09_29_identity_resumption/test_lower_profile_transfer.py
```

The component test checks removal of symbol/flank offsets, flank-preserving
rotation, and abstention without usable coordinates. Source receipts and the
method SHA256 are recorded in the output. No new RF, production changes,
fixture modifications, or data commits were made.

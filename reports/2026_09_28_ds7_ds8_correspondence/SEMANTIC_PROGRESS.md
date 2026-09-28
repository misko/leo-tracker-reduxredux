# Bit interpretation: restricted model audit

**Later follow-up:** the resumed sequence investigation found an exact 60-state
cyclic generator matching all 907 qualified DS7/DS8/UT observations. See
[the phase-state report](../2026_09_28_sequence_semantics/README.md). This explains
the word vocabulary and parity, but does not yet assign a protocol meaning to
phase selection or decode header fields. The blocked audit below records the
earlier state of the investigation.

**Status: blocked on semantic validation, not complete.** Three consecutive
impasse checks found no applicable field/coding map or capture-matched known
field values. The completed experiments and independent pattern matches remain
valid within their stated limits. Resume with a verified applicable decoder,
header resource/coding documentation, or known transmitted field values tied to
a recording. No satellite ID, UTC, position, orbit, or header field is claimed.

The semantic decoding goal remains open. This audit combines 85 earlier
dual-receiver-qualified observations with 34 native 7.5/5 MS/s observations.
It has not identified a satellite ID, UTC field, coordinate, orbital element,
or application message.

## New evidence

- All 34 native-rate words have even parity, matching all 85 earlier words.
  Neither decoder enforces parity. There are 21 distinct native words and 42
  distinct earlier words; repetitions and cyclic relationships mean these are
  not 119 independent trials.
- Treating each recovered word as a binary polynomial, its common divisor with
  `x^60 + 1`, taken across either collection separately, is exactly `x + 1`.
  Thus no stronger common generator of an ordinary length-60 binary cyclic
  code explains these aligned words. This does not exclude LDPC, interleaving,
  scrambling, puncturing, cosets, or coding of a longer underlying message.
- No tested contiguous 2–32-bit unsigned field advances by one per elapsed RF
  frame throughout the observations. Both bit directions and polarities were
  checked. The best exploratory match explains only 30 of 103 within-visit
  transitions. This rejects these exact raw-counter hypotheses, not encoded
  counters, different units, resets, or counters in a different signal region.
- Across 38 observations conditionally assigned to NORAD 57526, every one of
  the 60 positions changes. A fixed satellite ID cannot be represented by
  invariant, directly readable positions in these aligned words under that
  assignment. Scrambled/coded IDs and different mapping conventions remain
  outside this test. The native-rate observations were not assigned identities.

## Where to look next

The repeatable 60-bit T-code and the early frame header are different signal
regions. The current primary paper explicitly leaves header semantics
uninterpreted and conjectures that T-codes arise from processing empty payload
allocations. Neither is a verified field decoder. See
[Qin et al., *Pilots and other predictable elements of the Starlink Ku-band downlink*](https://www.nature.com/articles/s44459-026-00075-6).

These results favor investigating the early full-band UT header for actual
message fields while retaining T-codes as calibration and synchronization
evidence. The existing direct convolutional-code serialization test was weak;
the next technical uncertainty is resource mapping and interleaving before
any decoder output can be interpreted. A plausible integer is insufficient:
a proposed field/coding model must predict withheld RF observations.

## Header layout follow-up

`header_layout_probe.py` broadened the prior direct serialization test to 360
layout trials: physical-frequency/native-FFT ordering, both directions,
1/4/8/16/32-lane grouping, interleaved/grouped encoder streams, three triplet
phases, and each pair of three streams. Each trial selects an even-weight
two-stream, seven-tap parity equation using only its discovery frame pair.
The selected overall candidate was still the direct native-FFT ordering.

Its parity correlation was 0.1936 on discovery frames 253/251, 0.0899 on
evaluation frames 254/252, and 0.0945 on frames 250/256. A perfect noiseless
relation would score 1. The latter scores correspond to only about 54.5% and
54.7% agreement with the equation, insufficient for claiming a code recovery.
These previously inspected UT frames are reused; this is a disjoint evaluation
within the assay, not a fresh prospective holdout. No header field was decoded.

Three tests check lossless lane permutations, equivalent stream layouts, and
recovery/generalization of an actual known convolutional-code relation.
The synthetic positive control achieves correlation 1 in both independent
streams. This result narrows the tested layouts without ruling out unknown
interleaving, scrambling, variable resource mapping, or a different code.

## Timing and transition follow-up

`temporal_word_audit.py` tests exact received-word cycles using only frame
differences within a visit. Every period from 1 through 23 frames has at least
one contradiction in the 85 original observations. This is nominally 1.33–30.67
ms at 750 frames/s, not a decoded clock. The 22 observations conditionally
assigned to STARLINK-31567 alone contradict each period from 1 through 7 frames.
Longer periods are not meaningfully excluded by its short eight-frame excerpts.

Within the single `holdout-upper` visit, four distinct words each have more
than one observed next word at an immediately consecutive frame. Therefore the
next word is not an exact deterministic function of the current 60-bit word
alone. No changes between visits or uncertain cross-pass alignment are needed
for these counterexamples. This does not exclude a larger hidden generator
state, changing inputs, or random selection from a codebook. It supplies no
absolute timestamp or semantic field.

These tests are conditional on the accepted recovered bits, and do not fit a
model allowing occasional bit errors. Two focused tests validate grouping,
missing-frame handling, and the consecutive-frame requirement. Detailed
counterexamples and input hashes are in ignored `local/temporal-word-audit.json`.

## Independent published-pattern catalogue comparison

The comparison was expanded from 13 UT frames to all 1,009 published frames,
using four carriers at bins 100–103 for fitting and four different carriers at
200–203 for validation. The bounded HTTP-range exports transferred about 4.1 MB
in total from the 5.4 GB published MAT file. Both slices have the same remote
ETag and local content hashes. These are published hard constellation symbols,
not a new raw-IQ demodulation or FEC-decoded message dataset.

A 64-symbol window is selected on the first slice alone. A word is accepted
only when selection correlation and prediction correlation on the second slice
both exceed 0.9, all 60 positions are observed on both slices, and both slices
independently recover exactly the same word. This accepts 347 UT frames,
representing 59 exact words and 31 rotation/inversion-normalized families.
The long-window criterion misses short T-code blocks; this is not claimed to
reproduce the paper's complete catalogue.

**All 119 DS7/DS8 observations match these independent reference families;
118 match exact reference words without rotation or inversion.** Our 119
observations occupy 29 families, all present in the accepted UT subset.
The new reference was not used to fit or select the DS7/DS8 words. Per-observation
matching reference frame indices are saved for audit.

This substantially strengthens the interpretation as a shared finite set of
physical-layer patterns. It does not prove that pattern selection contains no
information: choice of code, sequence, timing, or allocation could still carry
state. No numerical index assigned to this catalogue is a decoded on-air field.
In particular, the matches do not supply satellite identity or absolute time.

Source: [UT supplementary dataset and guide](https://rnl-data.ae.utexas.edu/datastore/supplementaryMaterial/qin-starlink-pilots/).
Scripts: `fetch_ut_codebook_slice.py`, `compare_ut_codebook.py`.
Two tests verify separated-frequency recovery, reject polarity disagreement,
and reject independent random signs. Outputs and slices are Git-ignored under
`local/ut-codebook/`; no data is committed.

## Pattern-selection timing and complete linear span

The 347 accepted UT words have binary linear rank **59** and all have even
parity. Since the even-parity subspace of 60 bits has dimension 59, no other
independent homogeneous linear parity equation holds for all these words in
the current position convention. This concerns the recovered 60-bit words,
not a proof against coding or scrambling elsewhere in the transmitter.

The published `TOAs` metadata reveals missing transmitted frames and 32 steps
whose arrival-time differences are not close to integer multiples of 1/750 s.
Consequently, dataset frame indices cannot be treated as a continuous RF frame
counter. The timing assay uses only the longest uninterrupted segment, dataset
indices 0–465. Arrival times fit integer frame ticks with maximum residual
0.002133 tick (about 2.85 microseconds), after removing the segment's origin.
These are receiver-relative times, not a decoded UTC field.

Within that segment, 123 accepted word observations were divided into whole
200 ms blocks. A seeded random partition assigned 87 observations to training
and 36 to evaluation. For each period 2–128 frames, a lookup predicts the most
frequent training label for each frame-tick residue, falling back to the overall
training mode for unseen residues. Leave-one-training-block-out accuracy chooses
the period; evaluation blocks do not select it.

| Predicted label | Selected period | Correct evaluation predictions | Training-mode baseline |
|---|---:|---:|---:|
| Exact word | 2 frames | 3 / 36 | 4 / 36 |
| Rotation/inversion family | 39 frames | 2 / 36 | 4 / 36 |

This provides no predictive evidence for the tested periodic selection model.
It does not exclude nonperiodic state, longer periods, information in allocation
locations, or different signal regions. Previously inspected catalogue data
are reused, so this remains exploratory despite the separate evaluation blocks.

`ut_selection_timing.py` records hashes, timing discontinuities, the partition,
all period trials, and results in ignored `local/ut-codebook/selection-timing.json`.
Two tests check a known periodic source and ensure unseen phases never use test
labels. The metadata is from the same ETag-bound published MAT file as the symbol
slices (`TOAs`, `SINRs`, `betas`, and `hasTemplate`).

## Remaining semantic evidence gap

No tested model has decoded an actual header field. The current evidence
supports reproducible physical-layer patterns and rejects several specific
interpretations, but neither a validated header resource/coding map nor matching
known transmitted field values is available. Terminal logs tied to a capture,
a verified applicable decoder, or a documented field map would provide an
independent semantic reference. The request for matching diagnostic logs remains
pending. The goal must not be marked complete on the strength of pattern matches,
failed model searches, or successful software tests.

## Reproduction files

`semantic_audit.py` reads existing qualified results and writes ignored
`local/semantic-audit.json`, including input hashes, complete restricted-model
results, and limitations. Two tests exercise binary polynomial arithmetic and
counter wraparound, gaps, and visit boundaries. No raw signal was newly
collected and no data is committed.

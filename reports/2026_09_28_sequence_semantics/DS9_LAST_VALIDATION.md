# Additional DS9 recording: paired sequence and header-sign recovery

An additional existing DS9 visit independently reproduces the known 60-state
sequence and contains changing header signs that agree across receivers above
the mismatched-frame control. It does not identify new header fields or payload.

The source is DS9 10 MS/s session index 52, session
`scan-fw-c64b5da401800b53`, visit 1295, lower pilot edge. Selection maximized
the weaker receiver's qualified pilot margin before examining bits. Margins
were 0.83861 and 0.83464. The existing 120 ms visit contains 1,200,000 complex
samples per receiver. Production storage was read through read-only contracts;
no RF recording was started and no source data were modified.

The unchanged native-rate decoder recovered 89 frames and 24 carrier coordinates
per receiver. Both receivers pass held-pilot coherence above 0.5 on all 45
reserved evaluation frames. Mean quadrature power fraction in the last ten
symbols is 0.399 and 0.385, so the full-band low-quadrature tail-boundary test
still cannot be assumed to transfer to this narrow noisy recording.

## Sequence words

The existing fixed-window paired assay attempted 405 windows and accepted 331.
Acceptance requires all 60 sequence slots represented, receiver scores above
0.25, and independently recovered words agreeing exactly. Generator lookup is
performed only after acceptance.

All 331 accepted words belong to the known generator; none introduces an unknown
word. The visit contains 28 distinct words, and all 45 evaluation frames have
multiple accepted windows with no within-frame word conflict. This is another
recording-level replication of sequence recovery, not 331 independent information
words or a new semantic interpretation. Satellite identity was not established
by this assay. The exploratory acceptance procedure does not include a shuffled
codebook gate.

## Changing header signs

The existing header audit uses the first 22 qualified frames to select varying
coordinates and RX0 confidence thresholds, then evaluates the later 23 frames.
It selects 96 varying symbol/carrier positions in symbols 2–7. Across 1,079
qualified evaluation decisions:

| Comparison | Agreement |
|---|---:|
| Matched receivers and frames | 77.48% |
| Mean of nonzero frame-shift controls | 57.69% |
| Frame-shift range | 55.70–59.96% |
| Per-coordinate marginal baseline | 60.10% |

This supports a shared changing signal, but neither receiver supplies ground
truth. Shared interference or calibration effects remain possible, and these
signs have not passed FEC, CRC, or semantic validation. The result is noisier than
DS9-middle's 86.35% matched agreement under the same assay; another strong-pilot
visit does not automatically produce more reliable header bits.

## Reproducibility

Ignored artifacts contain the exported IQ, inventory and manifest hashes,
decoder cache, frame quality, raw words, and header sign strings:

- `local/ds9-last-10m/`
- `local/DS9-last-soft.npz`
- `local/ds9_last_quality.json`
- `local/ds9_last_word_audit.json`
- `local/ds9_last_header_audit.json`

The exporter ran with `--session-index 52 --tag last --paired`; the decoder and
word audit ran with `--tag last`. The header result calls
`local_header_recovery.audit` on that cache. The word audit now accepts a tag
while retaining its previous default and output path. Raw artifacts remain
excluded from Git. No claim of decoded satellite ID, timing, orbit, or plaintext
is made from this additional visit.

## Reference-derived parity inside the captured lower edge

`lower_edge_parity.py` searches two- and three-position XOR equations directly
within the common captured bins 516–527 and 536–547, over symbols 2–7. The first
39 reference frames select equations, requiring every constituent to have at
least two observations of each sign and qualified decisions throughout discovery.
The later 39 frames test the frozen coordinates and XOR value.

There are 108 eligible discovery positions and 132 discovery equations. Exactly
one equation passes all 39 later qualified reference frames:

`bit(symbol 3, bin 524) XOR bit(symbol 3, bin 537) XOR bit(symbol 5, bin 524) = 1`.

It was then tested, without fitting local parity values, on all 45 paired
pilot-qualified evaluation frames in each of DS9-middle and DS9-last:

| Visit / receiver | Equation agreement | Independent-sign baseline |
|---|---:|---:|
| DS9-middle / RX0 | 60.00% | 57.40% |
| DS9-middle / RX1 | 48.89% | 55.24% |
| DS9-last / RX0 | 66.67% | 68.25% |
| DS9-last / RX1 | 64.44% | 64.88% |

Every constituent changes in each local comparison. Nevertheless, the equation
does not consistently exceed its marginal baseline, so it is not a validated
local parity constraint or a correction rule. Receiver noise and different
conditional layouts remain possible explanations; the test does not exclude
all FEC or more complex relationships. Local evaluation frames have been used
for other exploratory analyses, and no significance claim is made.

All candidates, failures, transfer statistics, and source hashes are retained in
ignored `local/lower_edge_parity.json`. A synthetic test recovers a complemented
copy and a three-bit XOR while excluding a fixed column. It and Ruff checks
pass. No additional recording or download was needed for this test.

## Tail-derived carrier-phase correction did not improve recovery

`ds9_tail_phase_transfer.py` tests a per-frame, per-carrier phase correction in
both DS9-middle and DS9-last. Known-sequence phase comes only from previously
accepted paired windows ending before symbol 242. For each receiver, symbols
242–271 estimate complex gain against that sequence; only its phase is removed.
Symbols 272–301 evaluate the correction. Neither those evaluation symbols nor
the header fit the gain.

The test uses the later 23 paired evaluation frames in each visit. Median
absolute phase corrections are 6.6–7.9 degrees. All four receiver/visit combinations
become slightly worse on the withheld tail:

| Visit / receiver | Tail sign disagreements before / after | Decisions |
|---|---:|---:|
| DS9-middle / RX0 | 1,946 / 1,996 | 16,560 |
| DS9-middle / RX1 | 2,010 / 2,102 | 16,560 |
| DS9-last / RX0 | 2,761 / 2,819 | 16,560 |
| DS9-last / RX1 | 2,543 / 2,564 | 16,560 |

The header comparison preserves the original RX0 discovery selection mask.
Correcting both receivers changes agreement from 86.35% to 85.71% in DS9-middle
and from 77.48% to 77.29% in DS9-last. Correcting RX0 alone leaves the original
agreement unchanged; correcting RX1 alone gives the same reduction as correcting
both. No improvement justifies applying this correction to stored decoder output.

These are disagreements with an inferred repeating sequence or the other
receiver, not verified transmitter BER. The sequence phase was selected using
paired receiver words, so the processing paths are not wholly independent.
The result rejects this specific constant-phase estimator and transfer, not
every calibration or interference model.

Detailed counts, frame splits, and hashes are in ignored
`local/ds9_tail_phase_transfer.json`. A synthetic test verifies phase removal
for a known gain without changing amplitude. It and Ruff checks pass. Existing
native caches remain unchanged; no new data were collected.

## Combining receivers improves withheld sequence recovery

`ds9_receiver_combining.py` compares original receiver signs, their equal-weight
sum, a receiver chosen per carrier using discovery performance, and learned
linear combinations. Sequence phase comes from accepted windows ending before
symbol 242. Learned weights use only the first 22 frames, symbols 242–271;
evaluation uses the later 23 frames, symbols 272–301. Each learned model has
five coefficients per carrier: real and imaginary values from each receiver,
plus an intercept. No weights are tuned on evaluation results.

| Predictor | DS9-middle disagreements / 16,560 | DS9-last disagreements / 16,560 |
|---|---:|---:|
| RX0 | 1,946 | 2,761 |
| RX1 | 2,010 | 2,543 |
| Equal-weight sum | **1,102 (6.65%)** | **1,393 (8.41%)** |
| Discovery-selected receiver per carrier | 1,994 | 2,572 |
| Linear weights from DS9-middle | 1,380 | 1,820 |
| Linear weights from DS9-last | 1,058 | 1,330 |

The equal-weight combination improves on both individual receivers in both
visits without fitted coefficients. Linear weights learned in DS9-last improve
slightly further, including transfer to DS9-middle, but weights learned in
DS9-middle are less effective. This favors retaining the simple combination
as a reproducible research estimate rather than adopting the most favorable
evaluation result as a tuned production decoder.

The improvement is measured against the inferred repeating sequence, not
independent transmitter truth. Its phase recovery uses earlier paired receiver
words. The test does not demonstrate equivalent accuracy on the header, which
may have different signal statistics, or validate FEC, CRC, or field meanings.

Equal-weight soft header estimates `(z0+z1)/2` and their real-sign decisions
are saved separately in ignored `local/DS9-middle-combined-header.npz` and
`local/DS9-last-combined-header.npz`. They include carrier coordinates, symbols
2–7, frame indices for the evaluation subset, and source-cache hashes. These
are explicitly unverified header estimates; original receiver caches remain
unchanged. Detailed results, learned coefficients, output hashes, and splits
are in ignored `local/ds9_receiver_combining.json`.

A synthetic independent-noise test verifies improvement on held-out signs.
It and Ruff checks pass. All generated arrays remain excluded from Git, and
no new recordings or downloads were made.

## Combined header estimates still do not validate the reference parity

`combined_header_parity.py` applies the previously frozen three-bit equation
at (symbol 3, bin 524), (symbol 3, bin 537), and (symbol 5, bin 524), XOR 1,
to the equal-weight combined header estimates. It uses the later 23 frames
in each visit and verifies the source-cache hashes. No comparison against the
component receivers is treated as independent truth.

| Visit | Parity agreement | Independent-sign baseline | Mean frame-shift control |
|---|---:|---:|---:|
| DS9-middle | 13/23 = 56.52% | 60.38% | 62.85% |
| DS9-last | 17/23 = 73.91% | 78.19% | 77.08% |

The frame-shift control moves the first constituent through every nonzero
frame offset while preserving the other pair. It is descriptive, not a
significance test. Both observed rates are below their marginal baselines and
their mean frame-shift controls. Receiver combining therefore does not rescue
this equation as a reliable local constraint, despite its measurable benefit
on the repeating sequence.

Requiring all three combined observations to have axis confidence above 0.9
leaves only one middle-visit frame and three last-visit frames. These all satisfy
the equation, but their marginal baseline is also 100% and no constituent varies
within either subset. They supply no validation of changing parity information.

The ignored `local/combined_header_parity.json` contains raw bit triples, masks,
frame indices, baselines, and hashes. The reused baseline/constant-sign tests
and Ruff checks pass. No corrected bits were imposed on the estimates; native
receiver caches remain unchanged. Header FEC and field meanings remain unknown.

## Symbol-by-symbol pilot phase tracking probe

The native decoder fits a linear phase drift over each frame. To test whether
untracked fluctuations between OFDM symbols explain the remaining errors,
`ds9_symbol_phase_probe.py` re-demodulates eight existing DS9-last frames
(1, 14, 28, 43, 51, 64, 76, 88) from both receivers. It reconstructs the stored
clock correction and phase-slope calibration, then fits an incremental common
phase using alternating pilot carriers and a fixed nine-symbol boxcar smoother.
The other pilot carriers evaluate the correction. Both alternating splits are
tested, producing 32 frame/receiver/split comparisons.

Mean held-pilot coherence decreases from 0.58437 to 0.57638; none of the 32
comparisons improves. For pilots in the six header symbols, mean coherence
decreases from 0.56240 to 0.55778. The experiment therefore does not justify this
additional phase correction. It may follow noisy pilot estimates rather than a
shared phase fluctuation, but the physical cause is not established.

Only the incremental correction uses disjoint pilot halves: the existing baseline
calibration already used all pilots. Pilot coherence is not bit accuracy, and
this test does not exclude other timing, phase-noise, or channel-estimation
methods. No native decoder setting or cached observation was changed.

The ignored `local/ds9_symbol_phase_probe.json` stores every before/after result,
held pilot coordinates, and hashes. A synthetic slow-phase example verifies
that the estimator can improve unused pilot carriers when a shared fluctuation
is actually present. The test and Ruff checks pass. Only existing IQ was read;
no recording or download was initiated.

## Amplitude-based erasures after receiver combining

`ds9_combined_reliability.py` tests whether weak combined observations explain
remaining disagreements with the inferred repeating sequence. Thresholds use
absolute real amplitude of the equal receiver average, learned from the first
22 eligible frames at symbols 242–271. Evaluation uses the later 23 frames at
symbols 272–301. Sequence phase comes from earlier paired windows ending before
symbol 242. Thus the evaluated decisions do not set the thresholds or phases.

The following thresholds are all learned from DS9-middle and then frozen:

| Discovery amplitude quantile | Middle retained / disagreements | Last retained / disagreements |
| --- | ---: | ---: |
| No erasure | 16,560 / 1,102 | 16,560 / 1,393 |
| 50% | 8,270 / 34 | 8,152 / 47 |
| 75% | 3,944 / 3 | 4,029 / 5 |
| 90% | 1,476 / 0 | 1,538 / 1 |
| 95% | 723 / 0 | 774 / 0 |

The median threshold retains about half the decisions with 0.41% and 0.58%
disagreement, respectively. Excluding the six worst discovery carriers gives
only a modest improvement while sacrificing a quarter of carrier observations.
Amplitude erasures are therefore more promising in this experiment. Zero observed
disagreements at stricter thresholds do not establish zero error probability;
these periodic sequence decisions are also not independent information bits.

Applying the same middle-trained thresholds to the frozen three-bit header parity
does not validate it. The median threshold leaves three complete triples in each
visit: middle agreement is 2/3, equal to its marginal baseline; last agreement is
3/3, but all constituents are constant and its baseline is also 100%. The 75%
threshold leaves one middle triple and no last triples; the 90% threshold leaves
none. These results neither identify a code nor justify correcting header bits.
Tail reliability cannot be assumed to transfer to a different signal region.

The ignored `local/ds9_combined_reliability.json` records discovery thresholds,
carrier masks, both directions of cross-visit evaluation, frame splits, counts,
and source hashes. `local/combined_header_parity.json` records the transferred
header gates. Three targeted tests pass, including masked/empty-support handling
and parity baselines; Ruff passes. Native decoding and stored IQ remain unchanged.

## Header versus tail amplitude and quadrature

`ds9_header_quadrature.py` compares the six header symbols with tail symbols
272–301 on the same 23 evaluation frames per visit and 24 carriers. The fixed
middle-trained median amplitude gate retains roughly half the individual header
observations, just as it does in the tail. Sparse complete parity triples are
therefore not evidence that the gate rejects the header as a whole.

| Visit / region | Retained observations | Imaginary energy fraction of combined signal | Real RX correlation | Imaginary RX correlation |
| --- | ---: | ---: | ---: | ---: |
| Middle / header | 49.67% | 23.90% | 0.584 | 0.220 |
| Middle / tail | 49.94% | 23.74% | 0.624 | 0.227 |
| Last / header | 49.00% | 25.11% | 0.367 | 0.017 |
| Last / tail | 49.23% | 26.35% | 0.437 | 0.037 |

Correlations remove each symbol/carrier's mean across frames before pooling, so
stationary coordinate offsets cannot alone create the reported correlation.
All nonzero cyclic frame shifts provide descriptive controls. Middle header
imaginary correlation exceeds its shifted range of −0.059 to 0.046, but the tail
shows a similar correlation. Last header imaginary correlation falls inside its
shifted range of −0.028 to 0.029. Neither visit supplies a header-specific
quadrature excess that would support interpreting the imaginary component as an
additional header bit stream. Shared channel errors, calibration, or interference
remain possible explanations; this comparison does not identify the modulation
or exclude additional bits.

Per-symbol results are retained, including weak centered real correlation in
symbol 2 (0.150 middle, 0.001 last). Centering removes constant information, so
weak variation correlation is not by itself evidence that a symbol is undecodable.
The ignored `local/ds9_header_quadrature.json` contains all controls and input
hashes. A synthetic test verifies stationary-offset removal and preservation of
shared variation; the test and Ruff pass. No observations or decoder settings
were modified.

## Does the known tail sequence explain early symbols?

`ds9_header_tail_prediction.py` predicts early signs using each frame's phase
already recovered from paired sequence windows. It fits neither phase nor
polarity to the header. Physical carrier indexing and the −16-slot step per
OFDM symbol are the same as in the validated tail model. Evaluation uses the
later 23 frames per visit and the frozen middle-trained amplitude threshold.

Across symbols 2–7, middle has 1,645 retained observations and 45.90%
disagreement with the predicted sequence, versus a weighted mean 46.51% for
nonzero cyclic frame shifts of the predictions. Last has 1,623 observations,
48.86% disagreement, and a shifted mean of 48.32%. Thus this direct sequence
continuation does not account for the early region. It does not exclude other
scrambling, a different phase assignment, or a different serialization.

Late positive controls verify that the same prediction implementation succeeds
where the sequence is known: middle symbol 272 has 0/248 disagreements and
symbol 301 has 1/288; last has 1/263 and 1/268, respectively. Their shifted
means are 35–39% disagreement. The early-region failure is therefore not a
global sign, phase, or indexing failure of this implementation.

Symbols 8–13 are also recorded. Middle symbol 13 has 35.29% disagreement versus
48.54% shifted mean, but last has 51.25% versus 48.32%. This isolated partial
match does not establish a repeatable transition or a header length. All
controls are descriptive and involve dependent observations, not independent
significance trials. The ignored `local/ds9_header_tail_prediction.json` retains
gated and ungated counts, per-symbol controls, and input hashes. Ruff passes;
no data or native decoder settings changed.

## Independent sequence-family phase in the early region

The failed tail-phase extrapolation leaves open whether the early region uses
the same 60-word family with a different phase. `ds9_header_family_test.py`
fits phase and polarity separately for each evaluation frame using only sequence
slots 0–29, then predicts slots 30–59. Splitting by slot prevents repetitions of
the same slot in other OFDM symbols from entering both fit and evaluation.
The physical carrier ordering and −16-slot step remain fixed; the amplitude
threshold is the previously frozen middle discovery threshold.

| Visit / region | Errors / retained predictions | Disagreement | Mean shuffled-family disagreement |
| --- | ---: | ---: | ---: |
| Middle / symbols 2–7 | 443 / 916 | 48.36% | 48.17% |
| Last / symbols 2–7 | 489 / 900 | 54.33% | 46.90% |
| Middle / symbols 272–277 | 3 / 884 | 0.34% | 45.88% |
| Last / symbols 272–277 | 5 / 869 | 0.58% | 47.89% |

Twenty fixed, seeded permutations of codebook columns preserve the number of
candidates and each word's bias while disrupting its slot arrangement. Every
permuted family is fitted and evaluated by the same procedure. These are
descriptive controls, not independent trials or calibrated significance tests.
The header does not obtain useful prediction from the genuine family, whereas
the tail positive controls do. An independently fitted phase and polarity
therefore do not rescue this specific early-region layout. This test does not
exclude other layouts, masks, codes, or per-symbol phase changes.

The ignored `local/ds9_header_family_test.json` records phases, polarities, frame
IDs, counts, all shuffled controls, and input hashes. A synthetic test verifies
that altering held-out slots cannot affect the fitted phase or polarity and
that genuine family words are predicted correctly. The test and Ruff pass.
No raw data or native decoder settings changed.

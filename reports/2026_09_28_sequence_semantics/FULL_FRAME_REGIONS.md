# Full-frame region map for further decoding

**Correction from soft-decision audit:** the QAM-like transition points discussed
below are hard-sliced decisions. In all six selected transition windows checked
against published soft estimates, the signal is concentrated near the real
axis, while hard slicing forces nonzero imaginary coordinates. The apparent
additional imaginary bits are therefore not credible payload evidence. Treat
the earlier QAM interpretation and hard-decision onset estimates as provisional;
see the soft-decision audit at the end of this report.

The 13 cached full-band UT reference frames were examined across all 300 data
symbols, numbered 2–301. A symbol is listed below when more than 95% of its
1,004 selected non-pilot carriers lie within the existing +/-1 membership
tolerances after division by the shared published template. This is a
template-relative observation, not independent modulation identification or a
claim that these regions are headers.

| Reference frame index | Early binary-like interval | Later binary-like interval |
|---:|---|---|
| 0 | 2–14 | 66–301 |
| 1 | 2–7 | 13–301 |
| 2 | 2–14 | 124–301 |
| 3 | 2–24 | 49–301 |
| 4 | 2–7 | 25–301 |
| 5 | 2–7 | 80–301 |
| 6 | 2–10 | 120–301 |
| 7 | 2–7 | 34–301 |
| 8 | 2–9 | 103–301 |
| 9 | 2–9 | 59–301 |
| 10 | 2–9 | 42–301 |
| 11 | 2–10 | 108–301 |
| 12 | 2–10 | 151–301 |

The previous parity searches covered the common early interval 2–7, including
its internal boundaries. These results identify additional early regions worth
testing, but their lengths vary across frames. Comparing a fixed symbol across
frames can therefore mix different kinds of regions; a negative parity test
under that alignment need not apply to a variable-position PDU header.

The long late intervals must also be distinguished from genuine coded messages:
prior work found recurring cyclic-phase structure in such tails. Binary-like
membership alone cannot distinguish header, payload, padding, or idle behavior.
No field meaning or additional decoded bits follow from this map.

Reproduction: `frame_binary_map.py`; all fractions and input hashes are in
ignored `local/frame_binary_map.json`. A focused test verifies inclusive OFDM
symbol numbering and interval boundaries; it passes, as do lint/format checks.
All input is from the existing public reference recording, not a new acquisition.

## Comparison with the known cyclic-phase vocabulary

`region_phase_audit.py` applies the existing 60-state seed, its existing
symbol-dependent carrier mapping, and both global polarities. It selects the
phase/polarity on the lower physical-frequency half only, then evaluates the
other half without refitting. Only qualified template-relative +/-1 decisions
contribute. The frozen vocabulary is not learned again from these regions.

| Region | Symbols examined | Exact in both halves | Median discovery disagreement | Median evaluation disagreement |
|---|---:|---:|---:|---:|
| Common early symbols 2–7 | 78 | 0 | 43.17% | 49.25% |
| Additional early symbols beyond 7 | 46 | 0 | 44.82% | 49.70% |
| Two late-region samples per frame | 26 | 14 | 0% | 0% |

The late samples are the region's first symbol and five symbols later, not an
exhaustive audit of all tails. These controls show that the procedure can
recognize the vocabulary in this reference, while the extra early regions do
not follow that particular model. This supports investigating those 46 symbols
as a distinct target. It does not prove that they carry GMH headers, recover
their bits' meanings, or exclude other repeating structures or carrier mappings.
Disagreement with a hypothesized pattern is not receiver bit-error rate.

All per-symbol results and hashes are in ignored `local/region_phase_audit.json`.
A focused test flips only the evaluation half and verifies that it cannot
change the fitted phase/polarity. It passes, as do lint/format checks. Region
selection remains exploratory on the same shared recording/template.

## Region-matched coding probe in symbols 8–9

`extended_header_probe.py` tests symbols 8 and 9 using only reference frames
whose mapped early region includes the symbol. Discovery uses frame pairs
(0,2) and (3,6); evaluation is reserved as (8,9) and (10,11), with eligible
frame 12 unused. The split is by frame index, not selected by parity scores.
Frames whose early region ends at symbol 7 are excluded.

The existing generator-independent 114-bit assay searches every within-symbol
start in both carrier orders/directions and each pair of the three candidate
encoder outputs. It tests interleaved and separate-block layouts, qualifies
individual seven-tap windows, requires 30 windows total and eight per frame
pair, and excludes constant columns while allowing rare changes.

**All 21,384 configurations per layout have sufficient discovery support;
neither layout yields an exact discovery relation.** Consequently no relation
is selected for evaluation. This result extends coverage into a distinct early
region without mixing it with the variable middle region. It does not establish
an encoder or exclude coding with other serialization, scrambling, or decision
errors. The frames remain previously examined data from one recording.

Results and hashes are in ignored `local/extended_header_probe.json`. A focused
test verifies region eligibility, disjoint splits, and rejection when too few
frames qualify. It passes; lint/format pass. Symbols 10–24 do not have enough
eligible frames in this 13-frame set for the same two-pairs-per-split protocol.

## Exploratory tail onset versus cyclic phase

A bounded follow-up asks whether the late sequence starts at a fixed phase.
For each frame, phase/polarity are taken from the existing sample five symbols
inside the late region. Around the coarse tail transition, symbols from three
before through one after are ordered by physical frequency, with the existing
1,004 non-pilot carriers per symbol. The known phase pattern predicts each
carrier via `(compact_carrier_index - 16 * OFDM_symbol) mod 60`.

The candidate onset is the first 240-carrier window with at least 238 complex
decisions within 0.05 of its predicted +/-1 value. Its absolute compact index
is `b = (first_search_symbol - 2) * 1004 + window_start`. If the sequence
restarts from one constant cyclic phase, a candidate constraint is that
`(b + fitted_phase) mod 60` is constant, up to onset-estimation error.

For reference frames 0–12, the observed residues are:

```
58, 47, 58, 56, 16, 31, 58, 57, 58, 11, 3, 57, 58
```

Eight lie in 56–58; five are outside that range. The allowance of two
mismatches can move the apparent start before the actual transition, and
accidental matching symbols can move it further. Crucially, the onset estimate
itself depends on the fitted phase, and the three-residue grouping was noticed
after inspecting results. This is a partly circular exploratory lead, not a
statistically independent validation or recovered protocol field. It neither
establishes a fixed reset phase nor justifies assigning satellite identity.
An independently determined boundary would be needed to test that explanation.

Parameters, all per-frame values, and source hashes are recorded in ignored
`local/tail_boundary_phase.json`. No RF collection or firmware execution was
required for this calculation.

## Tail boundary estimated without the cyclic sequence

`tail_axis_boundary.py` repeats the boundary search using only membership near
the real-axis points +/-1 after the published template. It never uses signs,
phase, polarity, or cyclic words to locate the boundary. It uses the same five
symbols and 240-carrier window as above; phase is joined only after all
boundaries have been estimated. The coarse boundary also comes from axis
membership. This removes direct dependence on the fitted sequence, although
the recording and template remain shared.

With zero non-member carriers allowed in the window, `(boundary + phase) % 60`
for frames 0–12 is:

```
0, 50, 0, 0, 18, 33, 0, 0, 0, 13, 9, 59, 0
```

Seven frames give exactly zero; frame 11 gives 59. Five remain outside that
neighborhood. Allowing one or two non-members gives, respectively:

```
59, 48, 59, 58, 17, 32, 59, 58, 59, 12, 5, 58, 59
58, 47, 58, 52, 16, 31, 56, 57, 58, 11, 3, 57, 58
```

The shift with error allowance is consistent with a window starting slightly
before a transition. The no-error result strengthens the reset-phase hypothesis
relative to the earlier phase-conditioned boundary: its concentration survives
removing sign/sequence matching from boundary selection. However, a real-axis
transition is not necessarily the true sequence start, and five counterexamples
remain. This is exploratory evidence from 13 previously examined frames, not
independent acquisition validation, a decoded header field, or a significance
test. Carrier serialization and phase convention also matter to the residue.
The next discriminating check is to examine the five exceptions and test the
same fixed rule on other available frames without tuning to their phases.

Ignored `local/tail_axis_boundary.json` records all boundaries, phases,
parameters, and source hashes. Two focused tests verify invariance under
arbitrary sign changes, the effect of error allowance on a known transition,
and rejection when no qualifying region exists.

## The exceptions contain the tail sign pattern before the axis transition

`tail_transition_audit.py` examines the symbol immediately before each
zero-error axis boundary. All five outlying residues have boundaries at compact
carrier 0, 2, or 6 of a symbol. All seven residue-zero frames instead transition
inside a symbol, at carriers 76–690. The residue-59 frame transitions at carrier
1. The preceding carriers are finite, so missing/NaN data do not explain this
division.

For a fixed 240-carrier window at the end of the preceding symbol, the audit
projects the already fitted tail phase and polarity backward using the same
carrier rule. It compares real-part signs without fitting any new phase or
polarity, allowing QAM points with nonzero imaginary parts. Results for the
five exceptions and the near-zero frame are:

| Frame | Axis-boundary carrier | Residue | Matching signs / 240 | Marginal agreement baseline |
| --- | ---: | ---: | ---: | ---: |
| 1 | 2 | 50 | 239 | 60.69% |
| 4 | 0 | 18 | 239 | 60.69% |
| 5 | 0 | 33 | 231 | 50.08% |
| 9 | 0 | 13 | 185 | 50.03% |
| 10 | 6 | 9 | 239 | 50.19% |
| 11 | 1 | 59 | 240 | 55.56% |

In comparison, the seven residue-zero frames match only 48.3–54.2% in that
preceding-symbol window. The marginal baseline accounts descriptively for sign
imbalance; it is not a significance test. Errors here are disagreement with a
model, not a measured RF BER. These are published reference constellation
decisions, not a fresh independently demodulated recording.

This shows that, in several exception frames, the known tail sign pattern is
already present before the transition to +/-1 points. The axis detector can
therefore locate a constellation change rather than the start of that pattern.
The five exceptions cannot simply be dismissed as measurement noise, and the
earlier residues do not establish a universal reset rule. Frame 9 is less
conclusive than the other exceptions. Full QAM bit labeling, coding, and the
actual sequence onset remain unresolved. A next useful test is to follow the
sign pattern backward across the QAM region and characterize its other decision
bits, keeping phase selection separate from evaluation.

All rows and source hashes are in ignored `local/tail_transition_audit.json`.
Two tests cover QAM sign decisions, invalid/ambiguous points, and constant-sign
agreement that carries no information beyond its marginal baseline.

## Backward QAM trace and magnitude-only onset estimate

The transition audit now traces four preceding symbols with the later tail's
phase and polarity fixed. In frames 4 and 10, the sign pattern is already
present in the penultimate symbol: its last 240 carriers match 239/240. The
immediately preceding symbol matches about 99.9% across all 1,004 carriers in
both frames. Frames 1, 5, and 11 first show strong agreement in the last symbol
of this four-symbol trace; frame 9 remains weaker. Earlier sampled symbols
have approximately chance-level agreement. This bounds a short transition
region, rather than showing that the entire middle region is this sequence.

Other constellation components do not simply repeat the real-sign word. Across
the last 240 carriers of the immediately preceding symbol, imaginary signs at
lag 60 agree in approximately 48–63% of comparisons for these six frames.
In five frames the modal absolute coordinate pair is (0.707, 0.236); frame 9
instead has (0.857, 0.171). Thus a predictable real sign can coexist with varying
imaginary signs. This is not yet a verified QAM bit-label map or evidence that
the varying signs encode interpretable payload.

An exploratory magnitude-only boundary detector uses that modal coordinate
pair, tolerance 0.01 on each absolute coordinate, and the first 240-carrier
window with at most two outliers in the three symbols before the axis
transition. Neither coordinate sign nor fitted phase enters boundary selection.
The resulting `(boundary + phase) % 60` residues are:

| Frame | At most two outliers | No outliers |
| --- | ---: | ---: |
| 1 | 59 | 6 |
| 4 | 57 | 0 |
| 5 | No qualifying window | No qualifying window |
| 9 | No qualifying window | No qualifying window |
| 10 | 59 | 40 |
| 11 | 58 | 13 |

The two-outlier result brings four QAM transitions near the previously observed
reset residue, but the zero-outlier estimates are unstable and two frames yield
no qualifying boundary. The magnitude class and test were chosen after looking
at this recording. These results motivate the reset hypothesis; they do not
validate it. No new semantic bits have been identified. A useful next step is
to test whether the varying imaginary signs follow a separate known rotation
or scrambler, with discovery and evaluation carriers kept separate.

The existing ignored audit JSON now includes the four-symbol traces, modal
coordinate pairs, both boundary estimates, and updated source hashes. A third
focused test verifies boundary invariance under independent real and imaginary
sign flips.

## Imaginary-sign sequence probe

`qam_imaginary_probe.py` tests the same last 240 QAM carriers in frames
1, 4, 5, 9, 10, and 11. It treats the imaginary sign and the product of real
and imaginary signs as separate observables. Candidate families are all 60
rotations of all 60 cyclic words (3,600 candidates, including duplicates) and
all 32,767 shifts of the previously recovered 15-stage PN sequence. PN positions
retain the physical carrier spacing including skipped pilot positions. Both
polarities are allowed. Candidate and polarity are selected using only the
first 120 carriers; the remaining 120 evaluate the selected prediction.

None of the 24 frame/observable/family combinations gives an exact evaluation
match. PN evaluation disagreements range from 46 to 71 of 120. Cyclic-family
disagreements range from 23 to 63. The strongest cyclic result is frame 10's
imaginary sign, with 34 discovery and 23 evaluation disagreements. Its fitted
prediction is nonconstant, and its evaluation marginal-agreement baseline is
50.28%. However, simply predicting imaginary sign equals observed real sign
already gives 96/120 evaluation matches, versus 97/120 for the fitted cyclic
word. For the sign-product observable, the selected cyclic candidate is the
constant all-positive word; its 80% evaluation agreement equals its marginal
baseline. Thus this apparent lead adds little beyond the existing real-sign
pattern and coordinate-sign imbalance.

This bounded probe does not recover another sequence or semantic bits. It
rejects treating these imaginary signs as clean instances of either tested
family under these mappings; it does not rule out other scramblers, bit
interleaving, coding, mixed regions, or decision errors. The next useful work
is to determine the QAM bit mapping and investigate the concentrated magnitude
classes, rather than label the remaining signs as decoded payload.

Ignored `local/qam_imaginary_probe.json` records every selection, polarity,
support, error count, marginal baseline, PN seed, and input hash. One focused
test verifies that changing all evaluation signs cannot alter the selected
candidate or polarity. It and lint checks pass. Data are from the same
previously examined recording, not an independent acquisition.

## Soft decisions reveal a hard-slicing artifact

The public `EXEMPLAR_FRAMES_GUIDE.txt` defines `yDataDec` as nearest-constellation
hard decisions and `yDataSoft` as phase/timing-corrected and power-normalized
estimates before hard decisions. `modEst` stores one estimated constellation
per OFDM symbol. This raises a critical concern for symbols containing a
transition: a real-axis signal can be forced onto a QAM grid with no real-axis
points. Its resulting imaginary sign need not represent a transmitted bit.

`fetch_soft_transition.py` retrieves native FFT carriers 400–463 from soft
reference frames 0–12, transferring 3,889,047 bytes with bounded HTTP ranges
and an ETag consistency check. `soft_transition_audit.py` applies the same
published template to soft and hard decisions, comparing 64 carriers in each
selected symbol and in symbols two earlier and two later. No new RF recording
was made. The six transition-window results are:

| Frame | Median absolute soft I | Median absolute soft Q | Median absolute hard Q | Soft Q/I power |
| --- | ---: | ---: | ---: | ---: |
| 1 | 0.692 | 0.055 | 0.236 | 1.21% |
| 4 | 0.698 | 0.065 | 0.236 | 1.81% |
| 5 | 0.745 | 0.072 | 0.236 | 1.56% |
| 9 | 0.792 | 0.074 | 0.171 | 1.56% |
| 10 | 0.772 | 0.088 | 0.236 | 2.04% |
| 11 | 0.761 | 0.090 | 0.236 | 2.45% |

The soft samples cluster near the real axis, with small quadrature residuals;
hard slicing places them at a nonzero minimum quadrature level. Earlier control
symbols have median absolute soft Q of 0.248–0.527, whereas later real-axis
control symbols have 0.069–0.112. This strongly supports a hard-slicing artifact
in the selected windows. It does not establish a complete receiver error model
or exclude all quadrature information elsewhere in the frame.

Consequently, the previous characterization as extra QAM imaginary bits is
withdrawn for these windows. The real-sign continuation remains evidence, but
the hard-decision +/-1 transition is not a dependable physical onset detector.
Magnitude-only boundaries derived from hard points are also provisional. The
next boundary analysis should use soft estimates and allow amplitude changes;
further bit recovery must avoid treating forced QAM coordinates as transmitted
data. These are still published processed estimates from one recording, not
independent raw-IQ validation.

Ignored `local/soft-transition-0-12.npz` and its metadata preserve the downloaded
slice; `local/soft_transition_audit.json` records all statistics and input hashes.
A focused test distinguishes real-axis noise from forced QAM quadrature levels.

## Soft-power boundaries predict all 13 phases

`fetch_full_soft.py` extends the existing soft slice to all 1,024 carriers of
frames 0–12. The successful bounded extraction transferred 57,602,571 bytes,
checked the same source ETag, and reused the earlier 64-carrier slice. An initial
attempt stopped at its range-size guard after transferring 57,725,985 bytes;
the successful version groups chunks by file offset to avoid storage gaps and
checkpoints batches. Both attempts downloaded existing public data, not new RF.

`soft_tail_boundary.py` removes the published template and uses only the power
fraction `q = imag(z)^2 / abs(z)^2`, which is invariant to sign and nonzero
amplitude scaling. Within symbols `coarse_start - 4` through `coarse_start + 1`,
it estimates pre/post means from the first/last 502 selected carriers. It selects
the split minimizing squared error to those two fixed means, requiring at least
one flank on either side. The phase is joined only after all boundaries are
estimated. The coarse search region comes from the previous axis-membership
map, not from cyclic-phase matching.

For all 13 frames, the result is exactly `(boundary + phase) % 60 == 0`:

| Frame | Soft boundary | Fitted phase | Hard boundary minus soft boundary |
| --- | ---: | ---: | ---: |
| 0 | 63353 | 7 | 0 |
| 1 | 10696 | 44 | 350 |
| 2 | 122564 | 16 | 0 |
| 3 | 46855 | 5 | 0 |
| 4 | 21574 | 26 | 1518 |
| 5 | 78099 | 21 | 213 |
| 6 | 117649 | 11 | 0 |
| 7 | 31814 | 46 | 0 |
| 8 | 100627 | 53 | 0 |
| 9 | 57095 | 25 | 133 |
| 10 | 38777 | 43 | 1389 |
| 11 | 106066 | 14 | 359 |
| 12 | 149190 | 30 | 0 |

Boundary indexing concatenates the 1,004 selected non-pilot carriers in ascending
physical frequency, starting at OFDM symbol 2. This is a carrier count, not a
byte count or a time-of-arrival measurement. Before-transition mean quadrature
fraction is 0.475–0.523; after-transition mean is 0.011–0.028. Repeating with
251- and 1,004-carrier flanks gives exactly the same 13 boundaries, not just
the same residues. This sensitivity check is not a complete uncertainty model.

The result resolves the five earlier outlying phases and the one-carrier
near-match without phase-conditioned boundary selection. **Within these frames,
the cyclic phase is fully predicted by the start offset of the repeating
region modulo 60.** It is therefore unnecessary to posit an independent
satellite-identity field to explain this variation. The observation is
consistent with a sequence restarting at that boundary and being compared
against a template anchored elsewhere. It does not by itself specify the
transmitter implementation, establish padding semantics, or decode a header
length field. The boundary-to-phase interpretation still needs testing on
other frames/acquisitions; all 13 frames were previously examined and share the
same template. No statistical significance or universal protocol rule is claimed.

Ignored `local/soft_tail_boundary.json` stores all flank results and source
hashes. The full soft cache and checkpoint batches are also ignored. A focused
test verifies known-boundary recovery under independent coordinate sign changes
and per-carrier amplitude scaling; it and lint checks pass.

## Check using locally demodulated raw-IQ frames

`raw_tail_boundary.py` applies the same 502-carrier-flank soft-power change
detector to the final six symbols of the seven cached raw-IQ-derived frames
250–256. These labels correspond to public reference indices 249–255, disjoint
from reference frames 0–12 above. The source is `pilot_polarity.npz`, produced
by the local FFT, channel/timing correction, and two separate edge-pilot phase
references in `pilot_polarity.py`; it does not use published hard decisions.

Eligibility requires a before-flank mean quadrature fraction above 0.3 and an
after-flank mean below 0.1. This sign/phase-independent gate admits four frames
for both edge references. Frames 252, 253, and 256 have after-flank means
0.459–0.553 and are ineligible; they are not counted as matching or contradicting
the rule. The six-symbol window and eligibility thresholds are exploratory
choices, not a pre-registered test.

Phase is fitted on qualified post-boundary carriers in the lower physical
frequency half of the final symbol, then evaluated on its upper half. Carriers
qualify when `abs(imag(z))/abs(z) < 0.4`; the predicted boundary residue is not
used to select phase. Both edge references give identical results:

| Raw frame label | Boundary | Predicted and fitted phase | Upper-half evaluation support, edges 0 / 1 |
| --- | ---: | ---: | ---: |
| 250 | 299288 | 52 | 497 / 487 |
| 251 | 300517 | 23 | 498 / 494 |
| 254 | 298469 | 31 | 502 / 502 |
| 255 | 298465 | 35 | 499 / 477 |

All discovery and evaluation sign decisions agree with their fitted cyclic
words; all eight edge-specific estimates satisfy `(boundary + phase) % 60 == 0`.
The shorter tail in frame 251 leaves 179/178 qualified discovery carriers for
the two edges, still sufficient to select the observed phase in this assay.

This extends the exact relation to **17 distinct eligible frames** across two
processing paths. It supports the start-offset interpretation beyond the
published reference decoder. It remains one public acquisition, and both edge
corrections share SSS channel and timing estimates; eight edge estimates are
not eight independent frames. This is not yet evidence from DS7/DS8/DS9, a
decoded header length field, or an independently confirmed transmitter rule.

Ignored `local/raw_tail_boundary.json` records all 14 frame/edge cases,
eligibility statistics, fitted/predicted phases, decision counts, and source
hashes. A focused test checks that the eligibility gate rejects both a
non-axis tail and an all-axis window lacking a transition.

## Restricted firmware codeword budget check

`boundary_codeword_budget.py` asks whether the measured compact boundary count
can be expressed as `114 * h + L * n`, with one header of `h = 1..16` 32-bit
units, one payload MCS, and a positive integer number `n` of codewords of length
`L`. The 114-symbol header unit has firmware scheduler evidence; the payload
lengths come from the 132 nonzero MCS records in the existing firmware table
extraction. The range of header units is an assay bound, not a proved RF header
limit. No offset, gap, partial codeword, or mixed-MCS term is fitted.

Seven frames (0, 2, 3, 6, 8, 9, 10) have no solution. The remaining frames have:

| Frame | MCS-labelled matches | Distinct numerical budgets |
| --- | ---: | ---: |
| 1 | 33 | 7 |
| 4 | 1 | 1 |
| 5 | 1 | 1 |
| 7 | 1 | 1 |
| 11 | 2 | 2 |
| 12 | 9 | 4 |

Even exact numerical fits do not decode a header. Multiple MCS IDs share a
symbol count, and the isolated fits in frames 4/5/7 do not rescue a layout that
fails for seven other frames. Compact non-pilot carrier counts have not been
proven equivalent to the firmware scheduler's units across every RF region;
the firmware also postdates the recording. Thus this check rejects only the
specified simple layout under those assumptions. It does not invalidate the
observed phase-to-boundary relation or exclude mixed codeword groups, prefixes,
other overhead, or older firmware formats. A direct header-length claim would
be premature.

Ignored `local/boundary_codeword_budget.json` stores every match and hashes.
A focused test shows that shared codeword sizes cannot identify MCS and checks
an incompatible one-carrier offset; it and lint pass.

## Transfer feasibility in existing DS7/DS8 soft caches

`local_boundary_feasibility.py` inspects the nine existing paired-visit caches,
preserving their calibration/evaluation split. Frames must be evaluation frames
at both receivers and have held-pilot coherence above 0.5 at both. This leaves
179 frame pairs across five visits; four visits contribute none under this gate.

| Visit | Qualified frame pairs | Carriers per receiver | Mean final-ten-symbol Q fraction, RX0 / RX1 |
| --- | ---: | ---: | ---: |
| S01 | 44 | 11 | 0.397 / 0.421 |
| S02 | 41 | 11 | 0.408 / 0.402 |
| S13 | 20 | 24 | 0.436 / 0.428 |
| S22 | 32 | 24 | 0.372 / 0.417 |
| S23 | 42 | 24 | 0.369 / 0.404 |

S06, S07, S18, and S19 have no eligible frame pair. None of the 358 individual
receiver/frame final-ten-symbol averages is below 0.1. The usable raw-UT tails,
by comparison, had final 502-carrier Q fractions of 0.016–0.048. These windows
are not identical, so this is a transfer-feasibility diagnostic, not a direct
performance comparison or proof that the local signal lacks a tail. Noise,
calibration, interfering signals, and actual modulation can all affect it.

The current local caches therefore do not support applying the clean full-band
boundary detector unchanged. They contain only 11 or 24 observed carriers per
symbol, with large unobserved gaps. Concatenating those samples as if contiguous
would produce a false boundary index. Predicting the missing boundary from the
observed phase would also be circular. Recovery by averaging, improved local
calibration, or additional existing recordings remains possible.

This audit covers nine cached DS7/DS8 visits only: it is neither an exhaustive
dataset search nor a DS9 test. DS9 remains an authorized source for subsequent
analysis. Ignored `local/local_boundary_feasibility.json` saves every qualified
frame index, per-frame and per-symbol power statistic, and cache hash. Lint passes.

## First bounded DS9 demodulation

The first, middle, and last admitted 10 MS/s sessions were queried through the
production tracking-input read contract. An upper-edge-only candidate filter
returned no candidates in those three sessions. Inspection of the first session
found 4,438 lower-edge probes, so an upper-only filter was inappropriate for it.
This does not establish the edge distribution of every DS9 session.

`export_ds9_pilot_visit.py` selects the strongest qualified start-zero pilot
candidate of either edge in the first admitted 10 MS/s session, before examining
its unknown bits. It requires a matching peer candidate within five samples,
checks the admitted raw-manifest binding, and reads only one existing visit
through `AdaptiveHopIqStore(..., read_only=True)`. The exported case is:

- Session `scan-fw-2ab18976d4eb3bf8`, visit 1536, lower edge, channel 3.
- 10 MS/s, 120 ms, 1,200,000 complex samples per receiver.
- Acquisition fractional margins: RX0 0.62939, RX1 0.78602.
- Both receiver excerpts and their hashes are retained in ignored local storage.

`decode_ds9_visit.py` reuses the existing native-rate demodulator with a 90-frame
cap. It produces 89 complete frames and 24 data carriers per receiver. Of the
channel-estimation-held-out evaluation frames, RX1 has 25 with held-pilot
coherence above 0.5; RX0 has none. The paired gate therefore admits zero frames.
RX1's qualified frames have mean final-ten-symbol quadrature fraction 0.44294,
which does not support transplanting the clean-UT real-axis boundary threshold.

This is concrete DS9 IQ availability and demodulation evidence, but not a
cross-receiver sequence or boundary validation. A strong acquisition margin is
not a guarantee of good full-frame pilot calibration. The next useful checks
are diagnosing RX0 calibration and sampling another pilot-selected lower-edge
visit, rather than treating RX1's output as decoded semantic bits. No RF
collection or QNAP mutation occurred.

Ignored `local/ds9-first-10m/inventory.json`, `local/DS9-first-soft.npz`, and
`local/ds9_first_quality.json` preserve source bindings, excerpts, soft estimates,
evaluation indices, and quality statistics. The scope is one visit, not a DS9
survey or a dataset-wide failure claim.

## DS9 calibration diagnostic: no useful timing/alias correction

`ds9_calibration_probe.py` tests frame 0 of the selected visit using known pilots
only. It separately checks carrier-frequency aliases at -2, -1, 0, +1, +2 times
the OFDM symbol rate (1/4.4 microseconds), and timing shifts from -2 to +2 native
10 MS/s samples in half-sample steps at the original frequency. It selects by
coherence on pilot symbols 22–301, then evaluates the selected correction on
frame 1, including pilot symbols 2–21 excluded from each frequency/channel fit.
This is not a joint timing/frequency optimization or a test of every impairment.

Both receivers select the original frequency alias. Other aliases give only
0.016–0.088 training coherence, versus 0.362/0.484 at the original estimate.
The selected timing shifts are +1.5 samples for RX0 and +1.0 for RX1. On frame 1,
held-pilot coherence changes from 0.33186 to 0.32269 for RX0 and 0.48457 to
0.48495 for RX1. Neither result fixes the calibration limitation; RX0 gets
slightly worse. The original soft cache and acquisition estimates are retained.

These results do not identify the underlying impairment or exclude finer CFO,
channel-model, or interference effects. They do show that the tested simple
alias/timing corrections are not a useful recovery step for this visit. Sampling
another existing paired DS9 visit is preferable to adopting an unsupported
correction. Ignored `local/ds9_calibration_probe.json` records all trials,
selection, evaluation, and inventory binding. Lint passes.

## Second DS9 visit: paired 60-bit recovery succeeds

The exporter now supports choosing a session index and ranking matching
receiver pairs by their weaker fractional pilot margin. The second sample is
the middle admitted 10 MS/s session (zero-based index 26 of 53),
`scan-fw-fad62f2672600b46`, lower-edge visit 50. Acquisition margins are 0.87094
and 0.86146. Selection uses cached known-pilot scores before unknown-bit
inspection, requires peer epochs within five samples, and reads only this
existing 120 ms visit. A focused test verifies weaker-receiver ranking and
rejects an epoch-mismatched pair. The first visit's files remain unchanged.

Native-rate demodulation gives 89 frames and 24 data carriers at each receiver.
Both receivers pass held-pilot coherence >0.5 on all 45 channel-estimation-held-out
evaluation frames. Their final-ten-symbol mean quadrature fractions are 0.36744
and 0.36355; the narrowband/noise limitation on precise boundary detection
therefore remains even though paired sequence recovery is now successful.

`ds9_word_audit.py` applies the pre-existing fixed 32-symbol window assay,
starting at symbols 14, 46, …, 270. It independently recovers a 60-bit word from
each receiver, requires full slot coverage and exact receiver agreement, and
requires both correlation scores to exceed 0.25. Only afterward does it look
up the word in the previously derived cyclic generator.

- 405 windows tested across 45 evaluation frames; 368 accepted.
- All 45 frames have multiple accepted windows, with no within-frame word or
  family conflicts.
- 28 distinct words (20 rotation/complement families) occur.
- All 368 accepted words exactly match the known 60-state generator; none lie
  outside it.

This extends paired recovery of the known raw 60-bit signature into DS9 on a
separate acquisition from UT. It does not independently validate the
boundary-to-phase rule: inferring an unobserved boundary from these phases would
be circular. These are also not new header fields, satellite identities, or
payload bits. Windows overlap in frames and share calibration; 368 windows are
not 368 independent recordings. The assay retains its exploratory scope and
has no shuffled-code acceptance gate.

Ignored `local/ds9-middle-10m/inventory.json`, `local/DS9-middle-soft.npz`,
`local/ds9_middle_quality.json`, and `local/ds9_word_audit.json` preserve excerpt
bindings, demodulated samples, diagnostics, all recovered words, phases, and
acceptance outcomes. No new RF collection occurred.

## DS9 cross-receiver power: residual quadrature is shared

`ds9_cross_power.py` evaluates the last 30 symbols (272–301) in the 45 paired
evaluation frames, comparing matched-frame real/imaginary cross products with
all different-frame pairings. Both receivers cover identical bins. Cross-power
can suppress uncorrelated receiver noise, but retains common interference,
leakage, and signal-processing errors; it is not automatically transmitted data.

The mean matched real cross-power is 1.31842 and imaginary cross-power 0.20414
in the cache's normalized units, giving a quadrature fraction of 0.13407. The
different-frame imaginary mean is 0.00668 (standard deviation 0.04321). Thus the
remaining quadrature component is substantially shared by the receivers for
the same frame, rather than being explained solely by independent noise.
These dependent pairings are descriptive controls, not a significance test.

As a control, each receiver's real-axis angle is estimated from the preceding
30 symbols (242–271) using half the phase of the mean squared complex value,
without using decoded signs. Evaluating on symbols 272–301 after this correction
gives a quadrature fraction of 0.13531, essentially unchanged. A constant
per-frame axis rotation therefore does not remove this component.

No extra quadrature bits are claimed. The next discriminating test is whether
known neighboring-carrier patterns and a fitted linear leakage response predict
the shared residual on separate frames. That would distinguish a processing
artifact from unexplained signal structure more usefully than treating it as
independent noise or prematurely decoding it as payload.

Ignored `local/ds9_cross_power.json` records the complete cross-frame matrices,
axis estimates, statistics, and source hash. A focused synthetic test verifies
that shared quadrature survives cross-products while independent noise averages
down; it and lint pass.

## Adjacent-carrier model explains little of the shared DS9 residual

`ds9_leakage_probe.py` predicts template-relative complex values using known
cyclic signs on the target carrier and its nearest neighbors. Neighbor signs
are multiplied by the published neighbor-to-target template rotation, preserving
the complex phases that a leakage model would need. It fits a complex intercept
and complex coefficients separately for each receiver and target carrier.

The 45 eligible frames are divided chronologically into 22 discovery and 23
evaluation frames. Only symbols 272–301 enter the regression. Phase for each
frame comes from accepted windows ending before symbol 272, so no tail sample
is used to fit its phase for this probe. Four reported models use neighbor
radii 0, 1, 2, and 4. All use the same 16 target carriers, excluding targets
whose radius-four neighborhood includes an edge pilot. Each fitted carrier
has 660 complex discovery samples and at most ten complex coefficients.

| Neighbor radius | Evaluation imaginary cross-power | Reduction from uncorrected |
| --- | ---: | ---: |
| Uncorrected | 0.18864 | — |
| 0 | 0.19083 | -1.16% |
| 1 | 0.17824 | 5.51% |
| 2 | 0.17673 | 6.31% |
| 4 | 0.17712 | 6.11% |

Single-receiver imaginary power reductions are below 1.3% for all models.
The shared residual therefore is not mainly explained by this fitted linear,
same-symbol nearest-carrier model. This does not exclude leakage involving
other OFDM symbols, pilots, nonlinear processing, another signal, or changing
channel parameters. It also does not establish transmitted quadrature payload.
The uncorrected value differs from the earlier power audit because this assay
uses only 16 carriers and 23 evaluation frames.

Ignored `local/ds9_leakage_probe.json` records splits, carriers, source hashes,
and all model results. A focused test verifies exact recovery of a synthetic
linear response and confirms that altering evaluation values cannot change
fitted coefficients or predictions. It and lint pass. A useful next test is
direct cross-receiver reproducibility of quadrature decisions and their time/
frequency structure, rather than assuming the residual is either noise or bits.

## Quadrature signs reproduce weakly, without the known repetition

`ds9_quadrature_structure.py` uses the same chronological split: 22 discovery
frames and 23 evaluation frames. It examines symbols 242–301 on the 24 captured
carriers. Thresholds on RX0 imaginary magnitude are fixed from discovery frames;
RX1 neither sets thresholds nor selects evaluation samples.

| RX0 magnitude gate | Evaluation decisions | Receiver sign agreement |
| --- | ---: | ---: |
| All samples | 33,120 | 57.41% |
| Discovery median | 16,230 | 61.92% |
| Discovery 75th percentile | 7,842 | 66.45% |
| Discovery 90th percentile | 3,091 | 70.92% |

Marginal sign-imbalance baselines are approximately 50% for all four gates.
These percentages are receiver agreement, not bit error rates or the fraction
of correctly decoded transmitted bits. Matching different frames gives 49.38%
quadrature agreement. Cross-receiver symbol lags 1, 2, 5, 15, and 30 give
49.48–50.16%; native-bin lags 1, 2, and 4 give 49.51–50.38%, counting only
actually observed bin pairs and never bridging missing pilot bins as neighbors.

For comparison, unshifted real-sign agreement is 81.01%, and at symbol lags 15
and 30 it remains 78.35% and 79.09%. Those lags preserve the known slot mapping
because `16 * 15` is divisible by 60. The quadrature component does not show
that same repetition, so the averaging that recovers the known real 60-bit word
cannot simply be reused to claim a second quadrature word.

This confirms weak same-coordinate reproducibility beyond sign imbalance and
constrains simple time/frequency repetition hypotheses. It does not identify
the shared component: another signal, common interference, or receiver/model
effects remain alternatives to unknown transmitted data. Any further bit claim
needs an encoding or additional reproducible structure, not just a confidence
threshold on these signs.

Ignored `local/ds9_quadrature_structure.json` stores thresholds, splits, counts,
lag controls, and input hash. Two focused tests verify the sign-imbalance
baseline and masked disagreement accounting; tests and lint pass.

## Direct boundary-field probe in early soft signs

`header_boundary_fields.py` uses measured soft boundaries as external labels for
the first six data symbols (2–7) in the 13 full-band reference frames. It tests
four direct binary quantities: compact boundary (18 bits), zero-based symbol
offset `boundary // 1004` (8 bits), within-symbol carrier offset (10 bits), and
remaining carriers `301200 - boundary` (19 bits). Each quantity is tested in
LSB-first and MSB-first bit order, with ascending/descending native-FFT and
physical-frequency carrier orders, preserving forward symbol order.

Every contiguous start, including symbol crossings, is examined. Discovery
frames 0–5 must qualify on all field decisions using
`abs(real(z))/abs(z) > 0.9`. A positionwise XOR mask is fitted only on those
six frames, allowing fixed sign inversions without assigning their meaning.
Evaluation uses frames 6–12 with the mask frozen.

There are **183,188 supported start/field/order configurations and zero exact
discovery matches**, hence no validated copied field. The best discovery
fraction has 8 disagreements out of 48 decisions for the 8-bit symbol offset;
on evaluation it has 33 disagreements out of 55 qualified decisions. This
posthoc best case provides no useful prediction.

The result excludes only the tested direct contiguous binary representations
under a fixed XOR mask and these decision qualities. It neither establishes
absence of a length field nor addresses FEC, interleaving, variable scrambling,
byte permutations, different field units, or nonlinear encodings. Boundary
positions are observations, not known transmitter header contents. The frames
also remain from the previously examined acquisition.

Ignored `local/header_boundary_fields.json` records every model's support,
discovery/evaluation counts, selected mask, and source hashes. A focused test
recovers an injected masked field and verifies that changing evaluation values
cannot alter selection or mask; it and lint pass.

## Boundary-only prediction of complete tails

`boundary_tail_prediction.py` predicts every selected tail carrier from the
power-derived boundary alone. It uses the existing generator with
`phase = (-boundary) % 60`, fixed polarity +1, and
`slot = (absolute_compact_position - 32) % 60`. The latter is algebraically
identical to `carrier - 16 * symbol` in the prior convention. There is no
per-frame word, phase, or polarity fit in this prediction.

| Source and region | Decisions | Model disagreements | Boundary+1 control disagreements |
| --- | ---: | ---: | ---: |
| 13 reference frames, 240 carriers before boundary | 3,120 | 1,516 | 1,538 |
| Reference, first 240 tail carriers | 3,120 | 1 | 1,561 |
| Reference, rest of tail | 2,968,121 | 2,185 | 1,484,004 |
| 4 raw frames × 2 edge corrections, 240 before | 1,920 | 990 | 902 |
| Raw, first 240 tail carriers | 1,920 | 0 | 960 |
| Raw, rest of tail | 14,202 | 2 | 7,098 |

Across the reference tails, 2,186 of 2,971,241 sign decisions disagree with the
prediction (about 0.074%). Across the two raw edge corrections, 2 of 16,122
disagree. All finite decisions are counted without a sign-confidence gate.
The abrupt improvement at the boundary and the approximately chance-level
one-position control support a deterministic sequence beginning there, beyond
merely matching phase labels sampled later in the frame.

This is expanded verification on previously examined data, not a fresh blind
validation: the generator and boundary relation came from this acquisition.
Millions of periodic decisions are not millions of independent information
bits. The two raw edge corrections share IQ and are not independent recordings.
Also, adding 60 to the boundary predicts identical signs, so the pattern alone
does not determine the absolute boundary. Its location still comes from the
soft-power transition. Model disagreements are not a verified transmitted BER.

The result supports reconstructing this observed deterministic part of the
signal; it does not decode preceding header fields or establish whether the
transmitter labels the region padding, idle allocation, or something else.
Ignored `local/boundary_tail_prediction.json` stores all per-frame counts and
hashes. A focused test verifies absolute/within-symbol indexing equivalence and
the unavoidable modulo-60 ambiguity; it and lint pass.

## Remaining tail disagreements concentrate at FFT bin 511

`tail_error_localization.py` counts every model disagreement and decision by
frame and carrier. Of the 2,186 reference-tail disagreements, **2,180 occur at
native FFT bin 511**; only six occur on all other selected carriers combined.
The six are at bins 513 (two), 514 (two), 515 (one), and 518 (one). Bin 511
errors typically have substantial amplitude, so calling them low-SNR decisions
without further analysis would be unjustified.

To avoid selecting a carrier mask from evaluation outcomes, the script marks
carriers whose error fraction exceeds 10% using frames 0–5 only. That rule
selects bin 511 alone. With that carrier set frozen:

| Split | Carrier group | Decisions | Disagreements |
| --- | --- | ---: | ---: |
| Discovery, frames 0–5 | Bin 511 | 1,461 | 1,227 |
| Discovery | All other carriers | 1,462,598 | 1 |
| Evaluation, frames 6–12 | Bin 511 | 1,505 | 953 |
| Evaluation | All other carriers | 1,505,677 | 5 |

Thus the boundary-driven model explains essentially all observed tail signs
away from one specific carrier, while retaining a clear unresolved exception.
The exceptional carrier is not silently discarded from overall results, and
its behavior is not yet classified as an artifact, pilot, or additional data.
The localization was noticed posthoc on the same acquisition; the subsequent
split is a check on concentration, not a fresh independent validation.

Ignored `local/tail_error_localization.json` contains the complete carrier/frame
counts, selected carrier, and hashes. A test verifies that evaluation-only
errors cannot change carrier selection; it and lint pass. Next, the bin-511
exception should be compared with the corresponding raw spectrum and adjacent
carriers before assigning any bit meaning.

## Bin 511 follows the same sequence after a complex-gain correction

The short raw-IQ tails also localize both of their mismatches to bin 511: one
decision in frame 251 under each edge correction. Across four eligible frames,
each edge correction observes only nine tail decisions on that carrier. This
is insufficient for a meaningful per-frame discovery/evaluation gain split,
so the longer public soft-reference tails are used for the following test.

The bin-511 complex samples have high correlation with the boundary-predicted
sequence even when their real-part signs disagree. Unlike neighboring bins,
their complex phase relative to that prediction is far from zero and varies
between frames. `tail_carrier_phase.py` estimates a single complex gain per
frame/carrier from the first 30 tail symbols as `mean(observed * predicted_sign)`.
It freezes that gain and evaluates all later tail symbols. Neighboring bins
510 and 512 serve as controls.

| FFT bin | Later evaluation decisions | Original sign disagreements | After gain correction |
| --- | ---: | ---: | ---: |
| 510 | 2,576 | 0 | 0 |
| 511 | 2,576 | 1,880 | **0** |
| 512 | 2,563 | 0 | 0 |

Bin 511's discovery gain angles range from about -174 to +169 degrees across
frames; the neighbors stay near zero (-1 to +11 degrees). This explains the
earlier sign exception as a phase/gain issue for purposes of sequence recovery:
after correction, the same generator predicts every evaluated bin-511 sign.
It provides no evidence for extra changing bits on that carrier.

The correction does not identify the physical cause. A transmitter convention,
channel/equalization effect, or reference-processing issue could produce such
phases. The gain is fitted using known tail predictions, so this is a calibrated
extension of the model, not a boundary-only prediction with no fitted parameters.
The test is also posthoc on the same acquisition; it does not prove the gain
model will transfer to other recordings or into the header.

Ignored `local/tail_carrier_phase.json` records all gains, counts, and hashes.
A focused test recovers a synthetic complex gain and verifies that changing
evaluation samples cannot alter it; test and lint pass.

## Tail-trained phase correction can improve bin511 header alignment

`tail_header_phase_transfer.py` fits a linear phase versus symbol index to
bin511 using only the first half of its known tail signs. It evaluates sign
prediction on the remaining half and extrapolates the same correction backward
to header symbols 2–7. Header signs do not enter the fit. This addresses a
different question from the constant-gain tail test: whether a tail-derived
calibration can help recover the earlier unknown portion.

The later-tail evaluation has zero sign disagreements in 1,486 decisions.
The mean normalized header quadrature fraction at this carrier falls from
0.41777 to 0.08962 across the 13 frames, improving in 11 frames and worsening
slightly in two. This supports using the known tail as calibration evidence at
this exceptional carrier, with an explicit extrapolation limitation.

No header decisions are validated by axis alignment alone. The test covers
only six header decisions per frame on one carrier; it neither explains the
bulk header coding problem nor identifies a header field. A corrected point
near the real axis may still have an unknown polarity or other decoding error.
The fit's physical origin and transfer to other acquisitions remain unproved.
The original soft samples and prior results are preserved.

Ignored `local/tail_header_phase_transfer.json` stores all coefficients,
per-frame header/tail metrics, decision counts, and hashes. A focused test
recovers a known phase drift under changing BPSK signs; test and lint pass.

## Coding streams separated across OFDM symbols

`time_separated_code_probe.py` extends the earlier coding tests to pairs of
different OFDM symbols. It tests every pair among symbols 2–7 as two candidate
encoder-output streams, in ascending/descending physical and native-FFT carrier
order. At every 38-carrier block start, it searches for a nontrivial seven-tap
binary parity relation involving both streams, without prescribing generator
polynomials. Constant discovery columns cannot contribute to a relation.

Discovery uses three frame differences from the locally demodulated raw header
cache; evaluation is prepared from six frame differences in soft reference
frames 0–11. Frame differencing cancels a fixed positionwise mask only. Every
parity window must have all 14 input decisions qualified, with at least 30
windows overall and eight per discovery frame pair. Frequency ordering does
not collapse the OFDM-symbol dimension: stream separation is the new hypothesis.

Of 58,020 configurations, 57,320 meet discovery support requirements.
**None has an exact discovery relation**, so no candidate advances to evaluation.
This rejects only the specified two-stream, seven-tap, 38-carrier mapping under
the decision qualities used. It does not exclude a convolutional code with
different memory, bit offsets, variable scrambling, a more general interleaver,
or enough decision errors to break exact checks. It is not evidence that the
header is uncoded or encrypted.

Ignored `local/time_separated_code_probe.json` records coverage and source
hashes. A focused test verifies frequency-window and frame-pair indexing and
quality rejection; it and lint pass.

## Noise-tolerant full-symbol parity check

`noisy_time_code_probe.py` pools qualified seven-tap windows across whole
symbol pairs, allowing imperfect parity rather than requiring an exact null
relation. It evaluates 60 symbol-pair/carrier-order configurations and 918,960
mask/configuration combinations, including dependent duplicates. Masks contain
4–10 taps across both streams, using only discovery columns whose one-frequency
lies between 10% and 90%.

Raw parity correlation needs a stronger baseline than independent individual
bits. An initial high score between symbols 2 and 4 was largely explained by
adjacent-bit repetition within each stream: discovery correlation 0.514 versus
a product-of-stream-parities baseline 0.555; evaluation 0.189 versus 0.175.
That relation is not persuasive encoder evidence.

The implemented selection therefore maximizes the absolute excess over the
product of the two empirical stream-parity means, with mask and orientation
chosen on discovery only. The selected relation is mask 15878 between symbols
3 and 4 in ascending physical frequency. Discovery excess is 0.18363 across
2,568 windows; evaluation excess is only 0.01253 across 5,862 windows. Its
oriented evaluation parity correlation is -0.01433, approximately chance-level
agreement. It supplies no usable code relation or decoder.

This addresses noise tolerance for the specified pooled mapping, not all FEC
layouts. A short embedded code may be diluted by pooling an entire symbol,
and the overlapping windows do not justify a naive independent-sample
significance calculation. Data remain from different frame sets of the same
acquisition. Ignored `local/noisy_time_code_probe.json` stores all selected
relations, baselines, support, and hashes. A synthetic test recovers an injected
four-tap relation with 2% parity violations; it and lint pass.

## Fixed repeated-carrier bit grids are not supported

`header_repetition_grid.py` tests whether each changing encoded bit is repeated
on a fixed group of adjacent selected carriers. Frame XOR first cancels a fixed
positionwise mask. True noiseless repetition of width R would place all changes
between adjacent XOR bits at one residue modulo R. The probe tests widths 2–32
in native-FFT and physical-frequency order for symbols 2–7. It chooses the grid
offset with the highest change rate using three raw-IQ discovery frame pairs,
then measures it on six separate soft-reference frame pairs.

For the strongly correlated symbols 2 and 4, the physical-order evaluation
fraction of changes on the selected grid is:

| Repetition width | Symbol 2 | Symbol 4 | Approximate support fraction |
| --- | ---: | ---: | ---: |
| 2 | 50.94% | 50.75% | 50% |
| 4 | 25.12% | 26.52% | 25% |
| 8 | 13.23% | 12.21% | 12.5% |
| 16 | 6.86% | 6.13% | 6.25% |

There are 1,429 and 2,006 qualified evaluation transitions in those symbols.
The changes are not concentrated at fixed repeated-bit boundaries. These
results do not justify collapsing carrier groups before FEC decoding. They
test selected-carrier grids only: variable repetition, a grid advancing through
excluded pilots, other offsets/layouts, and a formal error model are not covered.
Within-stream correlation by itself is not evidence for a simple repetition code.

Ignored `local/header_repetition_grid.json` stores all 372 symbol/order/width
results, coverage baselines, and hashes. A synthetic repeated-bit test verifies
that the assay finds changes only at true group boundaries; it and lint pass.

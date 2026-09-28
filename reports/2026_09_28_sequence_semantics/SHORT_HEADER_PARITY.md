# Short-prefix header parity investigation

2026-09-28. No verified header fields or additional decoded message are claimed.

The [downlink patent](https://patents.google.com/patent/US12074683B1/en)
describes convolutionally encoded BPSK PDU headers, a rate-1/3 encoder with six
memory bits, and assignment from lower to higher available subcarriers. It does
not establish that the entire observed six-symbol region is one coded header.
Its general modem discussion covers multiple links; applicability to this
recording remains a hypothesis.

This assay tests only prefixes of 69, 81, 87, or 99 data carriers, separately in
OFDM symbols 2 through 7. These lengths explore short-header hypotheses; they
are not measured lengths. We test physical-frequency and FFT-bin ordering in
both directions, three output phases, and all output-stream pairs. Pairwise
frame XOR cancels a fixed unknown carrier mask. Fourteen-bit windows represent
seven taps from two output streams. Search includes both odd and even parity.
Any selected input column must have discovery one-fraction between 0.1 and 0.9,
to reduce trivial checks dominated by constant regions.

Discovery uses three disjoint pairs from raw-derived UT frames 250–255.
Evaluation uses six disjoint pairs from published reference indices 0–11.
Frame 256 and reference index 12 are unused. Both sets have been inspected in
earlier research and come from the same recording; this is exploratory reuse,
not prospective validation. Only windows with qualified decisions in both
frames enter the analysis. The pairing treats each set in its stored order.

634 configurations have sufficient support and eligible masks. None has an
exact discovery parity relation. The discovery-selected candidate uses symbol
2, a 99-carrier prefix in descending FFT order, phase 2, output streams 0 and 2,
and mask 264. It is a two-bit relation, not evidence for a complete encoder.
Its signed parity correlation falls from 0.875 (64 windows) to 0.474359
(156 windows): agreement falls from 93.75% to 73.72%. Correlated windows and
selection prevent interpreting these counts as independent binomial trials.
The residual correlation may reflect repeated or low-entropy structure;
it does not validate a convolutional code or identify a header field.

The test closes a gap in the earlier whole-symbol parity probes, but does not
exclude headers elsewhere, other carrier allocations, interleaving, variable
boundaries, or low-entropy headers excluded by the activity filter. A header
decoder still requires stronger evidence. Firmware acquisition remains useful
for independently constraining mapping and coding.

Reproduction: `short_header_parity.py`; ignored results and input hashes:
`local/short_header_parity.json`. Two focused tests verify recovery of a known
synthetic convolutional relation on separate random words and rejection of an
all-constant region. No new RF data was collected.

## Follow-up: arbitrary within-symbol starting positions

`moving_header_code.py` tests a fixed **assumed**, not measured, generator set
of octal 133/171/165 in all six output-stream permutations. Unlike the prefix
probe, it slides candidate lengths 69/81/87/99 across all within-symbol starts
in both carrier orders and directions. It uses all three pairwise convolutional
syndromes, removing the first six input-time positions where encoder history is
unknown. Frame pairing and discovery/evaluation split remain as above.

Eligibility requires every discovery decision in the candidate to be qualified,
and average frame-XOR activity between 0.1 and 0.9. These restrictions exclude
many starts; therefore this is not a claim to have rejected every location.
76,488 eligible start/length/order/generator combinations were evaluated. None
had zero discovery syndrome errors. The discovery-selected candidate was symbol
4, physical ascending order, compact start 477 (FFT bin 979), length 69, output
generators 165/171/133. Its syndrome error fraction was 0.228758 on discovery
and 0.467320 on evaluation; all evaluation decisions were qualified. Activity
rose from 0.106280 to 0.260870, so low discovery entropy is a plausible source
of the apparently better training score. Evaluation is near the random-bit
syndrome baseline and does not substantiate a decoder.

Only the best discovery candidate per configuration was evaluated; no search
over evaluation scores selected the reported candidate. Pairwise syndromes and
overlapping positions are dependent. A nonzero syndrome can reflect receiver
errors, so the result weakens this restricted hypothesis rather than proving
that no such code occurs. Other generators, interleaving, header boundaries
crossing symbols, or different carrier allocations remain untested here.

Two additional tests verify zero syndromes for synthetic encoded words, detection
of deliberate corruption, and approximately half failing checks for random
uncoded words. The JSON results and input hashes are in ignored
`local/moving_header_code.json`. Formatting/lint checks passed.

## Firmware-derived 114-bit candidate

The dish firmware's MAC MCS entry 0 specifies 32 bits and 114 symbols. This is
compatible with 32 information bits plus six termination bits encoded at rate
1/3, but neither the generators nor downlink applicability is established.
The same moving-window assay was therefore rerun with length 114, preserving
the previous carrier orders, directions, six stream permutations, eligibility
filter, and discovery/evaluation split. Reproduction:

```
python moving_header_code.py --lengths 114 --output local/moving_header_code_114.json
```

Of 10,020 eligible start/order/generator combinations, none had zero discovery
syndrome errors. The discovery-selected candidate was symbol 7, descending
physical frequency, compact start 874, actual FFT bin 649, generators
133/171/165 octal. Its syndrome-error fraction was 0.413194 on discovery and
0.513889 on evaluation, with qualified evaluation decisions. This provides no
support for that candidate. It does not reject other generator sets,
interleaving, symbol-crossing boundaries, or excluded low-activity regions.
The assay uses necessary convolutional parity relations; it does not enforce
the proposed termination state or recover a 32-bit message.

The reporting code now distinguishes the actual FFT bin from the column index
in the compact carrier array; the older output's `first_bin` field stored the
column index. Existing historical JSON remains unchanged. A third focused test
encodes 32 random bits with six termination zeros, checks 114-bit words after
fixed-mask cancellation, and detects corruption. All three focused tests and
lint passed. No new RF data was collected.

User-directed recording scope going forward is **DS7 + DS8 + DS9**. DS9's
manifest is `reports/2026_09_28_ds9_post_ds8/manifest.json`; the current assay
still uses the UT full-band reference. Dataset availability does not establish
that a narrowband visit contains a complete candidate codeword.

## Generator-independent exact relation check

`blind_header_114.py` removes the assumed 133/171/165 generators. For each
eligible 114-bit window it builds seven-tap windows for each pair of the three
serialized output streams. GF(2) elimination searches for a homogeneous parity
relation using both streams. Columns with one-fraction outside 0.1–0.9 cannot
participate, to avoid constant-region relations. All within-symbol starts are
considered in both carrier orders and directions; quality/activity filters and
frame pairing remain as above. Arbitrary starts already cover the three output
phases. Only one representative relation per eligible configuration would be
evaluated on the separate frame group; that group never selects the relation.

**No exact discovery relation was found in 5,010 eligible configurations.**
Consequently there was no relation to evaluate or interpret. This result is
independent of a particular seven-tap generator pair, but still assumes direct
uninterleaved serialization and fixed-mask cancellation. It is an exact,
error-sensitive necessary-relation test, not a decoder or proof that the signal
lacks convolutional coding. The activity filter can exclude real low-entropy
headers, and untested symbol-crossing/interleaved layouts remain possible.

Two focused tests verify recovery with a different synthetic generator set,
generalization to independently generated words, detection of corruption, and
rejection of random or constant input. Both pass; lint/format checks pass.
Results and input hashes: ignored `local/blind_header_114.json`.

## Separate encoder-output blocks

The same generator-independent assay also tests a 114-bit word as three
consecutive 38-bit output-stream blocks, converted to interleaved triples before
forming the parity checks. This layout was not covered by reversing carrier
order or permuting interleaved streams. Reproduction:
`python blind_header_114.py --layout stream_blocks`.

Again, **5,010 eligible configurations produced no exact discovery relation**;
there was no candidate to evaluate. The layout is a hypothesis, not one recovered
from firmware. Noise sensitivity, fixed-mask assumptions, activity exclusion,
within-symbol boundaries, and reuse of previously examined UT data all still
apply. Three focused tests now pass, including a synthetic block-serialized
code that yields a relation after the correct permutation and no relation under
the wrong interleaved interpretation. Lint and formatting pass. Results are
in ignored `local/blind_header_114_stream_blocks.json`; the earlier interleaved
result remains separate.

## Coverage and rare-change audit

The original all-bits-qualified gate excludes **19,256 of 21,384** candidate
windows (90.05%). This substantially limits the negative result's coverage;
it does not mean 90% of individual bits are bad. One unqualified decision in
any of the three discovery frame pairs rejects the entire 114-bit window.

`--activity-floor 0` now allows arbitrarily rare changes while still excluding
exactly constant input columns and exactly constant candidate differences.
Of the 2,128 quality-qualified windows, 404 are constant and 1,724 remain,
yielding 5,172 paired-stream configurations per layout. Interleaved output
produces 12 exact discovery relations, all two-bit checks in overlapping
symbol-4 windows represented under different orders/directions. Their
discovery activity is only 0.01754–0.02339. Every relation's evaluation signed
correlation falls to 0.458333 (agreement 0.729167), with qualified evaluation
bits. None remains exact or establishes an encoder. The separate-block layout
produces zero discovery relations at this lower activity threshold.

Results are saved separately as `local/blind_header_114_activity_0.json` and
`local/blind_header_114_stream_blocks_activity_0.json`. Four tests pass, including
a rare-change synthetic code that the old activity threshold excludes and the
new setting detects; constant columns remain excluded. Lint/format pass.
The next useful improvement is to qualify individual parity windows rather
than reject every candidate containing any uncertain bit, while retaining
minimum support and separate evaluation requirements.

## Qualification at the parity-window level

`--quality-mode parity_window --activity-floor 0` retains a seven-tap,
two-stream parity window only if all its 14 input decisions are qualified.
It requires at least 30 retained windows overall and at least eight from each
frame pair. Discovery still selects one representative mixed-stream null check
without consulting evaluation. Evaluation additionally requires every selected
column to vary, avoiding trivial success on constant evaluation inputs.

Both layouts now admit 18,888 candidate words before pair-level support checks.
Of their 56,664 stream-pair configurations, 326 lack discovery support for the
interleaved layout and 904 for separate blocks. Thus **56,338 interleaved** and
**55,760 block-layout** configurations are tested, versus 5,172 per layout with
the whole-word quality gate at the same activity threshold. These are overlapping
configurations, not independent statistical trials.

The interleaved scan finds 1,684 exact discovery relations; all have sufficient
evaluation support and varying selected columns, but **none remains exact on
evaluation**. Separate blocks yield no exact discovery relation. This closes
much of the earlier quality-coverage gap without establishing an encoder.

A post-hoc inspection of evaluation scores finds a maximum signed correlation
of 0.947917 (187/192 agreeing windows). That candidate is only a two-bit
relation in a low-activity symbol-2 region, with discovery activity 0.020468;
it is not a recovered generator triple or decoded header. Selecting this maximum
uses evaluation data, so it is exploratory evidence, not held-out confirmation.
The largest correlation among checks using at least three bits is 0.90625.
Near-relations merit error-aware follow-up, but neither a zero-error requirement
nor these selected scores establish absence or presence of a full code.

Five focused tests pass. The new test verifies that changing an unqualified bit
cannot change retained parity windows and that a frame pair with no support
fails the support gate. Lint/format pass. Results:
`local/blind_header_114_activity_0_parity_window.json` and
`local/blind_header_114_stream_blocks_activity_0_parity_window.json`.

## Bias audit of the highest evaluation near-match

`parity_bias_audit.py` re-extracts the post-hoc highest-scoring two-bit relation.
Across its 192 evaluation windows, the two columns have eight and three ones.
Their contingency counts are 184 occurrences of (0,0), zero of (0,1), five of
(1,0), and three of (1,1). Thus observed agreement is 97.3958%, but the product
of the observed marginal frequencies already gives a descriptive independent-
bits baseline of 94.4010%. Excess agreement is only 2.9948 percentage points.

There is additional alignment: all three ones in the second column coincide
with ones in the first. Circularly shifting the second column within each
32-window frame-pair block gives 94.2708% agreement for shifts 1–30 and
96.3542% for shift 31, compared with 97.3958% at shift zero. These are
descriptive controls, not independent significance tests. They neither prove
independence nor establish an encoder; the candidate was selected using these
evaluation data and the windows overlap. Most of the headline agreement comes
from zero-heavy inputs, so interpreting 2.6% disagreement as an encoder's bit
error rate would be unjustified.

Two focused tests verify the marginal baseline on independent biased bits and
perfectly equal balanced bits. Both pass. Results and hashes are saved in
ignored `local/parity_bias_audit.json`. No RF header or payload is decoded by
this audit.

## Candidate codewords crossing OFDM-symbol boundaries

`--boundaries crossing --quality-mode parity_window --activity-floor 0`
extends the assay to the 113 possible 114-bit windows straddling each boundary
between symbols 2–3 through 6–7. Carrier order is applied within each symbol;
time order remains forward. Both physical/FFT carrier orders, both frequency
directions, and both output-stream layouts are tested. These are candidate
serializations, not a recovered transmitter allocation rule.

There are 2,260 candidate windows per layout, of which one has constant
discovery differences. After the existing per-frame-pair support requirements,
6,541 interleaved and 6,099 separate-block configurations remain. Interleaved
output gives 275 exact discovery relations, but none passes the exact evaluation
gate. Separate blocks give no exact discovery relations. No full encoder or
header is identified. The results retain the earlier noise, fixed-mask,
selection, overlap, and reused-recording limitations.

Six focused tests now pass, including explicit verification that stitching
adjacent symbols preserves forward time order while reversing carrier order
within each symbol. Lint/format pass. Results are the ignored
`local/blind_header_114_activity_0_parity_window_crossing.json` and
`local/blind_header_114_stream_blocks_activity_0_parity_window_crossing.json`.

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

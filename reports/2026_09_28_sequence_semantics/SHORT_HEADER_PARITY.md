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

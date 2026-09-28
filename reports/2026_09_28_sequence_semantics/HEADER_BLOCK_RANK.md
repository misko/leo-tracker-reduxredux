# Necessary linear-code test on the existing 78-frame reference

`header_block_rank.py` tests whether contiguous 114-position windows could be
the output of a fixed affine encoder with at most 32 variable inputs. Such an
encoder must produce frame differences with binary rank at most 32. This is a
necessary condition, not evidence that a passing window uses that encoder.

The test uses the existing `header-reference-0-77.npz` cache, SHA-256
`192d4271c055b4bba90ec6df0db011dbc0d2391ec677ee57fc69940488a6133f`.
It removes published template rotations and uses 1,004 nonpilot carriers in
symbols 2–7. Discovery frames are 0–38; evaluation frames are 39–77. Four
layouts cover FFT and physical carrier order in either direction. All contiguous
starts, including symbol crossings, are tested. Layouts overlap and are not
independent candidates.

Every discovery bit must pass the hard-axis quality gate, and at least 64 of
114 columns must vary relative to the first discovery frame. A fixed XOR mask
cancels in the frame differences. Discovery ranks above 32 are rejected; passing
windows with qualified evaluation data receive a combined 78-frame rank test.

| Stage | Windows |
|---|---:|
| Starts examined | 23,644 |
| Discovery quality passes | 20,926 |
| At least 64 changing columns | 18,854 |
| Discovery rank at most 32 | 2,940 |
| Also evaluation quality passes | 2,644 |
| Combined rank at most 32 | 1,970 |

Surviving starts lie in symbols 3 and 4. Combined ranks range from 7 to 32.
No surviving window has 32 or fewer nonmodal frames, so the low rank is not
explained merely by almost all frames being one identical word. However, 822
windows have rank equal to the number of distinct words minus one: in those
cases the limited number of distinct patterns already bounds rank without
demonstrating additional linear constraints.

For example, FFT ascending start 2821 has 87 changing discovery columns,
discovery rank 3, combined rank 7, and only eight distinct words among 78 frames;
50 frames differ from its most frequent word. This is structured variation but
does not identify a 32-to-114 encoder. Repeated bit groups, conditional templates,
or a small set of message states can also produce low rank.

The remaining candidates need structural analysis and independent validation,
including tests against already understood repetition. No input bits, generator,
interleaver, CRC, or MAC fields have been recovered by this rank test. Errors can
increase exact rank; variable masks, encoder state, and other layouts are outside
its scope. All frames are from the same public acquisition.

Detailed windows, counts, and hashes are in ignored `local/header_block_rank.json`.
The rank unit test covers an explicit 32-dimensional basis, a 33rd independent
bit, redundant rows, and the zero case. It passes along with Ruff checks.

## Follow-up: higher-order relationships and raw-frame transfer

`header_rank_relations.py` derives an explicit binary dependency basis from the
39 discovery frames, then evaluates each relation on the later 39 frames. It
examines all 2,644 discovery-selected windows with evaluation quality, including
those whose combined rank exceeds 32. Constants and simple copies/complements
are distinguished from relations involving three or more positions.

None of the 1,970 low-rank survivors is explained entirely by constants and
copies: the number of distinct nonzero frame-difference column patterns exceeds
rank in every case. This demonstrates higher-order dependencies within the
observed sample, but limited message diversity can still cause them.

There are 123,166 discovery basis relations of weight at least three, of which
6,101 pass all later reference frames. Deduplicating by actual symbol/carrier
coordinates reduces these to 1,497 distinct equations. These counts are strongly
dependent and must not be interpreted as independent confirmations.

The equations were then evaluated on the existing seven pilot-referenced raw-IQ
frames from another portion of the same public acquisition. All 1,497 have at
least four qualified frames; 1,494 have no qualified parity errors. However,
**1,417 of those passing equations have no changing constituent at all** in this
short raw sample. Only two passing equations have every constituent vary; both
have nine positions. This distinction prevents static-template agreement from
being mistaken for strong code validation.

One such nine-position equation uses OFDM symbol 2, native FFT bins
901, 903, 905, 906, 916, 917, 918, 920, and 932. Its template-relative sign-bit
XOR is 1 in all 78 reference frames and all seven qualified raw frames. This
is a candidate empirical relation, not an identified transmitter parity check.
The other surviving equations and all failures are retained in ignored
`local/header_rank_relations.json`.

The next useful test is whether these relations follow from known or conditional
templates, or recur under a fixed mapping in the local datasets. No encoder,
input bits, CRC, or header semantics has yet been established. The raw check
uses another processing path and different frames, but not an independent
acquisition. A synthetic test distinguishes copies from a three-bit parity,
then injects one held-out error and verifies that it is detected. It and Ruff
checks pass.

## Translation test of the two changing nine-position equations

`header_parity_translation.py` freezes the two nine-position shapes and moves
each across native carrier positions in the same OFDM symbol. Pilot/gutter
positions are excluded. Each translated equation learns its fixed XOR value
from discovery, allowing a position-dependent fixed mask, then tests the later
frames. This reuses the existing observations and is exploratory, not an
independent validation of the original candidate selection.

Of 1,849 allowed translations, 437 have all 78 reference frames qualified and
all nine constituents changing in discovery. Exactly two have constant parity
across all reference frames: the two original equations at translation zero.
Both also pass the seven raw frames as already reported. No other eligible
translation passes. Thus the candidate is not a demonstrated sliding parity
rule across frequency; fixed block boundaries or conditional layouts remain
possible.

Each original nine-bit block has affine rank eight, 27 distinct patterns in
78 reference frames, and ten evaluation patterns not seen in discovery. Rank
eight means that within those nine coordinates there is exactly one independent
affine parity constraint in this sample. It cannot be reduced to a smaller
subset parity constraint among those same coordinates. This is stronger than
merely replaying a few discovery patterns, but still does not identify a
transmitter code or assign meanings to the eight degrees of freedom.

The exact coordinates are absent from the common carrier coverage of all eleven
cached DS7/DS8/DS9 paired decodes. That is a coverage audit of these decoder caches,
not a claim about every raw recording in the three datasets. No missing carrier
is filled in or substituted for a direct local validation. The full translation
results, original-pattern diversity, cache coverage, and source hashes are saved
in ignored `local/header_parity_translation.json`.

A synthetic test verifies that parity is frozen from discovery, a later injected
error is detected, and an unqualified observation is excluded with the correct
denominator. The test and Ruff checks pass. No new data were collected or downloaded.

## Fixed affine predictor around the candidate positions

`header_block_predictor.py` selects independent carrier columns using only the
first 39 reference frames, then expresses every other column as a fixed XOR of
those columns plus a constant. Those exact rules predict the later 39 frames
and the seven existing raw frames. All discovery blocks and later reference
predictions pass the hard-axis quality gate; predictions are not repaired or
refitted using later data.

| Symbol-2 native bins, inclusive | Width | Discovery rank | Combined rank | Exact later-reference rules / rules tested | Exact raw rules |
|---|---:|---:|---:|---:|---:|
| 901–937 | 37 | 16 | 22 | 7 / 21 | 21 / 21 |
| 880–993 | 114 | 24 | 39 | 11 / 90 | 90 / 90 |
| 888–1001 | 114 | 26 | 41 | 11 / 88 | 88 / 88 |

The two 114-position windows exceed the rank-32 bound when later reference
frames are included. Under the tested fixed affine mapping, fixed mask, and
hard-decision assumptions, neither is a 32-input encoded block. This rejects
these two locations and layouts, not every possible header encoding. Bit errors,
variable masks, and state-dependent mappings remain outside the model.

The smaller 37-position block also gains six dimensions. Its seven surviving
rules include three copies and four higher-order relationships. The two wider
blocks each retain seven constant outputs and four higher-order relationships.
These partial constraints do not reconstruct the entire neighborhood from the
discovery inputs. Empirical basis bits are not claimed to be transmitter input
bits, MAC fields, or an eight-bit message inferred from a nine-bit equation.

The raw sample passes even the many rules that fail on the later reference
frames. This is a concrete warning that those seven raw frames do not exercise
enough states to validate the whole block model. Different processing paths
alone cannot replace adequate message diversity.

The ignored `local/header_block_predictor.json` contains every frozen XOR rule,
carrier order, per-rule evaluation errors and qualification counts, basis
positions, combined ranks, and source hashes. A synthetic affine-code test
checks prediction on held-out frames and detection of an injected output error.
It and Ruff checks pass. No new recording or download was used.

## Rectangular time/frequency layouts

`header_rectangle_rank.py` tests whether a 114-bit block is spread across
multiple OFDM symbols: 57 contiguous carriers in two symbols, 38 in three, or
19 in six. Every subset of the first six candidate header symbols (2–7) is
included. Native-bin runs must be contiguous and exclude pilots/gutters.
Permuting positions inside a rectangle cannot change rank, so separate
time-major, carrier-major, or reversed order tests are unnecessary for this bound.

As before, discovery requires all 39 frames qualified, at least 64 changing
columns, and affine rank at most 32. Evaluation checks the other 39 frames,
requiring qualification throughout the block. The exact binary rank bound is
sensitive to sign errors and assumes a fixed mask and encoder state.

| Symbols × carriers | Starts | Qualified discovery | Changing support | Discovery rank ≤32 | Also evaluation quality | Combined rank ≤32 |
|---|---:|---:|---:|---:|---:|---:|
| 2 × 57 | 12,900 | 12,900 | 12,105 | 504 | 411 | 153 |
| 3 × 38 | 17,960 | 17,960 | 17,814 | 79 | 57 | 0 |
| 6 × 19 | 950 | 936 | 936 | 0 | 0 | 0 |

Neither narrower rectangle supplies a fully qualified candidate under the tested
model. Twenty-two discovery candidates in the three-symbol layout lack full
evaluation quality and are unresolved rather than rank-rejected. Fourteen
six-symbol rectangles fail discovery quality. This is not a blanket exclusion
of all time-interleaved encoders or narrowband decoding.

The two-symbol survivors comprise 96 starts in symbols 2/3 and 57 in symbols
2/4. Their ranks range from 16 to 32. Neither component symbol is constant;
their individual ranks sum to between one and six more than the combined rank,
showing some shared variation. Limited message diversity and conditional
templates remain alternative explanations. These are candidate layouts, not a
recovered encoder or decoded source bits.

At the established 234,375 Hz subcarrier spacing, 57 carrier centers span
13.125 MHz, while 38 span 8.672 MHz and 19 span 4.219 MHz. These are center-to-center
spans, not required receiver bandwidths including guards. The two-symbol
candidates therefore exceed a 10 MS/s complex receiver's instantaneous span.
This test uses the existing full-band reference, with no new RF or download.

Detailed starts, symbol subsets, ranks, and hashes are saved in ignored
`local/header_rectangle_rank.json`. A test checks rectangular extraction and
rank invariance under column permutation. It and Ruff checks pass.

## Raw-frame transfer of the two-symbol candidates

`header_rectangle_transfer.py` fits explicit affine relations to all 78 reference
frames for the 153 surviving rectangles. It retains relations involving both
symbols, deduplicates them by their actual coordinates, and evaluates them on
the existing seven separately processed raw frames. This is a follow-up after
reference selection, not another held-out test within the same 78 frames.

All 2,847 distinct mixed-symbol equations have at least four qualified raw frames
and zero qualified parity errors. Sixty equations have changing constituents in
both symbols in the raw sample; the others do not exercise both sides this way.
The sixty equations have weights six through eleven, rather than being simple
copies between symbols. They are dependent equations, not 2,847 independent tests.

For example, the XOR of symbol-2 bins 600 and 603 and symbol-3 bins 600, 601,
612, and 627 equals zero throughout the reference and all seven qualified raw
frames. Four of its six constituents vary in the raw sample. This remains an
empirical relation, not a verified encoder parity check.

The stricter whole-rectangle raw quality gate admits two to six raw frames per
rectangle. Adding these to the reference data increases rank in none of the 153
rectangles. Eighty-one windows contain no novel qualified raw word, so their
whole-block transfer simply repeats already observed patterns. The remaining
72 do contain new words: 31 have one, 30 have two, six have five, and five have
six. Their unchanged rank shows those new observations lie in the previously
observed affine subspace, a useful structural lead beyond exact word repetition.

This does not identify source bits, interleaving, polynomial generators, or MAC
fields. A conditional template family or limited message states can also occupy
an affine subspace. All samples are from one public acquisition; overlapping
windows and shared frames limit the independence of these confirmations.

The ignored `local/header_rectangle_transfer.json` retains every equation,
raw support, varying-symbol information, whole-block ranks, novel-word counts,
and source hashes. The companion test checks mixed-symbol classification;
the existing affine-predictor tests cover fitting and evaluation. Tests and
Ruff checks pass. No data were collected, downloaded, or altered by this test.

## Short convolutional-rule search in the two-symbol rectangles

`rectangle_convolution_probe.py` tests the 153 surviving rectangles for a
three-output-stream, seven-tap convolutional relationship without assuming
particular generator polynomials. The 114 positions become 38 output triples.
For each output-stream pair, a binary null-space test seeks a seven-tap check
using variable positions from both streams, repeated over all 32 usable triple
positions in each discovery frame difference. Frame XOR removes any fixed mask.

The search covers both symbol directions, both carrier directions, symbol-major
and carrier-major serialization, and interleaved versus three-block stream
assignment. Across 7,344 rectangle/layout/stream-pair configurations, **no exact
discovery check is found**. Each configuration supplies 1,216 windows from 38
discovery frame differences. Consequently no check proceeds to later-frame
evaluation.

Thus the previously observed low-rank structure does not supply a short
convolutional decoding rule under these mappings. This is a restricted negative:
other interleavers, longer memories, state-dependent masks, different code
families, and decision errors remain possible. The earlier firmware dimensions
alone do not establish a convolutional code. The rectangles were already selected
using all 78 reference frames, so this is exploratory model diagnosis, not an
independent significance test.

The ignored `local/rectangle_convolution_probe.json` records trial counts, scope,
and input hashes. A synthetic two-generator example verifies discovery of a
mixed-stream relation and detection of one injected parity error. It and Ruff
checks pass. No raw data or native decoder output was changed.

## Check against the known 60-state sequence

`rectangle_sequence_test.py` tests whether the surviving two-symbol rectangles
are instances of the already understood cyclic sequence. It uses the established
compact-carrier slot mapping `(carrier_index − 16 × OFDM_symbol) mod 60`.
For each frame, phase and polarity are chosen from the first 28 positions of the
rectangle, then frozen to predict the other 86 positions across both symbols.
The test does not fit a new alignment, mask, or generator.

Across 153 overlapping rectangles and 78 frames there are 321 exact complete
matches out of 11,934 rectangle/frame instances. **Every exact match is a
constant-sign block**; no nonconstant rectangle matches exactly. These constant
matches therefore do not establish recovery of changing information.

Using the first 39 frames only to select changing coordinates, the later 39
frames supply 375,258 held-out-position comparisons. The generator disagrees
with 46.78%, compared with 47.84% for a constant-sign prediction selected from
the same first 28 positions. The generator beats that baseline in only 77 of
153 windows. The overlapping observations are dependent and these are model
disagreement rates, not transmitter BER estimates or independent trials.

The known sequence under its established alignment does not provide an adequate
decoder for the changing rectangular header structure. This rejects that
particular explanation, not every possible shifted or masked sequence family.
The existing tail-sequence recovery remains separate evidence.

Detailed per-window errors, fitted phases, polarities, and hashes are saved in
ignored `local/rectangle_sequence_test.json`. A synthetic test verifies recovery
of a known phase/polarity and ensures changing held-out positions cannot affect
the fitted prediction. It and Ruff checks pass. No new data were acquired.

## Frame-pairing control narrows the two-symbol lead

`rectangle_rank_control.py` holds the first symbol fixed and circularly shifts
the second symbol's 78-frame sequence by every nonzero offset. This preserves
each symbol's observed words, frequencies, and cyclic temporal ordering while
breaking the actual cross-symbol pairing. It tests all 153 previously selected
windows. These are descriptive controls, not an independent search or calibrated
significance test; circular shifts and overlapping windows are dependent.

- In 139 windows, the actual paired rank is lower than every shifted rank.
- In 105 windows, every shifted rank is nevertheless still at most 32. Their
  passing the 32-input bound is therefore weak evidence for joint encoding.
- In 37 windows, every shifted rank exceeds 32 while the actual rank is at most
  32. These windows depend on correct frame pairing to satisfy that bound.
- Eleven windows have a mixture of shifted ranks above and below the bound.
  Across all shifted tests, 69.26% still satisfy the bound.

The 37 narrower candidates are 57-carrier rectangles with native start bins:

| OFDM symbols | Start bins, inclusive ranges |
|---|---|
| 2 and 3 | 723–725 |
| 2 and 4 | 872–884 and 891–911 |

This prioritizes locations for inspecting shared information across symbols. It
does not prove FEC: common scheduling or message states can also reduce joint
rank. Nor does it turn the surviving affine coordinates into decoded input bits.
The full list of 77 shifted ranks per window is retained in ignored
`local/rectangle_rank_control.json`, together with source hashes.

A synthetic test checks rank reduction for matched columns, its loss when the
frames are shifted, and invariance under a fixed XOR offset. It and Ruff checks
pass. No new recording, download, or native decoder change was made.

## Shared coordinates resolve into nine observed states

`shared_header_coordinates.py` extracts the mixed-symbol equations in the 37
pairing-dependent windows and separates each into a left-symbol XOR and a
right-symbol XOR plus a fixed offset. It saves the explicit carrier sets and
their reference and raw bit sequences. These are empirical binary coordinates,
not claimed transmitter input bits.

After grouping equal reference traces up to inversion, there are 70 distinct
changing traces. Their union has binary rank eight. Crucially, their joint
78-frame sequence occupies only **nine distinct states**, with sorted occurrence
counts 1, 1, 1, 2, 2, 3, 14, 26, and 28. Rank eight is already the largest affine
rank possible for nine states; it does not establish eight independently variable
information bits. The grouping identifies a small observed state family, whose
meaning and behavior beyond this acquisition remain unknown.

All 70 selected coordinate representatives pass their qualified raw equality
checks. However, none changes value among its qualified raw frames. Thus the
short raw sample does not validate changing shared-state behavior. Earlier
reports that some constituent bits vary in both symbols do not imply their
combined shared XOR varies. Likewise, new complete rectangle words can differ
in symbol-specific information while preserving the same shared state.

This weakens an interpretation of the low-rank candidates as evidence of a
32-input encoder. It provides a more concrete next target: determine whether
these nine shared states track a header mode or another conditional structure,
without labeling them as decoded protocol fields. The states were identified
on all 78 reference frames; no independent semantic validation is claimed.

The ignored `local/shared_header_coordinates.json` stores all 70 representative
equations, sign conventions, full traces, raw validity masks, per-frame state
indices, occurrence counts, and hashes. State indices are assigned by first
appearance and carry no semantic meaning. A synthetic test recovers one known
shared coordinate with a fixed inversion. It and Ruff checks pass. No new data
were acquired and the native decoder was not changed.

## Shared-state persistence and frame structure

`shared_state_structure.py` compares the nine-state sequence with the previously
measured sign-independent tail boundary and early hard-axis region. Only the
first 13 frames have these structural measurements; they contain four of the
nine states. The early hard-axis endpoint is a signal-processing diagnostic,
not a decoded header length.

Across all 78 frames, the labels form 32 consecutive runs, with a longest run
of eight frames. Adjacent labels match 59.74% of the time. Uniformly reordering
the same label counts gives an expected adjacent-match fraction of 26.61%.
This demonstrates descriptive temporal persistence; it is not a permutation
significance test, and state labels were fitted on the same recording.

The observed states do not determine either structural measurement:

| State | Measured frames | Tail boundary range, compact positions | Early hard-axis last symbols |
|---|---|---|---|
| 0 | 0, 2 | 63,353–122,564 | 14, 14 |
| 1 | 1, 3, 4 | 10,696–46,855 | 7, 24, 7 |
| 2 | 5–10 | 31,814–117,649 | 7, 10, 7, 9, 9, 9 |
| 3 | 11, 12 | 106,066–149,190 | 10, 10 |

Predicting each measured frame from the median of its other same-state frames
gives a tail-boundary mean absolute error of 38,293 positions, versus 41,126
using all other frames. For the early hard-axis endpoint, errors are 3.00 versus
3.04 symbols. These small-sample exploratory comparisons do not establish a
useful length decoder. Leave-one-out prediction does not undo the earlier
exploratory selection of the states.

The states could reflect a persistent mode, conditional message structure, or
another shared source of variation; none is established. Their indices must not
be labeled as satellite IDs, timing fields, or encoded lengths. Detailed runs,
frame associations, errors, and hashes are in ignored
`local/shared_state_structure.json`. Two tests verify run segmentation and
exclusion of the target observation from prediction. Tests and Ruff checks pass.

## State-conditioned prediction outside the defining symbols

`state_conditioned_header.py` trains per-state majority-bit templates on the
first 39 reference frames and evaluates them on the later 39. It predicts only
symbols 5–7, completely excluding symbols 2–4 used to define the shared states.
Only positions with discovery positive-sign frequency between 20% and 80% are
evaluated, so fixed bits cannot dominate the result. Each prediction also
requires at least three qualified training observations in that state. The
comparison baseline is one majority template fitted to all discovery frames.

| Predicted symbol | Qualified changing-position decisions | State-conditioned disagreement | Global-template disagreement |
|---|---:|---:|---:|
| 5 | 28,235 | 44.70% | 47.11% |
| 6 | 28,028 | 40.12% | 44.98% |
| 7 | 29,511 | 46.46% | 48.08% |

Eight evaluation frames contain states absent from discovery and are left
unpredicted: 47, 67, 68, 71, 73, 75, 76, and 77. The other 31 frames supply
the comparison. No template is fitted to evaluation bits.

The state captures some association with distant header symbols, but the
remaining disagreement is too large to supply a decoder for their changing
bits. This modest gain does not establish a mode field or its semantics.
Furthermore, the state definitions themselves were discovered using all 78
frames, so separating template training and prediction does not make this a
fully independent validation. The reported values are disagreement with the
reference hard decisions, not independently verified transmitter BER.

The ignored `local/state_conditioned_header.json` stores per-frame counts,
errors, abstentions, and input hashes. A synthetic test checks per-state fitting
and exclusion of unqualified observations from training support. It and Ruff
checks pass. No new data were collected or downloaded.

## Convolutional search after canceling state-dependent masks

The chronological split has discovery state counts 23, 11, 3, and 2. The two
most common discovery states have only five and fifteen later examples,
respectively. This is insufficient to identify a separate general 32-input
encoder for each state reliably.

Instead, `rectangle_convolution_probe.py --state-conditioned` tests a common
short convolutional code with a fixed XOR mask that may differ by state. Each
discovery state uses its first discovery frame as a frozen anchor. Only frames
of that same state are XORed with that anchor, so any fixed state-dependent
mask cancels. This produces 35 discovery difference frames and 31 later
difference frames; the eight later frames with unseen states are excluded.

Across the same 153 rectangles and 7,344 serialization/stream-pair configurations,
no exact mixed seven-tap discovery check is found. Each configuration tests
1,120 discovery windows. No check proceeds to later-frame evaluation. Thus
introducing a fixed mask per observed state does not rescue this particular
three-stream, short-convolutional model.

Other interleavers, longer memories, different encoders between states,
frame-varying masks, and decision errors remain outside this test. The states
were identified using all 78 frames, so the result remains exploratory.
Detailed counts and hashes are in ignored
`local/rectangle_convolution_state_conditioned.json`. The original unconditioned
result is preserved. A new synthetic test verifies cancellation of distinct
state masks, use of discovery anchors, and abstention for an unseen state.
Both convolution-probe tests and Ruff checks pass. No new data were acquired.

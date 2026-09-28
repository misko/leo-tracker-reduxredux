# DS7 raw-bit recovery and field interpretation

## Result

Recovered complete 60-bit physical-layer repetition patterns in 38 tested
frames from two existing DS7 visits. Both receivers independently recovered
the same 60 signs in every tested frame. This is evidence for transmitted
non-pilot bits, not a decoded packet or a satellite identifier. The user's
request for raw bits **and interpreted fields remains incomplete**: no
satellite ID, UTC timestamp, position, or orbit field has been validated.

All IQ, decoded bit exports, and figures are git-ignored under `local/`.
No new RF collection, production component change, or data commit was made.

## Evidence and scope

Cached pilot candidates from all 19 DS7 10 MS/s recordings were surveyed,
without scanning their full IQ. Strong candidates selected using pilots alone
were exported through the pinned read-only storage reader with source hash
validation. This is a targeted investigation, not an exhaustive waveform survey.

| Local group | Session | Visit | Edge | T-code frames tested/passed |
|---|---|---:|---|---:|
| best-upper | scan-fw-a2d5dadd1a63c960 | 191 | upper, channel 4 | 14/14 |
| holdout-upper | scan-fw-a2d5dadd1a63c960 | 208 | upper, channel 4 | 24/24 |
| best-lower | scan-fw-0da0bd80eeec99cf | 947 | lower, channel 4 | not qualified for this decoder |

Each export contains 120 ms from both receivers, sampled at 10 MS/s, with 89
complete frame windows. Visit 208 was selected before inspecting its unknown
header bits. These are two visits in one recording, not two independent
satellite identifications or two independent recording sessions.

`tcodes.py` implements the 60-bit frequency repetition and 16-position
symbol-to-symbol shift described by [Qin et al.](https://www.nature.com/articles/s44459-026-00075-6).
Their explanation involving unladen allocations and coding/scrambling is a
conjecture; this result does not establish its payload origin.

The captured 24 non-pilot upper-edge carriers have compact frequency indices
976–999 after omitting pilots and gutter. Repeated observations over 64 OFDM
symbols cover every position of the 60-bit pattern, despite the narrow
instantaneous bandwidth. Eight candidate windows are considered. RX0 even
rows fit a code and RX0 odd rows select the window. RX1 then independently
estimates the code and tests correlation with RX0's result. Known pilots and
SSS determine channel/phase corrections; no per-bit phase rotation is fitted.

Every accepted RX1 score exceeds all 1,000 Hamming-weight-preserving shuffled
code controls. These exploratory controls are not calibrated false-alarm
probabilities. All four even/odd receiver splits agree on every bit in 35 of
38 frames. In the remaining three frames, at least one half differs; the full
RX1 estimate still agrees with RX0 on all 60. Receiver agreement is strong
evidence, but is not a CRC or a mathematical guarantee of error-free bits.

The lower-edge finite-vector wrap needs a different mapping and is explicitly
rejected by this decoder. The clean UT exemplar's seven complete frames do
not show a qualifying post-header T-code window. It is a negative applicability
check here, not a positive T-code reference. Synthetic known-code and noise
tests provide separate numerical checks.

## Independent published-code comparison

The [UT supplementary dataset](https://rnl-data.ae.utexas.edu/datastore/supplementaryMaterial/qin-starlink-pilots/exemplar-frames-data/)
provides independently demodulated hard constellation symbols. A bounded
HTTP-range read retrieved 24 upper-edge carriers for zero-based dataset
frames 806–818, covering the paper's T-code example. It transferred only
119,056 bytes from the 5,415,856,507-byte HDF5/MAT file in 8.7 seconds. The
ETag was checked throughout; local output has a SHA-256 digest. These are
published constellation decisions, not a newly downloaded raw-IQ recording.

All 13 reference frames yield exact repetition scores of 1.0 on the selected
64-symbol windows. **Ten of the 13 have an exact code-family match to DS7**
under cyclic rotation and global sign inversion. These cover six distinct
families and 12 DS7 frame observations. The other three reference frames
are 14 bits away from their nearest DS7 code under the same equivalence.
No arbitrary bit corrections are allowed in the comparison.

This independently validates the matched DS7 patterns as members of the
published T-code family. It does not transfer the reference capture's satellite
identity to DS7: no unique mapping from code to satellite is established.
It also does not reveal user data, header FEC, or field semantics.

`fetch_ut_reference.py` enforces a 16 MiB transfer limit and a 110-second
internal time bound with 10-second HTTP timeouts; use an outer 125-second
timeout. It requires h5py and NumPy. `compare_published_codes.py` uses the
existing NumPy/SciPy environment and verifies the extracted file's hash.
Both outputs remain ignored under `local/ut-reference/` and
`local/published-code-comparison.json`. The normal tests verify that rotation
and inversion match, while a one-bit error cannot qualify as an exact match.

## Header pattern and rejected timing hypothesis

Symbol 4, with SSS numbered 1, contains a stable 24-position sign pattern in
visit 208. Its two groups occupy bins 476–487 and 496–507, separated by pilots.
The values and bootstrap evidence are in
`local/holdout-upper/recurring-words.json`. Positive/negative signs are displayed
as 1/0 relative to the published template and SSS phase convention. Packed hex
is only a display convention: these are not established contiguous packet bytes.

A proposed three-frame cycle from visit 191 was frozen before examining visit
208. That proposal **failed**: both validation phase groups yielded the same
24-position pattern, including the group predicted to differ. It must not be
interpreted as a frame counter or timing field. Group averaging supports a
stable pattern; it does not establish every individual frame's header bits.

Reserved known-pilot BPSK-equivalent sign error rates after combining receivers
are 7.25% for best-upper, 8.78% for best-lower, and 12.99% for the earlier visit
2022. These are calibration diagnostics, not measured header BER. Repetition
combining is what makes the T-code estimates substantially more reliable.

## Field interpretation audit

### Prospective even-parity test

All initial 18 codewords had an even number of one bits. The hypothesis that
the XOR of all 60 positions equals zero was frozen in ignored
`local/even-parity-hypothesis.json` before recovering visit-208 frames 4–23.
Every one of those 20 additional frames passes the original candidate gates,
agrees between receivers on all 60 bits, and satisfies even parity in each
receiver independently. Six previously unseen cyclic rotation classes occur
in this validation set. The complete set contains 38 frame observations,
27 distinct words, and 21 distinct cyclic rotation classes.

This establishes an empirical constraint for these tested patterns: any one
bit can be predicted as the XOR of the other 59. It does not establish a
designated parity bit, a complete error-correcting code, a CRC, or a semantic
field. Repeated/cyclically related words are dependent; a probability based
on 20 independent fair-bit trials would be inappropriate. A synthetic check
confirms that the recovery algorithm accepts odd-parity words as well, so it
does not impose this constraint. `audit_code_parity.py` exports the complete
validation, source hashes, and dependence caveat to
`local/even-parity-validation.json`.

### Cross-recording header comparison

An additional edge-inclusive UT export now covers all 1,004 non-pilot loaded
carriers. The earlier UT soft export deliberately retained only 857 central
carriers and therefore could not compare DS7's upper-edge header positions.
Using the same 24 bins and OFDM symbol 4, all seven complete UT frames yield
one identical sign pattern. It differs from the DS7 visit-208 pattern at 10
of 24 positions (14 if globally inverted). Minimum absolute real component
in those UT observations is 0.622 in normalized units, so these are not
decisions sitting on the zero threshold.

This rejects a universal fixed sign pattern at those positions under the
current template convention. It does not distinguish configuration, coding,
beam, identity, or other causes of the cross-recording difference. UT's blind
axis alignment retains a global polarity ambiguity; both polarities were
checked. No per-bit rotations or flips were used to force agreement.
`compare_ut_header.py` saves the actual patterns and source hashes to ignored
`local/ut-ds7-header-comparison.json`. Reproduce its UT prerequisite with:

```sh
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy --with matplotlib python reports/2026_09_27_ut_header/analyze.py --carrier-limit .5 --out reports/2026_09_27_ut_header/local/fullband
.venv/bin/python reports/2026_09_27_ds7_header/compare_ut_header.py
```

### Rejected seed-only model

The 38 recovered words have binary linear rank 27 and affine rank 26. For
the fixed model `word = A * seed XOR constant`, with all operations over GF(2),
a 15-bit seed can produce affine rank at most 15. Thus a fixed linear encoder
driven solely by a changing 15-bit seed and otherwise constant data cannot
explain these aligned words. This remains conditional on their recovered signs
and the common position convention; varying mapping, multiple seeds, variable
input data, or nonlinear processing are not excluded. It does not rule out a
15-stage LFSR elsewhere in the transmitter, and rank is not payload entropy
or a decoded field width.

`code_model_audit.py` computes exact GF(2) rank and saves source hashes and
limitations in ignored `local/code-model-audit.json`. Its tests distinguish
binary rank from ordinary real-valued rank and check the affine seed bound.
This narrows the model search; it does not invert the actual transmitter code.

### Patent applicability

A check of the primary
[US12003350B1 patent](https://patents.google.com/patent/US12003350B1/en)
locates the explicit 27-bit first-PDU and 23-bit later-PDU headers in its
**SAT–SAG DL** discussion: the satellite-to-gateway mode. Applying these
lengths directly to our satellite-to-user Ku header is therefore unverified.
The patent also says these lengths may vary. Secondary summaries that omit
the link mode are insufficient grounds for fixing a Ku decoder's layout.

The [SpaceX modem patent US12074683B1](https://patents.google.com/patent/US12074683B1/en)
describes BPSK PHY PDU headers with rate-1/3 nonrecursive, nonsystematic
convolutional coding and six memory bits. It names sequence number, partial,
MCS length, and MCS fields. These are useful hypotheses, not proof that the
observed early OFDM header uses that exact layout. The reviewed text does not
establish the generator polynomials, on-air resource-element mapping, or a
validated decoder for our captures. The cited header field list does not
identify a satellite ID, UTC timestamp, or ephemeris field.

### Direct convolutional-code probe

`header_code_probe.py` tests a restricted rate-1/3, constraint-length-7
serialization hypothesis using the clean UT header. It XORs frame pairs to
cancel the fixed template, then searches all even-weight parity checks over
seven positions of each of two hypothesized encoder output streams. It tests
three triplet phases, three stream pairs, both frequency directions, and
physical-frequency versus native-FFT ordering. Checks require both streams
to contribute. Each window stays within one OFDM symbol. Symbols 3, 5, 6, and
7 are used; the conspicuously static symbols 2 and 4 are excluded.

Frames 250/251 select the check; 252/253 and 254/255 independently evaluate it
without choosing another check. The selected correlation is 0.224 in discovery,
0.165 in validation, and 0.157 in the final pair. For a positive parity check,
these last two scores mean only 58.2% and 57.9% of windows satisfy the relation.
There is weak structure, but no reliable parity equation for a decoder.
The known-code synthetic test recovers a relation that holds in 100% of an
independent noiseless encoded stream; a separate noise control fails to
generalize. This result does not exclude convolutional coding: unknown
interleaving, scrambling, variable boundaries, puncturing, or residual errors
can invalidate the tested serialization. No generators or information fields
were recovered. Ignored `local/header-code-probe.json` preserves all 36
layout trials and the source hash.

Consequently, applying an arbitrary Viterbi code or splitting our 60-bit pattern
into plausible integers would produce unsupported interpretations. T-codes
occur in later repeated allocations; they must not be equated with PHY PDU
headers merely because both contain recoverable signs.

| Requested information | Current evidence | Missing validation |
|---|---|---|
| Raw non-pilot bits | Complete repeated 60-bit patterns; stable 24-position header pattern | Packet framing/FEC/CRC for header interpretation |
| Satellite ID | No decoded field | Documented mapping and independent identity association |
| Timing | Sample-relative frame epochs from synchronization | A decoded absolute time field and independent clock check |
| Position/orbit | No decoded field | Message layout, units, time reference, independent ephemeris check |
| MCS/sequence metadata | Patent suggests possible fields | Actual coding and carrier/time mapping, then held-out re-encoding validation |

The next useful experiment is to determine the complete header resource mapping
on the full-band UT recording before attempting its restricted DS7 projection.
Any candidate interpretation must predict withheld RF observations; plausible
numbers alone are insufficient. Recovering missing arbitrary wideband payload
bits from this narrowband slice is not implied by the repeated-code result.

## Reproduction and artifacts

### Completion audit and unresolved reference

The requested outcome includes both raw bits and interpreted fields. Current
artifacts prove 38 qualifying repeated-code observations, agreement between
receivers, and exact matches to six published code families. They do not prove
any decoded satellite ID, absolute time, position, orbit, MCS, or sequence field.
The goal is therefore not complete.

A targeted public search and inspection of the local research/analysis sources
found no verified Ku header field decoder to apply. This is a bounded search
result, not a claim that none exists anywhere. The primary Qin paper explicitly
does not interpret header contents semantically. Its constellation decisions
and reference templates supply RF ground truth, not labeled message fields.
The tested patent and direct-serialization hypotheses do not fill that gap.

The remaining obstacle is an external validation reference: an applicable
header layout/decoder, known transmitted field values paired with RF, or
terminal logs tied to an appropriate capture. A request for such material is
pending with the user. No additional collection is authorized or running.
No field values will be assigned from pattern appearance, code-family matches,
or plausible integer values alone. This is an evidence limit of the current
investigation, not a proof that blind reverse engineering is impossible.

Run numerical scripts with one BLAS thread in a NumPy/SciPy environment:

```sh
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_27_ds7_header/tcodes.py --group best-upper --frames 14
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_27_ds7_header/tcodes.py --group holdout-upper --frames 24
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy --with matplotlib python reports/2026_09_27_ds7_header/plot_tcodes.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_27_ds7_header -p 'test_*.py'
```

Prerequisites are the local exports and calibrated recovery outputs produced by
`export_best_edges.py` and `recover.py`; acquisition uses the pinned reader
release documented in README.md, not a reference repository runtime import.

- `local/{best-upper,holdout-upper}/recovered-tcodes.csv`: raw 60-bit strings,
  display hex, frame/window indices, receiver agreement and correlation.
- `local/{best-upper,holdout-upper}/tcodes.json`: detailed decisions and controls.
- `local/{best-upper,holdout-upper}/tcode-soft-evidence.npz`: observed complex
  values, mapping, and per-bit means, permitting inspection without hard slicing.
- `local/best-upper/recovered-tcode-iq.png`: observed IQ before/after repetition
  combining; the plotted means are not snapped to ideal constellation points.
- `local/holdout-upper/recurring-words.json`: prospective header-pattern test,
  including rejection of the proposed cycle.
- `local/survey/{cached-candidates,decision-audit}.json`: survey and held-out
  known-pilot diagnostics.
- Group `inventory.json` files bind the IQ excerpts to sealed source digests.

Earlier negative assays and soft recovery remain in README.md and RECOVERY.md
as historical results, superseded where explicitly described above.

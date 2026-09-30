# Firmware fields and observed signal associations

Checkpoint: September 30, 2026. The firmware audit establishes several serialized
control-message formats and conditional receive paths. The recording analysis
establishes known T-code and some shared early-symbol variation. **No recovered
RF feature has yet been mapped to a decoded message field or a satellite ID.**
This remains an active investigation; the historical association inventory is
not yet a completed semantic review of every receipt.

## What the executed firmware constrains

![Four verified conditional SYSINFO layouts](local/serialized-layout.png)

The figure is generated from the independently checked layout receipts by
`serialized_layout_figure.py`. Its offsets precede PHY coding. It is not an OFDM
map and does not assume one recovered sign equals one uncoded message bit.

| Verified constraint | Consequence for interpretation |
| --- | --- |
| Type-0 SYSINFO preserves a full 32-bit SATAddr and two 8-bit channels | A small cluster count is not evidence of the complete address. No NORAD equivalence is established. |
| Optional timing has 4-bit GroupFact, 4-bit GroupId, 32-bit RFNum and 32-bit ULTxTimeOffset | Widths constrain a future decoded message. They do not establish counter cadence or RF sign periods. |
| Optional ephemeris preserves 352 bits and shifts later fields by that amount | A fixed timing offset cannot be used across both optional layouts. Numeric plausibility alone does not validate the message. |
| PNT variance uses a custom unsigned 6-exponent/10-fraction representation | An IEEE-half interpretation is wrong; units and RF location still need evidence. |
| PNT telemetry attaches its ID from context | The telemetry schema does not imply PNT transmits an ID. |
| Type-15 UTGW SYSINFO can update that context in a particular mode; zero can be stored as valid | Type 15 must be distinguished from type 0. A context value is not automatically a unique physical-satellite label. |
| Decoder output can be partially written on failure; trailing padding values can be nonzero | A plausible output value or padding pattern is not a successful or authenticated decode. |
| TX reserves zero trailers and a downstream descriptor builder excludes matching byte counts in its ordinary branch | Supports later checksum insertion, but no verified checksum algorithm or RF mapping follows. Signaling mode has separate length rules. |
| ULMAP diagnostics name grant SID, index, symbol offset/count, resource-block offset/count and MCS | Refines the grant-handler's ambiguous OFDM names. Resource allocation is supported; RF locations and satellite identity are not established. MCS is separate from the five packed descriptor fields. |
| A queued grant is checked against session ID and a modulo-750 RF counter | A concrete scheduling constraint, but no proved correspondence to SYSINFO RFNum, recording sessions or an RF sign period. |
| Grant satellite validation compares stored and expected identity context, with zero bypasses | A satellite-mismatch diagnostic does not prove that each grant carries a satellite address. Identity association can depend on earlier context. |

Raw instruction windows, executions, conditions and limitations are in
[the parser and consumer audit](PARSER_GATE.md). The configuration enum controlling
UTGW routing has not been equated with the separately audited PHY role enum.

## How these constraints bear on the association families

The searchable ledger contains 685 entries across 31 named kinds. These include
hypotheses, negative findings and abstentions; neither number counts independent
discoveries. This table groups related kinds for interpretation. Coordinate-level
evidence and original falsifiers remain in the [searchable review](local/review.html).

| Association family | Firmware interpretation that remains plausible | What the current evidence does and does not establish |
| --- | --- | --- |
| T-state consistency, known vocabulary, unmatched words, known-state residual prediction | Shared waveform sequence and recovery errors | T-code is separately explained. Near-neighbor words do not establish new message fields; sparse state recurrence limits categorical tests. |
| Phase-profile dendrograms, change-trace edges/components, phase distributions | Shared waveform state, channel/calibration structure, or unknown modulation | Software enum widths cannot label the splits. Order-discarding distributions cannot locate fields; many tree comparisons are sensitive to ties or corpus composition. |
| Frozen symbol pairs, paired tiles, adjacent-region partitions, profile transfer | Coding/interleaving or repeated data, if independently transferable | No verified software-to-PHY mapping assigns these pairs to parity or copied header bits. Frozen-transfer negatives remain negative; a newly known field width does not rescue them. |
| Metadata distances, candidate contrasts, episode retrieval, stable coordinates, bandwidth contrasts | Satellite, channel, beam or timing dependence | Candidate labels are conditional. Session/trajectory controls and sparse cross-session support limit identity claims. Context ID provenance does not validate those labels. |
| Receiver I/Q correlation, DS9 correction/phase/carrier checks, amplitude and neighbor models | Shared modulation or residual channel/calibration effects | Receiver consensus supports shared signal variation. DS9 middle Q survives the tested corrections, but no discrete message alphabet or field meaning follows. |
| Periodic-counter models | RFNum or another counter, if cadence and mapping are independently established | RFNum is 32 bits in software; its cadence is unknown. Existing periodic-model ambiguity and negative controls still prevent a counter claim. |
| Receiver combining and core/extra-carrier recovery errors | Improved recovery of known waveform components | Better known-T recovery does not establish early-header BER, plaintext, FEC parity, or identity. |

## What would connect the two sides

The missing evidence is a reproducible path from a **specific observed RF region**
through its polarity/phase convention, scrambling, interleaving and coding into
the exact bytes consumed by a verified decoder. A candidate should pass framing
and decoder status checks, then predict unused observations with frozen choices.
Identity additionally needs transfer across visits while separating different
satellites under session, channel, time and trajectory controls. SATAddr or a
contextual telemetry ID cannot be equated with NORAD by name alone.

For example, the 18-byte conditional SYSINFO form is 144 serialized bits. Its
numerical equality to six symbols times 24 recovered carriers does **not** locate
that message: neither the coded-bit ordering nor the information per recovered
coordinate is established. Searching every ordering for a plausible ID would
discard the independent constraint that made the test meaningful.

The newly executed layouts therefore improve interpretation and candidate
validation without justifying another blind RF scan. The existing negative
experiments remain recorded; neither successful software round trips nor the
absence of a positive RF test proves the recordings contain no additional data.

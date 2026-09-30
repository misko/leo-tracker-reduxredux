# Timing, satellite identity, and position leads in public firmware

2026-09-29. This investigation identifies named control messages and software
fields; it does not decode those fields from DS7, DS8, or DS9. Sources are the
previously extracted public runtime binaries and their bundled configuration.
Acquisition and authenticity limits are in [firmware-leads.md](firmware-leads.md).

## Strongest target: SYSINFO

Receive-MAC diagnostics name `mac_ut_handle_sysinfo`, report starting reception
from a satellite address, and describe protocol versions, target ID, optional
ephemeris, channel IDs, and random-access settings. A separate SYSINFO dump
routine explicitly names RFNum, SATAddr, DLChanID, ULChanID, GroupFact, GroupId,
and ULTxTimeOffset. These are much more specific identity/timing leads than the
generic GMH fields studied previously.

At routine 0xcc8e0 in the canonical `rx_lmac`, diagnostic argument construction
at 0xcca30–0xcca94 maps the following decoded-structure fields. These offsets
are **in memory**, not packet or RF offsets:

| Named quantity | Structure offset / representation |
| --- | --- |
| SATAddr | 0x01, 32-bit load |
| DLChanID / ULChanID | 0x05 / 0x06, byte loads |
| GroupFact / GroupId | Low/high nibbles of byte 0x35 |
| RFNum | 0x36, 32-bit load |
| ULTxTimeOffset | 0x3a, 32-bit load |

Do not equate SATAddr with a NORAD catalog number or the public STARLINK-name
suffix. The relationship has not been established. RFNum's diagnostic name
suggests a radio-frame number, but its tick cadence, epoch, and rollover have
not been verified here. ULTxTimeOffset's units are also unresolved.

The SYSINFO ephemeris diagnostic reads three double-precision position values
at offsets 0x08/0x10/0x18, three single-precision velocity values at
0x20/0x24/0x28, and two 32-bit timestamp components at 0x2c/0x30. It also reports
a target-center position separately. The internal burst-information schema
explicitly contains satellite ID, position/velocity components, ephemeris
seconds/nanoseconds, channel IDs, and beam-target position. Types in an internal
schema need not match the packed control message or this dump structure.

The receive path supplies substantive evidence that SYSINFO is a message worth
decoding. We have not yet traced its entire deserializer or established whether
the optional ephemeris originates directly from each received SYSINFO message,
is propagated from an earlier one, or is supplemented by other control inputs.
The dump labels it `PropEph`; do not silently treat propagated state as the
original transmitted state.

## PNT information message

The binary explicitly names `mac_ut_handle_pnt_info_msg` and logs receiving a
PNT information message. A diagnostic says it is skipped when SYSINFO is not
valid. The named contents are a version, `disable_one_way`, `disable_two_way`,
and `clock_bias_times_c_variance`.

The dump path at 0xcd308–0xcd34c reads the version byte at enclosing structure
offset 2, takes the two flags from bits 8 and 9 of the halfword there, and
passes a 16-bit value at offset 4 through converter 0xd7f20 before printing the
variance. Do not assume that converter is standard IEEE half precision: its
meaning has not been verified. The bundled internal schema exports the flags
as booleans and the variance as a double, along with satellite ID.

The diagnostic does not include satellite ID among this message's displayed
fields. Its presence in exported telemetry therefore does not prove the PNT
message transmits an ID; the receiver may attach current satellite context.
Similarly, a variance is uncertainty information, not a decoded clock bias or
an absolute transmission timestamp. “PNT” and one-way/two-way names alone do
not establish the full ranging protocol or whether outside receivers can use it.

## Ranging and satellite transmit/receive times

The bundled `phy_fsw_ranging_info_to_control` schema contains:

- `ul_rf_num`, `tx_l2_time`, and `rx_l2_time`;
- `t_sat_tx` and `t_sat_rx`, both int64;
- `corrected_toa`, `ul_freq_err`, and `ul_snr`, each int16;
- `slant_range`, a double.

PHY diagnostic 0xa2b38 names `process_ut_ranging_info_msg` and reports corrected
time of arrival, slant range, frequency error, and SNR. This establishes internal
handling of ranging information, not the source, units, wire bit widths, or
availability to a passive observer. Tracing its incoming message decoder is an
appropriate next step.

## Synchronization and ephemeris use

PHY diagnostics explicitly cover GPS-to-local-counter mapping from PPS,
conversion between peer/local counters, separate transmit and receive counters,
and correction of radio-frame start and length. One peer timing message names
`peer_phyfw_ipc_ep`; peer synchronization must not automatically be interpreted
as an over-the-air satellite timestamp.

`compute_ut_tx_rx_offset` requires both local and remote ephemerides and logs
satellite position and velocity evaluated at receive time. Other diagnostics
state that local/remote ephemerides are used for Doppler correction. The
propagation library names ECEF-related types elsewhere in the runtime, but
coordinate units, frame conventions, timestamp epochs, and transformations
still require direct code verification before comparing values with orbit data.

## Implications for the recordings

Prioritize control-message decoding, especially SYSINFO and ranging, over
assuming that satellite identity is inside the generic MAC header. The firmware
does handle the quantities we want. We still need message framing/type values,
serialization and scaling, channel coding, RF placement, and encryption-state
evidence before identifying them in recorded signs. These findings do not prove
unencrypted availability, frequency of transmission, or presence in the six
early OFDM symbols. Existing DS7+DS8+DS9 remain the authorized local corpus.

`reports/2026_09_28_sequence_semantics/firmware_timing_identity.py` verifies both
canonical binary hashes, selected extraction instructions, and captures named
diagnostics plus hashes/content of the three internal schemas. Its output is
Git-ignored `local/firmware_timing_identity.json`. All assertions and Ruff pass.
No firmware execution, new RF recording, or deployment was performed.

## Follow-up: control-message envelope and PNT body located

Subsequent isolated execution was used for the following body-writer checks;
no dish or complete firmware process was run.

The dump dispatch table at 0x12c314 identifies type 0 with the SYSINFO dump and
type 13 (0x0d) with the PNT dump. Independently, serializer 0xd7680 and decoder
0xd7990 use tables 0x12c654 and 0x12c664 for the same types. Type 0 reaches
SYSINFO encoder/decoder 0xd6a30/0xd6bb0; type 13 reaches PNT wrappers
0xd7440/0xd7460. Receive handler 0x55190 invokes decoder 0xd7990 before its
successful-path dump/handling. This identifies a typed control-message layer,
distinct from the GMH prefix. Diagnostics elsewhere call the built PNT object
an SDU, supporting control-SDU placement; its enclosing per-SDU header and RF
placement have not yet been traced end to end.

The serializer writes an 8-bit message type, initially writes three zero bits,
encodes the selected body, computes byte-alignment padding, and backpatches the
three-bit field at bit offset 8 with the padding count. The decoder reads the
same 8+3 bits and subtracts that count from the remaining body-bit budget.
Thus the three bits are padding accounting, not a message version.

The PNT wrapper skips the in-memory version byte before calling 0xd12c0. That
body routine writes widths 1, 1, and 6 from the flag byte, then delegates the
encoded variance to 0xd1240, which emits its 16 bits. For this implementation:

| Bit offset from start of serialized control message | Width | Meaning |
| --- | --- | --- |
| 0 | 8 | Type 13 / 0x0d |
| 8 | 3 | Padding count: 5 |
| 11 | 1 | `disable_one_way` |
| 12 | 1 | `disable_two_way` |
| 13 | 6 | Meaning unverified; do not assume reserved zeros |
| 19 | 16 | Encoded `clock_bias_times_c_variance`; scaling unresolved |
| 35 | 5 | Byte-alignment padding |

These offsets apply to serialized control-message bytes, with LSB-first bit
numbering within each byte. They are not offsets into an OFDM frame, a GMH, or
raw IQ. The in-memory version reported by the dump is not emitted by this PNT
wrapper; the matching decode wrapper sets that version byte to zero. No
satellite-ID field is present in this inspected PNT body. The satellite ID in
exported PNT telemetry may therefore be receiver context rather than PNT payload.

`firmware_control_envelope.py` verifies the three dispatch tables against the
canonical RX binary and executes the real writer initializer, bit writer,
PNT body writer, and flush routine in bounded Unicorn RAM. All 204 cases match
the expected five bytes, including four zero-variance examples and 200 seeded
random flag/variance patterns. Example software test vectors:

- Both flags zero, other six bits zero, encoded variance zero: `0d 05 00 00 00`.
- Only disable-one-way set: `0d 0d 00 00 00`.
- Only disable-two-way set: `0d 15 00 00 00`.
- Both set: `0d 1d 00 00 00`.

These are synthetic encoder vectors, not recovered transmissions or proof that
zero variance is a valid operational value. The harness supplies the verified
type/padding prefix and calls the body directly; it does not execute the entire
outer buffer-wrapper path. All assertions and Ruff pass. Results remain in
ignored `local/firmware_control_envelope.json` under the sequence-semantics report.
The next question is how the containing control SDU is framed and channel-coded;
searching noisy RF signs for these five bytes would not establish a decode.

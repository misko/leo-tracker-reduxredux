# Firmware-constrained full-band control-message probe

2026-09-29. Per user instruction, assume the 2026 firmware's message structure
also applies to the 2025 UT recording. That assumption does not establish its
channel coding or frequency/time placement.

## Minimal SYSINFO serialization verified

The real SYSINFO encoder at 0xd6a30 calls base encoder 0xd37e0. With the internal
extension-version byte zero, ephemeris absent, and grant section absent, the
body is 32 satellite-address bits, eight downlink-channel bits, eight uplink-
channel bits, one absent-ephemeris bit, and one absent-grants bit: 50 bits.
With the control prefix (type 0 and three padding-count bits), that is 61 bits
plus three padding bits, or eight bytes.

`firmware_control_envelope.py` now executes 100 deterministic randomized minimal
SYSINFO cases through the real writer initializer, bit writer, SYSINFO body
encoder, and flush routine. All output bytes equal the independently constructed
LSB-first representation. The existing 204 PNT cases also pass. These are
synthetic software vectors, not captured packets. Channel values and satellite
addresses are arbitrary packing inputs, not proof of valid operational ranges.
The harness supplies the envelope prefix and does not execute its outer wrapper.

| Serialized bit offset | Minimal SYSINFO field |
| --- | --- |
| 0–7 | Type 0 |
| 8–10 | Padding count 3 |
| 11–42 | Satellite address |
| 43–50 | Downlink channel |
| 51–58 | Uplink channel |
| 59 | Ephemeris-present flag, zero in this minimal form |
| 60 | Grants-present flag, zero in this minimal form |
| 61–63 | Padding |

For non-minimal forms, optional content changes later positions and length.
These positions are in the serialized control message, not the OFDM frame.

## Application to existing full-band data

`fullband_control_probe.py` reads all 13 complete reference frames, applies the
published reference rotations, and retains 40- or 64-position windows whose
hard symbols lie on the binary real axis. It excludes complete OFDM symbols
at/after the independently measured repeating-tail boundary. It tests physical
and FFT carrier order, each with both global sign polarities, and scans every
bit start. No FEC decoding, fitted interleaver, or new phase fit is applied.

Both message patterns constrain only 16 bits: the type/padding prefix and the
trailing zeros (including the two absent-section flags for minimal SYSINFO).
The other bits remain unconstrained. Consequently a match is not a packet.

| Pattern | Qualified windows across all tested layouts | Matches | Five within-frame shuffled counts | Five coordinate-preserving shuffled counts |
| --- | ---: | ---: | --- | --- |
| PNT | 505,560 | 8 | 7, 6, 9, 12, 10 | 4, 8, 2, 4, 4 |
| Minimal SYSINFO | 497,496 | 91 | 9, 15, 15, 13, 14 | 71, 40, 56, 55, 60 |

The first control permutes signs among qualified positions within a frame. The
stricter control independently permutes qualified signs across frames at each
symbol/carrier coordinate, preserving its sign counts and validity mask. It
therefore preserves stationary bit patterns while disrupting changing joint
structure. The implementation asserts that all coordinate sign counts remain
unchanged. Controls are descriptive, not independent trials or p-values.

PNT has no clear excess against the controls. SYSINFO-shaped patterns recur,
but much of their excess over the first control survives a control preserving
fixed coordinate structure. Candidate words include repeated hypothetical
address/channel triples; repetition alone cannot separate fixed header patterns
from actual SYSINFO serialization. No channel-range or public-satellite-ID
assumption was used to cherry-pick them. Different layout searches overlap and
their counts must not be interpreted as distinct messages.

No SYSINFO, PNT, satellite address, or timing quantity is decoded by this probe.
It also does not exclude coded, interleaved, non-minimal, differently mapped,
or absent messages. The result establishes a baseline for accidental direct
format matches and preserves candidates for a future verified coding model.
Next validation must establish enclosing SDU framing/coding and predict unused
observations, rather than promote a repeated candidate to a satellite ID.

All candidate starts, sign words, hypothesized fields, controls, and input
hashes are in ignored `local/fullband_control_probe.json`. Firmware vectors are
in ignored `local/firmware_control_envelope.json`. The window-mask test and Ruff
pass. Raw IQ and native decoders were not modified; no downloads or RF collection
were needed.

## Receive-path bridge: outer classification precedes message type

A subsequent static audit traced the typed decoder upstream through the same
hash-verified `rx_lmac` binary. `firmware_control_receive_path.py` preserves
the disassembly, verifies 21 selected instructions and the source diagnostic
`mac/lmac/libs/liblmac/mac_ctrl_interface.c`, and writes an ignored JSON audit.
The audit and Ruff pass. This is a static path audit, not end-to-end execution.

The observed call chain is:

```text
cb4bc -> 6d610 -> 78870 -> 55190 -> d7990 -> typed body decoder
                         ^
30e90 -------------------+
```

At `6d64c`, a byte from the incoming descriptor at memory offset `0x18`
becomes an outer classifier. Values at most two reach a dispatch branch;
value two takes another path. At `6daf8`, the classifier is passed in `w3`,
a context halfword from offset `0x12` in `w2`, and the buffer in `x4` to
`78870`. The alternative caller `30e90` obtains these arguments from context
offsets `0x8a` and `0x88`, respectively. Neither set of offsets is a wire map.

Inside `78870`, classifier zero can reach the control handler `55190`,
subject to mode and routing checks. One branch compares the 16-bit routing
value against `0xff00`; another requires equality with a context halfword
at offset `0x12`. In the other inspected mode, a high-nibble `0x8000` route
is diverted before classifier-zero handling. These are conditional paths,
not a universal acceptance rule. The routing field's protocol name and wire
location are unresolved; it must not be called a satellite ID.

The eligible buffer reaches `55190` as its second argument and is passed to
`d7990`, which reads the previously established eight-bit control-message
type. Thus **outer classifier zero and inner SYSINFO type zero are different
fields**. Inner PNT type 13 does not imply an outer classifier of 13.

This strengthens the software hierarchy but does not locate another byte in
the recordings. A convincing RF candidate ultimately needs to satisfy both
the enclosing framing/classification and the inner message format. The next
specific trace is the producer of the descriptor passed at `cb4bc` (loaded
from stack offset `0x80`), followed by its relationship to the assembled
buffer. No new RF matches or semantic decodes are claimed by this audit.

## RLC framing and a stricter recording test

Following that producer establishes that the descriptor is **per-flow state**,
not simply another header copied verbatim from the wire. At `cbd74..cbd9c`,
the parser reads bits 3–6 of the incoming buffer's first word, rejects values
above eight, and selects an entry at `state_base + 32 * value`. Diagnostics
at `12b3a0` and `12b3c8` name this field `sfid` and identify the layer as RLC.
The state entry's low byte at offset `0x18` supplies the previously traced
outer classifier. Bits 9–11 of the word at that same state offset select the
header form. Thus the classifier is reached through an SFID-to-state mapping;
we have not established the mapping's configured values.

The inspected receive parser exposes these serialized fields, with bit zero
the least-significant bit of the first byte at its input buffer:

| Bit positions | Meaning supported by code/diagnostics |
| --- | --- |
| 0–2 | Unresolved here |
| 3–6 | `sfid`, four bits; this path accepts 0–8 |
| 7 | `last`, ends the parser's outer iteration when set |
| 8–17, extended form only | `SeqNum`, ten bits |
| 18–19, extended form only | `FragInfo`, two bits; value meanings unresolved |

State header mode one uses eight header bits; mode two uses twenty. The parser
then reads a list of 12-bit entries. Each entry's low bit terminates that list
when set; its upper eleven bits are a byte count, accumulated after multiplying
by eight. The header plus length list is rounded up to a byte boundary. These
observations come from `cc1cc..cc284`; the sequence/fragmentation diagnostic
at `cc674..cc6cc` independently associates their bit slices with field names.
This is a partial receive format, not a complete RLC implementation or a proof
of every mode, error path, or fragmentation rule.

`firmware_rlc_framing.py` verifies the binary hash, diagnostic text, and 28
selected instructions; its full inspected regions are preserved in ignored
`local/firmware_rlc_framing.json`. The older description of an "outer
descriptor classifier" remains valid as an internal interface, but must not
be interpreted as a separately serialized classifier byte.

We applied a deliberately conditional hypothesis to the same 13 full-band
frames: a complete minimal SYSINFO or PNT message immediately follows an RLC
header with exactly one length entry, without FEC or interleaving between the
tested sign positions. The length entry must be `(message_bytes << 1) | 1`:
17 for eight-byte SYSINFO and 11 for five-byte PNT. Payload begins at bit 24
for the eight-bit header or bit 32 for the twenty-bit header. The 12 length
bits plus the inner format constrain 28 bits. We leave SFID, fragmentation,
the first three bits, and header-rounding bits unconstrained, so no unverified
operational-value assumption can reject a candidate.

| Conditional pattern | Qualified windows, overlapping searches | Matches |
| --- | ---: | ---: |
| 8-bit RLC header + PNT | 497,496 | 0 |
| 20-bit RLC header + PNT | 494,808 | 0 |
| 8-bit RLC header + minimal SYSINFO | 489,432 | 0 |
| 20-bit RLC header + minimal SYSINFO | 486,744 | 0 |

Five within-frame shuffled controls yield zero for each pattern. Coordinate
controls yield zero except `[2, 0, 0, 0, 0]` for extended-header SYSINFO.
This does not establish statistical absence of messages; it shows that the
previous direct-format candidates do not satisfy this particular enclosing
layout. Coded, interleaved, fragmented, multi-SDU, non-minimal, or differently
mapped messages remain untested by this probe.

Run `fullband_control_probe.py --rlc` to reproduce. Results and input hashes
are in ignored `local/fullband_rlc_control_probe.json`; the original bare
message result is preserved. Both probe tests pass, including rejection of
a changed length entry, and Ruff passes. Next useful work is recovering the
SFID state initialization and tracing the buffer upstream toward the PHY
decoder, rather than assigning meaning to the rejected bare-format matches.

## Connection to the previously recovered GMH parser

The upstream trace now connects the earlier GMH work to this RLC/control path
inside the same receive routine. At `313fc`, the receiver invokes GMH parser
`c6240` with the bit-reader object in `x21`. After helper `c6870` at `314b0`,
it invokes `c6a40` at `315a0` with that same reader as argument four. The latter
function is associated with diagnostics in `mac_decoder_common.c`.

`c6a40` reads a four-bit dispatch value. One inspected path, value seven with
the relevant mode flag clear, enters a SID-descriptor loop. Each descriptor
begins with another four-bit value: the low three bits select a format and
bit three controls whether that loop ends (`c7570..c7574`). Diagnostics call
these fields `format` and `last`. Formats at most three read a 16-bit SID.
An explicit-length branch reads twelve bits; format two instead selects
sixteen bits (`c7a1c`). Other formats and implicit-length branches exist and
are not fully reconstructed here.

For the inspected explicit-length branch, a nonempty payload with an eligible
SID at most `0xfff` passes a buffer reference and selected byte count through
`c7a30 -> 6cfe0 -> 6caf0 -> cbc20`. The final call is the RLC parser described
above. The wrapper checks for a matching receive context before parsing.
The SID field is therefore a routing/context value; its name is **not evidence
that it is a satellite ID**.

```text
GMH parser c6240
    -> header/length helper c6870
    -> MAC dispatch c6a40 (inspected dispatch value 7)
    -> SID descriptor selects route and payload byte count
    -> RLC parser cbc20
    -> SFID selects per-flow state
    -> reassembly/dispatch path
    -> typed control decoder d7990
    -> SYSINFO / PNT body
```

This diagram records software control flow, not physical frequency/time order.
The SID parser takes the descriptor bit reader and payload buffer as separate
arguments. We have not established that the descriptor bits immediately precede
the RLC bytes in a single RF serialization. Nor have we mapped any of these
layers to a specific OFDM symbol or FEC codeword. That distinction prevents
incorrectly treating the inner control message as the GMH itself.

`firmware_mac_rlc_bridge.py` reproduces the hash check, 30 selected instruction
checks, source/field diagnostics, and surrounding disassembly in ignored
`local/firmware_mac_rlc_bridge.json`; the audit and Ruff pass. This trace adds
no RF decoded packets. The next discriminating step is resolving how the
descriptor reader and payload buffer are initialized upstream of `313fc`,
including which bytes have already been decoded or separated by hardware.

## Reader initialization and software buffer separation

That initialization is now traced. At `31308`, the caller obtains the data
pointer for the buffer at receive-context offset `0x288` (context subobject
`+0x280`, member `+8`). At `31318` it obtains the buffer length; `31328` passes
that pointer and length to the already validated bit-reader initializer
`ea8b0`. Thus GMH and subsequent descriptor reads originate in this buffer,
not an independently supplied descriptor stream at this stage.

After GMH parsing and the length helper, `314f8` calls `f2580` with that same
buffer and the helper's output count at stack offset `0x7c`. The original
buffer is retained in `x22`; the returned buffer replaces context member `+8`.
The descriptor reader remains positioned in the original backing storage.
This establishes a software split of one input buffer. It does not imply
that its contents were contiguous before PHY decoding or that all descriptor
and RLC boundaries have been reconstructed.

To test the split interpretation, `firmware_buffer_split.py` executes the
actual `f2580` instructions in Unicorn on 100 synthetic single-node buffers,
with randomized lengths and interior split offsets. Only the allocator and
128-byte metadata-copy helper are modeled. For every case:

- The original node retains the prefix and its original data pointer.
- The returned node describes the suffix and advances its data pointer by
  exactly the split count.
- Prefix and suffix lengths sum to the original length, and all payload bytes
  remain unchanged.

The harness asserts the firmware hash, return location, pointers, lengths,
and byte contents. All 100 cases pass; chained-node and failure cases are not
covered. Results remain ignored in `local/firmware_buffer_split.json`.
The static bridge audit now verifies 40 instructions, including initialization
and split call arguments; both scripts pass Ruff.

Upstream, calls at `28c0c` and `28e34` enter the receive routine `312b0` after
`27100` supplies/checks the next receive item. The next boundary to resolve is
inside `27100`, which obtains an object via `63f50` and reads metadata via
`653e0`. Those objects have not yet been equated to any specific RF codeword.
The current result closes the software-buffer separation question; FEC,
interleaving, and physical placement remain unresolved.

## Descriptor-to-buffer connection and the remaining PHY boundary

The upstream trace rejoins the hardware-facing descriptor path documented
earlier in `firmware-header-analysis.md`; discovering that path is not a new
result. The new connection is the propagation of its payload pointer and
length into the buffer consumed by the GMH/RLC/control chain above.

At `27138`, `63f50` supplies the receive descriptor. Helper `653e0` copies
its first 16 bytes as local metadata. The caller loads the first 32-bit
quantity as the payload length (`27224`) and separately loads the payload
pointer from descriptor offset `0x10` (`27228`). At `27354`, these become
arguments two and three of `f0ab0`. In that wrapper, the length is stored at
buffer-node offset `0x16` and the original payload pointer at offset `0x30`
(`f0cb4`, `f0cf8`). Helper `311e0` then installs the resulting node at receive
context member `+8`. This is the member subsequently read by `312b0`.

The inspected successful wrapper path retains the payload address; this is
buffer construction, not an observed demodulator or FEC transformation. The
descriptor's copied metadata is distinct from the payload storage. These
memory offsets must not be treated as offsets in the received bit stream.

A separate branch at `26a00` inspects a trailing area labeled `PHY Info` by
diagnostics, with entries labeled `demod stats` and `EVM stats`. These names
describe receive statistics, not decoded satellite messages. Their presence
in a receiver-side buffer does not establish that the area was transmitted
over the air. No search for these statistics in RF signs is justified by this
trace alone.

The reproducible static bridge audit now checks 55 selected instructions and
passes Ruff. It verifies argument/pointer propagation, not a complete hardware
execution. The remaining bridge is specifically the PHY transformation before
this descriptor interface: coding, interleaving, scrambling and placement of
the resulting MAC bytes in the full-band symbols. We now have the software
consumer chain to validate candidate decoded bytes against, but no established
inverse transformation from the recordings to those bytes.

## PHY frontier review, 2026-09-29

Review of the earlier `firmware-header-analysis.md` shows that its descriptor
section already recorded the pointer/length/wrapper path summarized above.
The expanded executable audit consolidates that evidence; it should not be
counted as a newly discovered PHY decoding step. The RLC/control-message
traces and splitter emulation add software detail, but have not moved the
unknown RF-to-MAC transformation boundary.

A bounded online refresh checked the published
[Qin et al. paper](https://www.nature.com/articles/s44459-026-00075-6), its
coding discussion and code-availability section. It describes pilot/template
and diagnostic tools, treats the header as unknown in its processing-gain
analysis, and labels its proposed scrambler/LDPC explanation of T-codes as
conjecture. These passages do not give a verified MAC-header decoder. The
paper links a Zenodo archive. Its web page failed in the browsing tool, but
the record API and small guide were subsequently accessible. The listing
contains three parts of `starlink-template-supp.zip` totaling 5,192,055,563
bytes, plus an 800-byte reassembly guide. The guide only explains concatenating
and extracting the parts. No archive payload was downloaded or inspected in
this check, so no additional decoder contents are asserted.

The already catalogued SDR-X supplement is an interpretation of an uplink
patent, not a measured downlink decoder. The existing restricted seven-tap
searches found no exact relation in 5,010 within-symbol configurations or
7,344 rectangle/layout/stream-pair configurations. Those negatives do not
exclude other coding or mappings, but repeating them without a new constraint
would not identify the missing transformation.

No new discriminating PHY constraint emerged from this review. This is an
investigation limit, not proof that the information is unavailable online or
that the signal cannot be decoded. The goal remains incomplete; further
progress needs a justified coding/mapping hypothesis or independently verified
symbol-to-byte example, not additional interpretations of accidental matches.

### Follow-up: bounded archive inventory check

The previously uninspected Zenodo archive directory has now been checked with
`zenodo_inventory.py`. A successful HTTP range request reads only the last
131,072 bytes of part three. The script resolves the ZIP64 directory offset,
checks the complete central-directory extent and entry count, and records
all 33 entries in ignored `local/zenodo_inventory.json`.

The inventory comprises the existing MATLAB supplement, supporting templates,
the large exemplar-frame MAT file, directories, and macOS metadata. All 19
small local files available for comparison match the archive's recorded sizes
and ZIP CRC32 values. That is a consistency check, not cryptographic proof of
identical or authentic content. No additional decoder file appears in the
complete directory inventory; the large MAT member was not downloaded or
compared. This closes the archive-inventory lead without claiming to inspect
every byte of the archive. The script and Ruff pass.

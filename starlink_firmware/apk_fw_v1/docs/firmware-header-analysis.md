# Receive-MAC header evidence from public firmware

2026-09-28. This is an executable-code investigation, not a decoded RF packet.
It supplies constraints for subsequent work but does not yet link the observed
six leading OFDM symbols to this MAC header.

## Artifact and method

Source acquisition is recorded in [firmware-leads.md](firmware-leads.md).
Input: `local/firmware/catson-bin--rx_lmac`, SHA-256
`9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe`.
It is a stripped AArch64 ELF. `.text` has equal file offset and virtual address,
starting at 0x227e0, so addresses below also locate bytes in this exact file.
The binary's authenticity remains independently unverified.

Capstone disassembly links GMH length diagnostics to the function beginning at
0xc6240. A nearby diagnostic identifies the source filename as
`mac_decoder_common.c`. Additional diagnostics refer to a GMH MCS table, MCS
values, and codeword counts. These references place the findings in receive-MAC
processing; they are not evidence of the PHY convolutional-code generators.

## Observed parsing operations

| Code address | Operation | Interpretation boundary |
| --- | --- | --- |
| 0xc6280–0xc62ac | Read 3 bits and copy into low bits of an output structure | Flag group; error diagnostics label bit 0 as MH version |
| 0xc62b4 | Branch on output bit 1 | Path associated with signaling-length diagnostic |
| 0xc6394–0xc63b8 | On the other path, read 1 bit into output bit 3 and branch | Selects long versus short parsing paths |
| 0xc63c4–0xc63e8 | Long path reads 12 bits into output bits 4–15 | Packed fields; not a claim about absolute RF bit offsets |
| 0xc6318–0xc634c | Short path reads 4 bits, splitting them into output bits 4–5 and 12–13 | A different compact representation |
| 0xc6418, 0xc658c | Extract output bits 6–11 | Diagnostic identifies GMH length; long path requires greater than 3 |
| 0xc65c4 | Short path checks output bits 6–11 are zero | Consistent with short-header length diagnostic |
| 0xc6690–0xc66a8 | Extract output bits 12–15 into MCS-table entry count | Diagnostic identifies GMH_NUM_MCS |
| 0xc66f8–0xc671c | Read a 20-bit entry; separate low 8 bits and next 12 bits | Nearby diagnostic labels these MCS and N_CWs |
| 0xc6724–0xc6744 | Look up MCS-related data and multiply a returned value by count | Diagnostic labels resulting quantity BITS; units need further tracing |

The table-building path is conditional, including a feature query and flags;
it is not taken unconditionally for every packet. Other branches process a
single entry with 16- or 20-bit width. Header-size calculations include
alignment, but a full validated parser has not been reconstructed.

## Verified bit-reader behavior

The parser calls a routine at 0xeada0 with bit count in register w2. On its
non-crossing cached-word path, it shifts a 32-bit cached value right by the
current offset, masks the requested width, and advances the offset. This is
LSB-first extraction **within that cached word**.

`local/firmware/verify_bitreader.py` ran 100 deterministic random test cases
through the actual ARM64 instructions using Unicorn. Every case matched
`(word >> offset) & ((1 << width) - 1)`, advanced by the requested width, and
returned success. Execution was limited to 300 instructions and 100 ms per
case, in emulated memory, with no peripherals or host-call hooks. No dish or
complete firmware process was run. The input hash and test cases are recorded
in ignored `local/firmware/bitreader-verification.json`.

This check does not verify how bytes enter the cached word, reads spanning a
word boundary, error paths, or RF serialization. In particular, the storage
endianness and OFDM bit ordering must not be inferred from this result alone.

### Follow-up: initialization, byte order, and word crossings

The subsequent assay resolves the first two limitations above for successful
reads on aligned input buffers. Initializer 0xea8b0 stores the buffer pointer,
resets the position, and loads the first 32-bit word using an ordinary AArch64
little-endian load at 0xea9b0. The crossing path at 0xeaefc–0xeaf50 loads the
next word and combines its low bits with the remaining bits of the previous
word. Position query 0xeb2d0 reports the total bits consumed.

The extended `verify_bitreader.py` calls these three real routines in emulated
memory, without substituting their algorithms. Across 200 deterministic random
128-byte buffers, 11,064 sequential reads of widths 1–32 passed comparison
against extraction from `int.from_bytes(buffer, 'little')`. There were 5,255
word-crossing reads, counting calls starting at an internal offset of 32. Every
position query also matched the cumulative read width. Each call retained the
500-instruction/100-ms bound and no peripheral or host-call hooks. Detailed
vectors are in `local/firmware/bitreader-stream-verification.json`.

This verifies increasing byte order with LSB-first bits within each byte at
this **software interface**. Tests intentionally stop before the end of the
buffer; unaligned inputs and invalid/boundary error paths remain untested.
It does not imply LSB-first transmission or establish any RF descrambling.

The parser's direct caller is identified at 0x313fc. In the function starting
at 0x312b0, calls at 0x31308 and 0x31318 supply a pointer and length to the real
initializer at 0x31328; its reader state is then passed to the parser as x3.
The buffered PDU is retained in a context member at offset 8. This establishes
that the parser uses the byte-buffer reader just tested. Tracing that buffer
back through the PHY/hardware receive interface remains necessary.

## Consequences for signal work

### Observed 60-bit sequence: literal firmware search

The empirical seed generating the previously recovered 60-state vocabulary was
searched in all ten extracted `catson-bin--*` executables, including PHY/MAC
variants and `uterm_binbox_user_terminal`: 35,450,176 bytes total, with input
hashes recorded. There are 240 distinct seed patterns after all cyclic rotations,
reversal, and complement. The search covers packed MSB-first and LSB-first bits
at every bit offset, plus arrays of 0/1 bytes and 32-bit little-/big-endian
integers. **No literal match was found.**

Reproduction: `reports/2026_09_28_sequence_semantics/firmware_seed_search.py`.
Two focused tests verify every bit alignment, truncated inputs, repeated matches,
and rejection after a bit mutation; tests and lint pass. Detailed results are
in ignored `reports/2026_09_28_sequence_semantics/local/firmware_seed_search.json`.
This is not an exhaustive search of all firmware assets or representations.
It does not exclude generated sequences, constants assembled by instructions,
different packing/transforms, or implementation in FPGA/ASIC logic. It supplies
no protocol meaning for the observed phase state.

### Transmit-side GMH prefix packing verified

The transmit binary now supplies an independent check on the receive parser.
Input `catson-bin--tx_lmac` SHA-256 is
`a92181989c19e4609692ed38b54b7e063871fed8e45d22c6ded041aaec9532d6`.
The encoder/finalization region contains an assertion naming
`mac_enc_mh_header_finalise` (string 0x11f178, referenced at 0xc1960/0xc1990).
The non-signaling path packs a prefix at 0xc1368–0xc13e0 and calls bit writer
0xe1430 with width 8 or 16. Isolated execution verifies:

| Prefix bits, least significant first | Short form: 8 bits | Long form: 16 bits |
|---|---|---|
| 0–1 | Both zero in this path | Both zero in this path |
| 2 | One input flag, meaning unresolved | Same |
| 3 | 0 | 1 |
| 4–5 | Two input bits, meaning unresolved | Same |
| 6–7 | MCS-entry count, low two bits | Low two bits of header length |
| 8–11 | Outside prefix | Remaining four header-length bits |
| 12–15 | Outside prefix | MCS-entry count, four bits |

The header-length and MCS-count labels come from the previously traced receive
parser's diagnostics, combined with matching layout; the transmit-side arguments
have not all been traced back to named source fields. In particular, do not
label the unresolved bits satellite ID, timestamp, or orbit information.
The short prefix's count occupies wire bits 6–7; the receive parser expands it
into bits 12–13 of its internal packed structure. Those representations must
not be confused.

`local/firmware/verify_gmh_prefix.py` emulates 400 packing cases across both
forms, then calls the actual bit writer for non-crossing cached writes at varied
offsets. Every case matches the expected prefix and LSB-first cache update;
results are in ignored `gmh-prefix-verification.json`. This verifies instruction
behavior, not validity of every synthetic field combination. It does not test
the entire header builder, signaling branch, cross-word flush, FEC, RF carrier
order, or a complete transmit/receive round trip. The verified prefix lengths
are components of a header; they are not replacements for the 32-bit scheduling
unit or its 114-symbol coded representation.

#### GMH padding and length units verified

The header finalization path calls 0xc1ac0 at 0xc1294 with argument 2 equal to
8. Routine 0xc1ac0 queries the current bit count through 0xe1af0, appends zero
padding to make `(current_bits + 8)` a multiple of the alignment, then appends
eight additional zero bits. Alignment is 8 bits when the low byte of mode is
1, otherwise 32 bits. The path calling it at 0xc1294 excludes mode 1 via the
branch at 0xc1280. Finally it calls 0xe1a10, which reports **bytes**, and stores
that byte count through the supplied output pointer.

`local/firmware/verify_gmh_padding.py` executes the original routine and its
writer/query callees in isolated RAM. Across input lengths 0–255 and modes
0/1/2, all **768 cases** preserve input bits, append only zeros, and return
`ceil((input_bits + 8)/alignment) * alignment / 8` bytes. Tests include writes
crossing 32-bit boundaries. Only the required stack-guard pointer is initialized;
no successful-path function calls are replaced by Python implementations.
Results are in ignored `gmh-padding-verification.json`.

At 0xc12bc the caller loads that byte count, and at 0xc1374 masks it to six
bits before packing the long-prefix length field. Thus this transmit path
supports **bytes as the long-prefix length unit**, rather than bits or coded
symbols. For the observed non-signaling alignment, the resulting byte count is
a multiple of four before masking. Upstream validity limits and later mutation
have not been fully traced; synthetic input lengths do not establish legal
header lengths. In particular, these eight zeros must not yet be labeled a CRC,
convolutional termination bits, or an immutable over-the-air zero trailer.

### Transmit MCS-entry layout cross-checked with receive bit reader

Transmit helper 0xc0f60 writes an MCS entry using bit writer 0xe1430. Its
ELF relative relocation at 0x16fa48 points to 0x11f258, containing 32-bit
values 8 and 12. The helper selects one by its low-byte form argument and adds
8 for the MCS ID. It packs `(MCS & 255) | ((count & 65535) << 8)`; the actual
writer masks this to the selected total width, 16 or 20 bits. Thus the first
eight serialized bits are the MCS ID and the next eight or twelve are the
codeword count. This matches the previously traced short/long receive layout.

`local/firmware/verify_mcs_entry.py` verifies the relocation and executes both
the actual transmit helper and receive initializer/bit-reader in separate
emulators. All 400 cases reproduce the expected entries, including arbitrary
initial offsets, word-boundary crossings, and truncation of oversized count
inputs. The verification reconstructs pending cached writer bits for transfer
to the reader; it does not claim to execute the writer's final buffer-flush
routine. Evidence: ignored `mcs-entry-verification.json`.

The count label is grounded in receive diagnostics (`N_CWs`) and the MCS
lookup's subsequent bits-per-codeword multiplication. These are payload coding
parameters, not satellite identity or orbit fields. This is an entry-level
writer/reader check; a complete header parser round trip and RF/FEC validation
are still outstanding. Oversized counts and arbitrary IDs in the synthetic
tests demonstrate packing behavior, not valid scheduler inputs.

### Complete receive-parser execution: acceptance is a weak gate

`local/firmware/verify_gmh_parser.py` executes the complete function 0xc6240
and its actual successful-path callees on 300 synthetic short/long headers.
It initializes modeled wrapper memory, a stack-guard pointer, a bookkeeping ID,
and the feature-query state so 0xffc40 returns false. No Python function
replacements or external hardware are used. Each test verifies the internal
prefix, recovered first MCS/count, consumed header bytes, remaining payload
length, and unchanged payload contents. Results are in ignored
`gmh-parser-verification.json`.

This establishes a complete parser path, but also shows why parser success
cannot validate an RF hypothesis by itself:

* For non-signaling headers, consumed size is computed from the prefix size,
  MCS-entry count, entry width, eight reserved bits, and 32-bit alignment.
* The long form checks that its six-bit declared length exceeds three, but
  the tested path does **not require equality** with the computed consumed size.
  Tests alternating correct lengths with declared length 60 succeed and consume
  the same computed size. This does not make inconsistent headers valid TX output.
* With the selected feature state, the parser records the first MCS/count and
  skips the complete computed header. It does not look up the MCS ID on this
  path; arbitrary eight-bit IDs can therefore pass.

The feature-enabled table-building path remains untested end to end. None of
these synthetic cases validates a recorded RF codeword. A future claimed decode
needs coding/re-encoding agreement, independently supported boundaries and
mapping, and cross-recording consistency in addition to parser acceptance.

### PHY hardware-table initialization leads

The runtime's three explicitly named firmware files are small signed UT-MCU
boot images, not identified radio decoder images. A content search of bundled
configuration found telemetry/error-counter references but no explicit
convolutional-generator or descrambler definition. This is a text-search result,
not proof that binary-encoded parameters are absent.

Tracing assertion strings in `catson-bin--phyfw` identifies two more direct
targets. Input SHA-256 is
`52285c9809696a88dca1a24407bc3ec5e853c255ca385f97b6da2463898cc326`.
In this binary file offsets and virtual addresses agree for these code/data
sections.

* At 0x5e19c, the call to 0x5edf0 is checked against an assertion naming
  `init_modcod_table`. That routine reads 512 32-bit words through object member
  0x2d0, selects source word `i XOR 1`, and writes through member 0xce0. It repeats
  the same 512-word block sixteen times (8,192 destination words). This is
  hardware loading order, not evidence that RF bits should be swapped.
* At 0x5e1a8, the call to 0x5ee40 is checked against an assertion naming
  `init_cgm_table`. It chooses a 256-word table at 0xaf3a0 when object member
  0x10 equals 3, otherwise at 0xaf7a0. It repeats that same block sixteen times
  through member 0xce8. The acronym and packed field meanings are not yet
  established; do not identify this as an LDPC matrix or constellation map.

Both constant tables were extracted with hashes to ignored
`local/firmware/phy-cgm-tables.json`; disassembly is in
`phy-table-initializers.txt`. No firmware hardware writes were executed.
The constructor at 0x5dc20–0x5dc30 assigns constant address **0xaeba0** to
member 0x2d0. Its 2,048 bytes form 256 pairs of words, with 132 distinct pairs.
Entry 68 and entries 133–255 equal entry 0. The source-table SHA-256 is
`b131741a54612d06084705d886c4656c0d4c53ba3455c93913ef5ca5ec37c907`.
Isolated Unicorn execution of the actual loader verifies all 8,192 writes,
including pair order, repetition, destination addresses, and zero return status.
This uses modeled RAM, not real hardware.

There is also a cross-binary numerical link. In `rx_lmac`, initializer 0xe7d40
calls table builder 0xe7b60; its source pointers are supplied by relocations
at 0x175468/0x175478/0x175488. The latter two point to 133-record tables at
0x12fb88 and 0x12f328. Each record is 16 bytes, with an identifier at byte 12;
both tables contain every ID 0–132. Initialization at 0xe7f18–0xe7f28 places
record pointers into the ID-indexed lookup later used by 0xe8520, the GMH
parser's MCS lookup.

For **every nonzero ID in both tables**, the first PHY table word equals
`ceil(record.field_at_byte_4 / 2) - 1`. ID 0 is an exception: its MAC field is
114, whereas its first PHY word is 1023. This ties the PHY table to MAC MCS
records, but does not yet establish the units of that field, the packed second
word, or an error-correction polynomial. The full extraction and checks are in
ignored `local/firmware/verify_modcod_table.py` and `phy-modcod-table.json`.
Next: trace how these record fields and packed second words are constructed or
consumed, then test the resulting coding constraints against RF observations.

#### Packed second word: exact arithmetic and semantic evidence

The MAC record fields now have diagnostic support. Function 0xe85b0 obtains a
16-byte MCS record through 0xe8520 into stack offset 0x28. Its overflow checks
load record+8 at 0xe85f0 and record+4 at 0xe862c. Their error branches reference
`bits_per_cw overflow` (string 0x12ec80, address construction 0xe8704–0xe8710)
and `syms_per_cw overflow` (0x12ece0, 0xe8790–0xe879c), respectively. Thus
record+4 is symbols per codeword and record+8 is bits per codeword. The helper
is named `ul_dom_mcs_table_gen` in diagnostics; this does not by itself prove
that either entire source table or a particular mode is the observed downlink.

For all 132 nonzero IDs, the second PHY word `W` admits the following exact
interpretation. The labels beyond the two MAC fields remain inferred:

| Word bits | Extracted quantity | Evidence |
|---|---|---|
| 0–8 | Candidate coded length `N = 64 * (W & 511)` | With candidate `m`, reproduces symbols per codeword |
| 9–13 | Candidate code-rate index | Each index maps to one exact `K/N` ratio across all entries |
| 14–16 | Candidate bits per symbol `m = 1 + ((W >> 14) & 7)` | `ceil(N/m)` equals MAC symbols per codeword for every nonzero ID |
| 17–30 | `K = 8 * ((W >> 17) & 16383)` | Equals MAC bits per codeword for every nonzero ID |
| 31 | Even-symbol-count flag candidate | Equals 1 precisely when the MAC symbol count is even |

For example, ID 2 gives `N=16384`, `m=1`, `K=8192`, ratio 1/2;
ID 10 gives `N=16384`, `m=2`, `K=8192`, also 1/2. These are numerical
constraints, not verified constellation mappings or FEC matrix definitions.
All checks and the inferred rate-index map are saved in `phy-modcod-table.json`.

**Entry 0 must be treated separately.** All three MAC source tables, including
the 48-record table at 0x130410, specify 114 symbols and 32 bits for ID 0.
That is numerically consistent with a rate-1/3, constraint-length-7 convolutional
code carrying 32 information bits plus six termination bits: `(32+6)*3=114`.
This is a candidate to test against the recordings, not proof of the encoder,
its generators, scrambling, bit order, or downlink applicability. The PHY entry
0 instead duplicates ID 68 and cannot be used as its coding definition.

#### Downlink scheduler confirms use of GMH MCS 0

The 32-bit/114-symbol entry is now connected to explicitly named downlink
code, rather than only an uplink diagnostic. At 0x92734 the scheduler supplies
ID 0 to 0xe9ca0. Its failure branch at 0x92ba4 reaches an assertion referencing
`mcs_table_mcs_query_dl(MAC_GMH_MCS, &mcs_data)` (string 0x11b9d8,
address construction 0x92bcc–0x92bd4). On success, 0x92750 passes the record
to helper 0x90020. That helper divides accumulated bits by record+8, then
adds the resulting codeword count times record+4 to its symbol accumulator
(0x90118–0x90134). For ID 0 this accounts for 114 symbols per complete
32-bit unit. It does not establish that the entire observed header is one unit.

The two MCS lookup roots are distinct:

* Downlink lookup 0xe9ca0 uses root 0x1b1d90.
* Lookup 0xe8520, also used by the earlier GMH parser path, uses root 0x1afbe8.
  Its use in `ul_dom_mcs_table_gen` identifies an uplink consumer. Do not assume
  that parser path's table choice describes every downlink receive mode.

Initializer 0xe7d40 selects the downlink root when its second argument's low
byte is zero and the other root otherwise. Observed calls initialize the
downlink root with source-selector 0, 2, or 3 depending on mode/feature checks;
builder 0xe7b60 maps those selectors to the 48-entry table at 0x130410,
the 133-entry table at 0x12fb88, or the 133-entry table at 0x12f328, respectively.
All three have the same ID-0 record. This establishes downlink scheduling use
of that record without selecting a runtime mode for the captured transmission.

Bounded disassembly extracts are saved to ignored
`local/firmware/downlink-gmh-mcs-path.txt`. The encoder generators, bit ordering,
scrambler, and physical placement remain unverified. The negative 114-bit
assay therefore rejects neither the firmware's scheduling quantities nor all
encodings compatible with them.

### Resolved receive method and address translation

#### Additional transmit-scheduler audit

A bounded static inspection of the canonical `catson-bin--tx_lmac` binary
(SHA-256 `a92181989c19e4609692ed38b54b7e063871fed8e45d22c6ded041aaec9532d6`)
confirms a second concrete GMH accounting path. Its diagnostic at 0x1128f8
names the downlink GMH MCS lookup. Nearby diagnostics at 0x1129c0 and 0x112a20
describe reserving GMH space and report bits and symbols per codeword.

At 0x92d1c, `ldp w5,w4,[sp,#0x9c]` loads the symbol and bit quantities from
the stack record. Instructions 0x92d28–0x92d38 compute
`w5 * floor((w7 + w4 - 1) / w4)`: integer ceiling division into codewords,
followed by multiplication by symbols per codeword. This supports scheduling
and size accounting, not a particular polynomial encoder.

The inspected helper at 0xe04c0 checks a table entry and copies sixteen bytes
to the caller buffer (`ldp` at 0xe051c, `stp` at 0xe0524). It does not encode
header bits in this path. No generator, interleaver, scrambler, or on-air placement
was identified in this bounded follow-up. Their absence here does not establish
that they are absent elsewhere in firmware or implemented exclusively in hardware.

The reproducible static audit is
`reports/2026_09_28_sequence_semantics/firmware_tx_gmh_audit.py`; it checks the
binary hash and exact instruction operands and saves bounded disassembly to
ignored `reports/2026_09_28_sequence_semantics/local/firmware_tx_gmh_audit.json`.
The firmware was not executed. The 32-to-114 convolutional interpretation remains
a numerical hypothesis; scheduler evidence must not be presented as its proof.

The indirect call at 0x63fb8 is now resolved for the objects constructed by
the initialization path under inspection. Calls at 0x63ce8 and 0x63e00 invoke
factory 0xbe660 with output locations 0x180900 and 0x180908, respectively.
The factory stores virtual-table address 0x188aa0 at object offset 0, and stores
a register-base pointer through the private object at offset 8. Modes 1 and 2
select different bases while using the same table.

The receive caller loads the virtual method at table offset 0x10. The ELF
R_AARCH64_RELATIVE relocation at 0x188ab0 supplies address **0xbe5b0**. This
method follows object+8 and private-object+8, then reads one 32-bit word at
`base + 0x34 + 4 * (lane & 255)` and returns it. The caller supplies lane 0 or 1.
It does not read or modify payload bytes, and contains no FEC or descrambler.

`local/firmware/verify_receive_leaf.py` checks the relocation and emulates the
actual method with modeled memory. All 100 cases across both lanes passed:
exactly two pointer reads and one 32-bit value read, no memory writes, and the
expected return value. This verifies CPU behavior; it does not model the
hardware-side meaning or side effects of reading the register. Results and
input hash are in ignored `receive-leaf-verification.json`.

The returned value then passes through 0xfe6b0. For memory mode zero the helper
returns the value directly. Modes 1–3 call 0xfdc60, which returns zero for a
zero input and otherwise applies a table-based base/offset address translation:
`virtual_base + uint32(value - physical_base)`. Thus the value participates in
descriptor-address translation, not software channel decoding. These names
describe the observed arithmetic; the physical mapping table's initialization
has not been independently verified.

This resolves the immediate indirect-call uncertainty and moves the search to
the hardware configuration/firmware interface upstream of this receive queue.
It does not establish that every possible firmware path has the same type,
that all decoding is in hardware, or that no auxiliary software decoder exists.

### Receive descriptor versus transmitted header

Further tracing in the same binary identifies the receive routine beginning
at 0x27100. Its diagnostics name `mac_l1_recv_pdu_int` and source file
`mac_l1_interface.c`. The following addresses distinguish local metadata from
the payload that eventually reaches MAC parsing:

| Address | Observed operation |
| --- | --- |
| 0x27138 | Calls 0x63f50 to obtain a descriptor pointer |
| 0x63fac–0x63fb8 | Loads a virtual method through an object and invokes it indirectly |
| 0x63fc4–0x63fc8 | Calls another helper and stores the returned descriptor pointer |
| 0x27164 | Calls 0x653e0 to copy the descriptor's first 16 bytes into local metadata |
| 0x6540c | Calls PLT entry 0x21e70 with length 16; ELF relocation resolves this entry to `memcpy` |
| 0x27224 | Loads a 32-bit quantity from the copied descriptor, subsequently used as buffer length |
| 0x27228 | Loads a distinct payload pointer from descriptor offset 0x10 |
| 0x27334–0x27354 | Passes that pointer and length into buffer-wrapper routine 0xf0ab0 |
| 0xf0cd4, 0xf0cf8 | Stores the original payload pointer in wrapper-related structures |
| 0x273a0 | Passes the wrapper into 0x311e0, which retains it at context offset 8 |

The tests on bytes at descriptor offsets 5 and 6 are therefore tests on
receive-interface metadata. Their exact semantics and provenance have not been
recovered. Treating these local descriptor bits as raw on-air header offsets
would be unjustified. The original 0x108110 diagnostic mentions a GMH parse
failure near this wrapper handoff; inspection of 0x311e0 shows that this routine
itself stores the wrapper rather than performing the full bit-level parse.
The actual parser call traced earlier is at 0x313fc.

These are static control/data-flow observations, not an end-to-end execution
test. Conditional paths, wrapper internals, and helper pointer translation
still need review before claiming payload bytes are entirely unchanged. The
indirect call at 0x63fb8 has since been resolved to the register-reading leaf
described above; it does not itself supply a software channel decoder.
Raw disassembly remains in ignored `local/firmware/`.

We now have direct evidence of short/long MAC formats and an MCS/codeword-count
table, offering stronger constraints than generic patent guesses. However,
we still need the interface between PHY header decoding and MAC input, including
any hardware transformations, before searching our observed signs for these
fields. A plausible 8-bit MCS value by itself would be a weak match.

No satellite identity, timestamp, orbit field, channel-code polynomial, or
error-corrected radio header has been established by this work. Next code targets
are the bit-reader initialization/crossing path and the caller supplying GMH
bytes, followed by the PHY hardware-configuration interface.

### Additional PHY setup constants: meaning unresolved

A bounded inspection of `catson-bin--phyfw` traces object member 0xcb0 to
constructor input base plus 0x4000 (instructions 0x5dba8, 0x5dbbc, 0x5dbd4).
The initialization path writes the following words before loading the previously
identified modcod and CGM tables:

| Register offset within this block | Mode other than 3 | Mode 3 |
| --- | --- | --- |
| 0x04 | 0x351c155b | 0x361d165c |
| 0x08 | 0x38220e3d | 0x39230f3e |
| 0x0c | 0x00004345 | 0x00614446 |

The ordinary constants are constructed at 0x5e0f4–0x5e104; the mode-3 branch
constructs its constants at 0x5e27c–0x5e290 and rejoins the same stores at
0x5e108, 0x5e110, and 0x5e118. In little-endian byte order, the first ten bytes
of the mode-3 set each exceed their counterpart by one; the next byte changes
from zero to 97. This is an arithmetic observation, not a register definition.
Neither field boundaries nor semantics are known. In particular, interpreting
these small values as convolutional-code generators would be unsupported.

`reports/2026_09_28_sequence_semantics/firmware_phy_register_audit.py` checks the
canonical binary hash, exact construction/store instructions, and byte relation.
It saves bounded disassembly and constants to ignored
`local/firmware_phy_register_audit.json` under that report directory. The audit
and Ruff pass. No firmware or hardware writes were executed. The next useful
step for this path is to identify other accesses to this register block and
their diagnostics, before applying any of its constants to received bits.

That follow-up identifies three named receive-side LDPC counter accessors using
the same object member 0xcb0. Their assertion branches reference source file
`mac/phy/libs/librx/modem_rx_catson2/counters_catson2.cc` and these function names:

| Function start | Diagnostic name | Word-offset constant |
| --- | --- | --- |
| 0x61dc0 | `get_rfp_ldpc_codewords` | 0x3c |
| 0x61e90 | `get_rfp_ldpc_syn_failed` | 0x2c |
| 0x61f60 | `get_rfp_ldpc_corrected` | 0x1c |

Each takes the low eight bits of its user argument, requires that value to be
0–3, reads from block offset `4 * (constant + user + 4 * object_word_at_0x2c)`,
masks off register bit 31, and adds the remaining value to a caller-supplied
32-bit accumulator. The meaning of object word 0x2c and the hardware semantics
of reading the counters are not established here.

This ties the block to LDPC receive counters; it does not prove that the GMH
uses LDPC or identify the setup words as code parameters. The bounded code
search also found control and telemetry accesses, but no second direct use of
the setup constants that explains their meanings. Matching member offsets alone
is not exhaustive alias analysis: other objects and computed pointers can use
the same offset or reach the same hardware by another path. The static audit
now includes the three counter routines, checked diagnostic strings and
instruction operands. It and Ruff pass; no firmware execution was needed.

### Header-decoder status register mapped through telemetry metadata

The bundled `telemetry_phy_rx.include` lists separate unsigned 16-bit fields
`header_decoder_error_cnt` and `mcs_decoder_error_cnt`. The ELF metadata entries
at 0x10bdc0 and 0x10bde0 independently pair these names with structure offsets
0x16 and 0x18. Their name relocations target strings 0xd0958 and 0xd0978.

The snapshot routine at 0x62208–0x6221c loads object member 0xcb0, reads register
offset 0x168, shifts right by 16, and stores a halfword at output offset 0x16.
It then reads the same register again and stores the low halfword at output
offset 0x18. Combining the instructions with the metadata gives:

| Register at block+0x168 | Named telemetry destination |
| --- | --- |
| Bits 16–31 | `header_decoder_error_cnt` |
| Bits 0–15 | `mcs_decoder_error_cnt` |

These are two separate register reads, not a demonstrated atomic snapshot.
Overflow, clear-on-read behavior, and the precise definition of an error remain
unknown. The separately inspected reset-like routine writes all ones to this
register at 0x63260, but that does not establish hardware write semantics.
The names do not prove that “header” means exactly the GMH under investigation,
nor do they identify its code. They do provide a concrete status location for
the header-decoder path alongside the LDPC counters in this block.

The static audit now verifies the string relocations, metadata offsets, and
exact extraction/store instructions, using ELF section mappings for metadata
addresses. All assertions and Ruff pass. These are local firmware observations;
they add no decoded on-air fields and require no new recording.

### GMH metadata byte field is transmit telemetry, not a wire-format definition

The string `mpp_pdu_gmh_meta_bytes` is present in the firmware, but bundled
`telemetry_phy_tx.include` and `phy_tx_to_control` place it under transmit beam
telemetry and type it as uint32. ELF metadata entry 0x10e0a0 references the name
at 0xd1ae0 and associates it with structure offset 0x18. Neighboring entries
describe `mpp_pdu_cnt` at 0x10, `mpp_pdu_payload_bytes` at 0x14, and
`mpp_dropped_pdu_cnt` at 0x1c. These metadata links are now asserted by the
static audit; it and Ruff pass.

The producer, accumulation/reset behavior, and byte accounting are not yet
traced. Consequently this field cannot provide a GMH byte length or an on-air
offset. A bounded inspection did not establish a producer: unrelated stores
to offset 0x18 must not be matched merely by their offset. The metadata callback
pointer for this entry targets 0x485d0, which simply returns 1; it is not a
routine retrieving the byte count. This closes the name-only shortcut from
telemetry to header layout without ruling out a subsequent producer trace.

That subsequent trace finds a producer consistent with the adjacent telemetry
layout at 0x6abd0–0x6ac24. It fills PDU count, payload bytes, GMH metadata bytes,
drop count, and FSM at the matching output offsets. In particular,
0x6ac10–0x6ac1c reads register offset 0x64 through adjusted-object member 0x5f0,
subtracts the saved word at adjusted-object offset 0x664 using 32-bit arithmetic,
and stores the result at output offset 0x18. The neighboring payload-byte field
uses register 0x60 minus saved word 0x660.

Routine 0x6ade0 first adjusts its object pointer by 0x8000 and saves these same
registers into the baseline words at 0x6ae08–0x6ae14. Thus the observed producer
calculates a modulo-2^32 counter difference, rather than parsing a packet header
to obtain its length. The timing of baseline capture, rollover interpretation,
and exact hardware byte accounting remain unknown. Identification with the
named telemetry rests on the matching adjacent layout; the entire serialization
call chain has not been executed or traced end to end.

The audit includes both the producer and baseline-capture instructions and
passes its exact operand checks and Ruff. This advances the telemetry trace,
but supplies neither on-air GMH placement nor a channel-code definition.

### Setup-byte shifts correspond to CGM table shifts

Comparing the two previously extracted CGM tables gives a concrete relationship
to the mode-dependent setup bytes. Let `A` be the ordinary table at 0xaf7a0 and
`B` the mode-3 table at 0xaf3a0, each containing 256 words. Direct comparison
against the canonical binary verifies these half-open intervals:

- `A[0:9] == B[0:9]`.
- `A[9:93] == B[10:94]`.
- `A[93:242] == B[107:256]`.

The ten populated ordinary setup bytes are
`91,21,28,53,61,14,34,56,69,67`; their mode-3 counterparts are each one greater.
Interpreting those byte values as indices, all ten pairs select identical table
words: `A[index] == B[index+1]`. Contiguous matches starting at those positions
span 13–90 words. These runs overlap and are consequences of the shared table
interval; they must not be counted as ten independent confirmations.

The correspondence supports an index or entry-position interpretation of the
setup bytes. It supplies a more concrete hypothesis than treating the numbers
as code-generator polynomials, but does not establish hardware field boundaries
or CGM instruction semantics. Mode 3 adds word 0x5ab32 at index 9; its later
extra block includes eleven zero words followed by 0x5e908 and 0x70160. The
additional mode-3 setup byte 97 remains unexplained. Padding/zero runs also make
some alignments non-unique.

`reports/2026_09_28_sequence_semantics/firmware_cgm_alignment.py` verifies the
binary hash, exact table slices, and every index pair, recording the results
under ignored `local/firmware_cgm_alignment.json`. All assertions and Ruff pass.
This narrows interpretation of the setup constants; it does not decode a
header or establish an FEC matrix.

### Other firmware variants use different CGM tables

The local `phyfw_v4` and `phyfw_catapult` binaries contain the same CGM loader
assertion name, but their loader routines (0x5f2d0 and 0x64ad0) copy **512 words
sixteen times**, rather than the canonical binary's 256 words sixteen times.
Mode 3 selects tables at 0xb1d10 and 0xb7980, respectively; other modes select
0xb2510 and 0xb8180. The mode-3 tables differ in 277 of 512 words across these
variants, and the ordinary tables differ in 291 words. Neither variant contains
an exact copy of either original 256-word table.

Thus the original index interpretation cannot simply be transferred by address
or by copying tables to another variant. Different hardware/table revisions
are possible, but their instruction semantics remain unresolved. No additional
header decoding follows from this comparison. The reproducible
`firmware_cgm_variants.py` audit under the sequence-semantics report checks both
binary hashes and loader instructions, records disassembly/table hashes under
ignored `local/firmware_cgm_variants.json`, and passes Ruff. All inspection is
static; no firmware was executed.

### Follow-up 2026-09-29: unnamed two-bit prefix field reaches PDU sequence logic

Tracing callers of finalizer 0xc1210 provides a new association for software
prefix bits 4–5. The finalizer receives the relevant value in w3, masks it to a
byte at 0xc122c, saves it at stack offset 0x68, and later selects its low two
bits for the prefix. This agrees with the earlier independently emulated packing.

At caller 0x7d9d8, w3 comes from w22. One incoming path sets w22 to 1 at
0x7d9a0–0x7d9a4. Another updates a bitmap at context offset 0x1e4, compares it
with the expected map, and sets w22 to 2 at 0x7dd7c. Its mismatch branch names
`pdu_seq_map_chk mismatch: exp:%x act:%x` and also forces value 2 before rejoining
the finalizer call. A second call at 0x7de7c supplies value 2 directly.

This associates the two-bit field with PDU-sequence-map handling in the traced
non-signaling path. It does not establish the exact protocol enumeration, an
end-of-burst flag, or a satellite identifier. In particular, matching the map is
not necessary for value 2, because the diagnostic path also uses it. No complete
caller reachability proof or RF bit mapping is claimed.

The new `firmware_gmh_sequence_flags.py` audit under the sequence-semantics report
checks the binary hash, instructions, and diagnostic linkage and saves bounded
disassembly to ignored `local/firmware_gmh_sequence_flags.json`. Its assertions
and Ruff pass; the existing isolated prefix test was rerun and all 400 cases
passed. This supplies a software-level constraint for future candidate decoders,
not permission to read observed RF positions 4–5 as this field. A candidate
still needs verified channel decoding and re-encoding consistency first.

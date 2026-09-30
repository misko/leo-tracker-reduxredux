# Local routing context versus received identity

The control-dispatch argument at RX context `+0x80` must not be assumed to be
the received byte buffer. A fresh backward trace finds `0x309bc–0x309c8`
calling `0x50110` with context `+0x78` and a 16-bit key, then storing the
returned pointer at `+0x80`. At `0x30e78–0x30e90`, that pointer, key at
`+0x88`, and classifier at `+0x8a` become separate arguments to `0x78870`.
The caller's second argument independently becomes the dispatcher's fifth
argument. This distinguishes local record selection from payload flow; it
does not yet close the hardware-descriptor-to-parser chain.

## Executed lookup behavior

`receive_route_lookup.py` executes complete RX function `0x50110`. Only its
mode query `0xffc40` is stubbed to return 0 or 1; those are test branch names,
not established hardware or operational mode names.

| Mode query result | Selection | Validation |
|---|---|---|
| zero | reject key above `0xfff`; load 16-bit index at table `+0xc9e + 2*key` | reject index `0xffff`, index at/above count `+0xa2`, null pointer table `+0xb0`, null record, or mismatched record key at `+0x12` |
| nonzero | select pointer-table entry zero if count is positive | reject null table, null record, or mismatched record key at `+0x12`; no `0xfff` key limit |

The input is truncated to 16 bits before either branch. There are **98 cases**:
both modes, seven input values including boundaries and `0x10001`, and seven
table conditions (valid, empty, index out of range, unmapped, missing table,
missing record, mismatched key). The entire synthetic table remains unchanged.
Tests include high key `0xff00` succeeding only in the alternate mode when its
record key matches. Actual table population and mode-helper semantics remain
unresolved. No new recordings or device access were used.

The first static reading incorrectly suggested that selecting entry zero also
bypassed key comparison. Execution disproved that hypothesis: the alternate
branch rejoins the common comparison at `0x5016c`. Both modes reject mismatches.

## Identity implication

This is evidence for a **local record lookup key**, not evidence that a 12-bit
or 16-bit RF field names a satellite. It neither equates this key with the
32-bit identity recovered by the SYSINFO decoder nor excludes an eventual
relationship. Establishing that relationship requires following record
population and the received envelope independently. The lookup's software
offsets are not RF symbol positions.

Reproduce with the existing Capstone, pyelftools and Unicorn environment:
`python receive_route_lookup.py`; component test: `test_receive_route_lookup.py`.
Ignored receipt: `local/receive-route-lookup.json`, including pinned binary hash
and inspected lookup/store/dispatch instruction windows.

## Executed control-buffer-to-SYSINFO chain

`control_buffer_chain.py` now executes a connected path from `0x78870`, through
`0x55190`, through the actual buffer accessors and `0xd7990`, into the SYSINFO
body decoder `0xd6bb0`. It stops at `0x551ec`, immediately after decoding.
Previously the outer-decoder probe replaced the buffer accessors with stubs;
this probe supplies a real synthetic buffer object and executes both accessors.

The buffer length accessor `0xf1860` sums each linked node's 32-bit length at
`+0x16`, following the next pointer at `+0`. Pointer accessor `0xf1910` locates
the requested offset and returns node data pointer `+0x30` plus the offset.
The experiment uses a single contiguous node; fragmented buffer behavior is
not covered. This structure is distinct from the local routing record passed
as the second dispatcher argument.

There are **280 cases**: four byte alignments, declared lengths 7/8, and 35
identity values including every one-hot bit. With classifier zero, a matching
local routing key of 123 and mode helper `0xffc40` stubbed to return 1, the
eight-byte cases decode type zero, the exact supplied 32-bit identity, and
channels 7/9. Seven-byte cases return status 27, although the output identity
field has already been written. **A populated field in a failed parse is not
an accepted identity message.** The caller's status gate remains essential.

For this tested minimal format, identity occupies serialized bits 11–42,
following the 8-bit type and 3-bit padding-count fields; the supplied trailing
padding count is 3. These are **decoded control-buffer bit positions**, not
raw OFDM positions. The input bytes are synthetic known-format messages, not
newly decoded DS7–DS10 samples.

Only the mode query is stubbed. Routing, buffer traversal, bit-reader setup,
alignment handling, type dispatch and body parsing execute real instructions.
The probe does not cover the hardware descriptor producer, upstream envelope
removal, subsequent acceptance/state updates, FEC, scrambling or a mapping to
recorded symbols. It therefore closes a software handoff without claiming the
full RF-to-identity chain. Receipt: `local/control-buffer-chain.json`;
component test: `test_control_buffer_chain.py`.

### Continuous execution into the received identity store

`control_buffer_chain.py --store` extends the same entry path without manually
calling the context-update function. For valid eight-byte inputs it passes
the caller's zero-status gate, executes `0xccf20` with its real diagnostic-enable
global disabled, follows the alternate-context branch at `0x552b8`, and calls
`0x44da0` with the decoded body pointer (`outer decoded object +2`). It stops
at `0x44e18`, after the initial stores and before later feature checks.

In **140 valid cases**, received record `root+0x415a0` gains the exact supplied
32-bit identity, valid byte 1, version 0 and channels 7/9. Its old version is
set to 1 to exercise the version-change branch. The primary record at
`root+0x41538` and configured expected identity at `root+0x4164c` remain intact.
Thus the received value flows from the message bytes; it is not substituted
from the configured expectation in this branch.

The experiment also retains 140 seven-byte negative cases, stopped at the
nonzero decoder status before error handling. Their received records remain
untouched up to that stop; the complete error path is not executed. Same-version
updates, other handler branches and eventual acceptance are not covered here.

The only function stub remains mode query `0xffc40`. Buffer accessors, routing,
decoding, status-success branch and the context-store prefix execute actual
instructions continuously. This strengthens the software provenance chain but
does not verify received DS7–DS10 identities or establish an RF bit location.
Receipt: `local/control-buffer-store.json`; the existing component test file
now covers both stopping points.

## Upstream receive buffer wrapper

The receive routine calls `0xf0ab0` at `0x27354`, passing payload pointer in
`x2`, length in `w3`, callback `0x267d0` in `x6`, and the descriptor pointer
in `x7`. The callee allocates bookkeeping objects, then initializes them.
`receive_buffer_wrap.py` executes its allocation-success window
`0xf0c58–0xf0d18` with branch register `w9=0`.

This window stores the original pointer at buffer node `+0x30`, original
32-bit length at unaligned `+0x16`, and zero at next-node pointer `+0`.
Those are exactly the fields read by the real buffer accessors in the
control-buffer experiment. The backing object also receives the payload
pointer at `+0x18`, callback at `+0x30` and callback argument at `+0x38`.
Packed backing metadata contains a 20-bit length and two small flag fields.
Their semantic names are not established by the packing arithmetic alone.

**60 executed cases** cover four pointer alignments, lengths 1/7/8/128/4096,
and three input tag values. They verify the node fields, callback fields,
packed metadata and preservation of every supplied payload byte. Allocation,
the alternative `w9!=0` branch, destruction and hardware behavior are not
executed. The result proves this initializer does not strip, rearrange or
decode the payload; it does not prove the payload already starts with SYSINFO.

The remaining software gap includes packet parsing/slicing and scheduling
between receive-buffer installation (`0x311e0`) and the control callback
(`0x30e20`). Do not compose the two experiments as though these intervening
operations had been verified. Receipt: `local/receive-buffer-wrap.json`;
test: `test_receive_buffer_wrap.py`.

## Length-delimited handoff immediately before the control callback

A call-site trace locates `0x30e20` at `0xc6f60`. In this parser branch,
`0xc6ee4–0xc6ef0` reads a 16-bit value through the real bit-reader interface
into stack `+0xc4`. The caller compares it with buffer length at `0xc6f28`
and branches away if insufficient bytes are available. It then calls
`0xf2580` with the current buffer and this length. The original buffer is
passed to `0x30e20`; after the callback returns, the helper's return value
replaces the remaining-buffer pointer at `0xc6f64`.

`control_buffer_split.py` executes complete helper `0xf2580` on one-node
buffers. For a positive cut below total length, it shortens the original
node to that cut, constructs a tail node sharing the backing object, advances
the tail data pointer by the cut and increments the backing reference count.
The original node retains its payload start. A cut exactly equal to total
length produces no tail. In these one-node cases, zero and overlong cuts
also return no tail and leave length unchanged; those helper outcomes must
not be mistaken for caller acceptance of invalid lengths.

**36 cases** cover total lengths 8/16/64, zero/interior/exact/overlong cuts
and two pointer alignments. They verify lengths, pointers, backing reference
count and every unchanged payload byte. Only node allocation and the 128-byte
metadata copy are stubbed. Allocation failure and multisegment buffers are
outside this experiment.

This establishes a concrete leading-buffer/tail split at the callback handoff.
It does not establish the parser opcode selecting this branch, the position
of that 16-bit length in an RF frame, or how earlier parser operations position
the current buffer. Thus identity bit 11 remains relative to the selected
control-message buffer, not the original modem payload or recorded symbols.
Receipt: `local/control-buffer-split.json`; test: `test_control_buffer_split.py`.

### Opcode selecting the control-buffer split

The enclosing parser starts at `0xc6a40`. It consumes **four bits** at
`0xc6a9c`; opcode **6** reaches `0xc6ee4` when the low-byte state argument
preserved in `w24` is zero. That branch consumes the next **16 bits** as the
byte count used in the split. A nonzero state takes `0xc6c78` instead; its
meaning and subsequent behavior are not established by this experiment.

`control_opcode.py` executes the real opcode/length reads and buffer-length
accessor for **96 cases**: eight initial bit offsets, lengths 1/8/255, sufficient
versus one-byte-short buffers, and state arguments 0/1. Valid state-0 cases
reach `0xf2580` with exactly the requested length and original buffer object.
Short buffers reach `0xc77b0`; state-1 cases take the alternative branch.
Only the diagnostic query is stubbed. The probe stops before those targets
execute, and initializes an already-positioned bit reader.

This yields a falsifiable software-format constraint: opcode 6 then a 16-bit
length in this parser branch's header stream. **It does not establish that
these 20 bits immediately precede SYSINFO in a contiguous RF bitstream.** The
parser receives the header bit reader and the current payload-buffer pointer
as separate arguments. Their earlier construction, positions within a modem
packet, and RF coding remain unresolved.

Receipt: `local/control-opcode.json`; test: `test_control_opcode.py`.

### Relationship between the header reader and payload buffer

The caller at `0x312b0` initializes its bit reader from the current packet
buffer's start and full length (`0x31308–0x31328`). It parses prefix/length
information with `0xc6240` and `0xc6870`, then calls the verified split helper
at `0x314f8` using the resulting length at stack `+0x7c`. It keeps the original
leading node in `x22` and installs the returned tail as receive-context `+8`.
The first opcode-parser call at `0x315a0` passes:

| Argument | Value |
|---|---|
| x4 | original positioned bit-reader object |
| x5 | leading/header buffer node |
| x6 | address of receive-context `+8`, now pointing to the payload tail |

`header_payload_handoff.py` executes continuously from `0x314d8` to entry
`0xc6a40`, including the real split helper. Nine combinations of supplied
header lengths 8/16/32 and payload lengths 8/16/64 verify these arguments,
the new payload pointer at `packet_start + header_length`, both node lengths,
unchanged reader state and unchanged packet bytes. Only node allocation and
metadata copy are stubbed.

The experiment begins **after** prefix/length validation. Its length and reader
position are synthetic; it does not certify these byte strings as valid full
packets. The original bit reader was initialized with the full packet length
and is not re-bounded by this window, so do not describe it as an independently
bounded header-only reader.

This establishes why the opcode header and selected control payload need not
be adjacent. They originate in one packet but are processed through separate
cursors after the leading-region split. For the first control payload, its
identity coordinate would be `8*header_length + 11` relative to the buffer
start **at this post-prefix window**, only if no earlier opcode consumes payload bytes.
It is not relative to the original pre-prefix modem packet. Header-length
derivation and preceding opcode effects must be established before using that
conditional relationship in recorded-signal analysis.

Receipt: `local/header-payload-handoff.json`; test: `test_header_payload_handoff.py`.

### Header split-length derivation and validation

The helper `0xc6870` supplies the length used by the caller's leading-region
split. Its prefix flags were previously decoded by `0xc6240`; this new test
executes the complete length helper with those flags supplied explicitly.

| Prefix flags tested | Length source | Acceptance in this helper |
|---|---|---|
| bit 1 set (`0x02`) | implicit 7 bytes; no explicit length read | available buffer at least 7 bytes |
| bits 1 and 3 clear (`0x00`) | next 16 reader bits | length 4–255 and no greater than available buffer |
| bit 1 clear, bit 3 set (`0x08`) | next 16 reader bits | length at least 5 and no greater than available buffer |

The caller initializes a prefix-overhead counter to 2. The `0x08` branch
changes it to 3; the explicit-length cases require length at least overhead
plus 2. Both explicit forms physically read 16 bits even though the `0x00`
form rejects values above 255. The implicit form leaves the supplied reader
position untouched with respect to length reading.

`header_length_gate.py` verifies **72 cases** with declared lengths
1/3/4/5/7/8/255/256 and available buffer lengths 6/7/512. Expected failure
status is 27. Only the diagnostic query is stubbed; bit reads and buffer-length
access execute real instructions. Prefix flags, positioned reader and initial
overhead are synthetic inputs, so this does not prove which full packet
prefixes can reach each case or that the subsequent opcode sequence is valid.

This replaces an unconstrained split size with branch-specific software rules.
It is not an assertion that seven-byte headers, opcode 6 and SYSINFO necessarily
co-occur in any recorded RF frame. Complete prefix/opcode composition and the
modem's coding/interleaving remain to be established.

Receipt: `local/header-length-gate.json`; test: `test_header_length_gate.py`.

### Prefix removal changes the coordinate origin

Composing the actual prefix decoder and length helper reveals an important
offset omitted by the earlier post-prefix experiment. `0xc6240` calls
`0xf14c0` to advance the buffer data pointer and reduce its length before
returning. For explicit forms it then reinitializes the bit reader from the
advanced buffer. Thus the following header split length is relative to the
**post-prefix** buffer, not the original modem payload.

`prefix_length_chain.py` executes both complete functions with the same reader
and buffer, using actual encoded prefixes instead of injecting decoded flags:

| Tested encoded prefix | Form | Bytes removed before length processing |
|---|---|---:|
| `0x00`, zero entries | short explicit | 4 |
| `0x0108`, zero entries | long explicit | 4 |
| `0x02` | implicit | 1 |

There are 48 cases across eight declared lengths and original buffer sizes
8/512. They verify prefix success, pointer advancement, reduced length,
decoded flags, subsequent split length/status and preservation of source bytes.
Only the diagnostic query is stubbed. The explicit forms reinitialize the
reader; the implicit form does not need an explicit length read. Other prefix
entry counts can change removal length and are not covered by this assay.
An initial seven-byte buffer trial failed prefix processing; this assay uses
aligned buffer sizes and does not claim arbitrary-length buffer support.

For a first SYSINFO payload without preceding payload consumption, the
conditional coordinate is now:

`identity_start = 8 * (removed_prefix_bytes + header_split_bytes) + 11`

This is a decoded-packet coordinate, not a raw RF coordinate. The experiments
still do not prove that every independently tested prefix/opcode combination
forms a valid full packet. Complete parser composition remains necessary.
Receipt: `local/prefix-length-chain.json`; test: `test_prefix_length_chain.py`.

## Connected constructed-packet execution

`packet_identity_chain.py` now executes continuously from parser entry
`0x312b0` through prefix removal, header splitting, opcode 6, control dispatch,
SYSINFO decoding and the first received-identity stores, stopping at `0x44e18`.
This supersedes the missing-composition limitation above for this one shape:

| Original packet bytes | Constructed contents |
|---|---|
| 0–3 | Zero-entry short prefix; four bytes removed |
| 4–5 | Little-endian header split length 8 |
| 6–8 | Four-bit opcode 6 followed by 16-bit payload length 8 |
| 9–11 | Zero trailing header bytes |
| 12–19 | Minimal SYSINFO body: type/version 0, padding count 3, variable identity, channels 7/9 |

All 35 identity patterns (zero, all ones, `0x12345678` and every single-bit
value) reach the alternate received context at root offset `0x415a0`, retaining
all 32 identity bits. The expected-identity field at `0x4164c` and original
packet bytes remain unchanged. For this constructed shape only, identity starts
at original packet bit 107 (LSB-first), consistent with `8*(4+8)+11`.

The mode and diagnostic queries, allocator and 128-byte metadata copy are
stubbed; routing records and context are configured synthetically. Parsing,
buffer access/splitting, dispatch, SYSINFO decoding and initial stores execute
the firmware instructions. This stops before handler completion and subsequent
header processing: it does **not** prove complete packet acceptance, CRC/FEC
validity, a raw RF coordinate, or any correspondence to NORAD identity.
No recorded RF packet has been matched to this construction.

Receipt: `local/packet-identity-chain.json`; focused regression:
`test_packet_identity_chain.py` (35 cases). It and the extraction component
tests pass; the new chain script and test pass Ruff.

### Connected-path negative controls

`packet_identity_chain.py --controls` retains the same constructed identity
and perturbs framing lengths. The valid 20-byte packet reaches the store;
five malformed variants stop at observed firmware gates:

| Change | Observed gate | Result |
|---|---|---|
| Header length 3 instead of 8 | `0x314b4`, return from length helper | status 27 |
| Header length 17, only 16 post-prefix bytes | `0x314b4` | status 27 |
| Payload length 9, only 8 bytes available | `0xc77b0` | short-payload branch |
| Buffer length reduced to 16, payload still declares 8 | `0xc77b0` | short-payload branch |
| Buffer length 16 and payload declares 4 | `0x551ec`, SYSINFO decoder return | status 1 |

Every negative leaves received and expected identity sentinels unchanged and
never enters `0x44da0`. Source bytes remain unchanged. Bytes beyond the declared
buffer length remain mapped with the original contents: the truncation tests
therefore check logical length enforcement, not an emulator memory fault.
The hook stops before error handling; these results do not establish complete
error cleanup or complete packet acceptance. At `0xc77b0`, X0 contains the
available byte count (8/4), **not** a decoder status. The other listed X0 values
are actual helper return statuses. Receipt: `local/packet-identity-controls.json`.

This separates software identity extraction from unconditional copying of any
candidate bytes. It still supplies no scrambling/FEC/carrier-to-byte mapping
and no evidence that a DS7–DS10 recording contains this packet shape.

### Real receive-buffer initialization and installation

The `--wrapped` variant replaces the hand-built packet node with execution of
the allocation-success initializer at `0xf0c58`–`0xf0d18`, starting from zeroed
node/backing storage. It then executes the complete installation routine
`0x311e0` before entering the connected parser. All 35 identity cases and all
six framing-control cases produce exactly the same outcomes as the hand-built
node. This is three composed executions, not a continuous run from a hardware
descriptor: allocation success and payload pointer/length are supplied by the
harness, and the receive scheduler is not executed.

Fresh caller disassembly connects the interface: `0x27354` calls `0xf0ab0`
with payload pointer X22, length W25 and callback `0x267d0`; `0x273a0` passes
the returned node to `0x311e0`. The installer puts that node at context `+8`,
stores a byte argument at `+0x14`, and sets `+0x15` to the low-byte third flag
argument XOR 1. The caller derives that flag from stack byte `+0x8e`, bit 1.
The tested flag is zero, producing context `+0x15 = 1`; other flag paths are
not covered by this composed assay. The installer performs no payload reads
or writes. The initializer retains the supplied payload pointer.

Thus these software boundary routines wrap and install bytes; they are not
the missing demodulator/FEC decoder. The descriptor producer, hardware receive
processing and carrier-to-packet mapping remain unverified. Reproduce with
`packet_identity_chain.py --wrapped` and with `--wrapped --controls`.
Receipts: `local/packet-identity-chain-wrapped.json` and
`local/packet-identity-controls-wrapped.json`. Regression compares the complete
case results against the earlier hand-built-node assay.

### Descriptor-to-allocator handoff

`descriptor_payload_handoff.py` executes the receive entry at `0x27100` through
the call into buffer allocator `0xf0ab0`. The FIFO dequeue is stubbed to supply
a descriptor. Both mode queries return zero, descriptor status/trailer flags
are zero, and only the diagnostic query and 16-byte copy import are otherwise
stubbed. The metadata helper `0x26a00` executes its actual no-trailer branch.

Across 20 cases (four byte alignments and lengths 20/124/128/132/512), the
allocator receives exactly the pointer from descriptor `+0x10` and the length
from descriptor `+0`. It also receives callback `0x267d0` and the original
descriptor as callback argument. Payload bytes and descriptor header remain
unchanged. The descriptor's first 16 bytes are copied to stack metadata by
`0x653e0`; they are not a 16-byte prefix in the pointed-to payload. The marker
at descriptor `+8` is separately copied to receive context `+0x10`.

The 128-byte threshold changes prefetch behavior without changing allocator
pointer/length. This narrows the software boundary: on this path there is no
payload offset adjustment between the supplied descriptor and allocator.
It does not reveal how the hardware produced the descriptor or decoded bytes.
These mode-zero cases have **not** been continuously composed with the
mode-one synthetic identity-parser cases; other status/trailer/mode branches
remain outside this assay. CPU descriptor offsets are not RF bit positions.

Reproduce with `descriptor_payload_handoff.py`; receipt:
`local/descriptor-payload-handoff.json`. Component regression:
`test_descriptor_payload_handoff.py`.

### Same-mode descriptor-to-identity composition

The mode mismatch noted above is now addressed for one constructed receive
configuration. `packet_identity_chain.py --descriptor` runs the complete
receive routine `0x27100` to its normal return, verifies installation of the
buffer, and then calls parser `0x312b0` with that same state. Throughout both
executions `0xffc40` returns 1 and `0xffc70` returns 0. The queue selector is 0,
descriptor flags are zero, and port-query initialization byte `0x180910` is
zero. These are explicit test conditions, not recovered live terminal state.

The FIFO dequeue supplies a synthetic descriptor. The node allocator returns
prepared storage, while the full wrapper `0xf0ab0` executes against a synthetic
backing-pool free list at global `0x188d60`; no jump into the middle of its
initializer is needed. The 16-byte descriptor copy and 128-byte split metadata
copy use a memcpy stub. Receive status logic, metadata helper, buffer wrapper,
installation, prefix/header parser, opcode 6 and SYSINFO decode/store use the
actual instructions. Scheduling between receive return and parser entry is
performed by the harness, not established by this experiment.

All 35 identity patterns reach the same initial received-identity stores.
The valid framing control and five negative controls have exactly the same
outcomes as the prior parser assay, including unchanged identity on failure.
This removes the previously synthetic buffer-installation boundary for these
mode-one cases. It remains a descriptor-to-software-field experiment, **not**
RF decoding or proof of complete handler acceptance. In particular it does
not establish descriptor production, FEC, scrambling, carrier assignment or
NORAD semantics.

Receipts: `local/packet-identity-chain-descriptor.json` and
`local/packet-identity-controls-descriptor.json`; reproduce with `--descriptor`
and `--descriptor --controls`. Four focused regressions pass, including exact
case-result comparisons between the descriptor and parser-only assays.

### Continuous execution from the actual receive/parser callers

A fresh direct-call audit found calls to receive `0x27100` at `0x28c3c`,
`0x28dd0` and `0x28e0c`, and parser `0x312b0` at `0x28c0c` and `0x28e34`.
These belong to two caller entries, `0x28b80` and `0x28d50`.
The first chooses the parser context from the pointer table at outer `+8`,
indexed by the word at outer `+0x2c0`; the second uses outer `+8` directly.
Both pass outer `+0x280` to the receive routine. The first invokes the parser
after any receive return other than 4; the second can retry queue 1 after
return 4 when the outer queue byte is zero. The assay exercises a successful
first receive, not that fallback.

`packet_identity_chain.py --caller 0x28b80` and `--caller 0x28d50` each start at
the corresponding real caller and run **continuously** until the initial
identity store or a negative-control gate. No harness call separates receive
and parsing. The configured packet budget is one, pointer-table index is zero,
and the same explicit mode/descriptor/pool assumptions described above apply.
The node allocator, dequeue, mode/diagnostic queries and memcpy remain stubbed;
the caller, receive routine, wrapper, installer and parsing path execute.

Both caller entries preserve all 35 identity-pattern results and all six
framing-control results. This supersedes the receive-to-parser scheduling gap
for these constructed cases. The experiment stops inside the first handler:
it does not verify post-parse cleanup, caller completion, repeated polling,
the queue fallback, live hardware initialization or authenticity of a packet.
The missing RF demodulation/FEC-to-descriptor mapping remains missing.

Receipts: `local/packet-identity-chain-caller-28b80.json`,
`local/packet-identity-chain-caller-28d50.json`, and corresponding
`packet-identity-controls-caller-*.json` files (add `--controls`). Five focused
regressions pass; the caller regression compares both complete case sets with
the parser-only baseline.

### Actual FIFO read and descriptor translation through identity storage

The `--fifo` variant removes the `0x63f50` dequeue stub. It configures synthetic
FIFO objects and a register bank, executes the actual virtual dequeue at
`0xbe5b0`, translates the resulting word with the actual type-2 address mapper,
and continues through the receive/parser caller to the initial identity store.
It also executes the real port-status query via vtable slot `0x188ad0` →
`0xbe5e0`, reading register-bank `+0x30`; the earlier disabled-query setup is
no longer used. The queue count is one and the selector is zero.

The supplied FIFO register `+0x34` holds `0x10020000`. The type-2 mapping record
maps that synthetic address to the descriptor at `0x882000`. The descriptor
contains the pointer to the constructed packet; these test addresses are not
claimed to be actual physical addresses on a dish. Read hooks verify exactly
one four-byte read of bank `+0x34`, at least one read of bank `+0x30`, and no
other bank reads before the observed store/error gate.

Both actual caller entries preserve the 35 identity cases and six framing
controls. In particular, holding the FIFO word fixed while varying every
identity bit shows that this word is the descriptor address in this tested
route, **not the satellite identity**. The latter is read from packet contents.
No FIFO pop side effects, hardware-produced descriptor, live memory-map setup,
or RF demodulation/FEC are simulated or established. Node allocation, memcpy
and mode/diagnostic queries remain stubbed. Execution still stops inside the
first handler rather than completing a receive loop.

Reproduce with `--caller 0x28b80 --fifo` or `--caller 0x28d50 --fifo`, optionally
adding `--controls`. Receipts are `local/packet-identity-{chain,controls}-caller-
{28b80,28d50}-fifo.json`. Six focused regressions pass, including equality of
case outcomes with the parser-only baseline.

### Identity survives the updater, through cleanup entry

`--fifo --through-update` extends continuous caller execution beyond the first
store at `0x44e18`. The complete minimal version-0 updater returns to `0x552c8`,
the outer handler increments its counter at statistics `+0x3c`, and the tested
branch reaches buffer-cleanup entry `0x5522c`. All 35 identity patterns remain
stored with their channels and validity flag; the expected-identity sentinel
remains unchanged. The five malformed framing controls still stop at the
earlier gates. Seven focused regressions pass.

The statistics pointer for this later path is at **root + `0xf088`**:
`0x552c8` adds `0x8000`, then `0x552cc` loads at additional offset `0x7088`.
The earlier harness populated `root+0x87088`, which was never exercised before
its initial-store stop. The extended assay supplies the correct pointer.
This is a harness correction, not a firmware patch or a changed packet layout.

The auxiliary context's byte `+0x29a` is zero; the real `0x1003a0` query follows
the cleanup branch in this initialized test environment. Other follow-up paths
through `0x7a680` are not exercised. Buffer destruction at `0xf2960`, handler
return and subsequent packet processing remain outside the execution window.

This closes the possible later-rollback concern **for this minimal alternate-
context update only**. The updater's independent version-0 behavior was already
tested by `sysinfo_update.py`; the new evidence is its composition with the
FIFO-to-packet path. Reaching cleanup does not prove authentication, attachment,
matching the expected identity, NORAD semantics or CRC/FEC validity. The tested
branch records received information even while the expected-identity field
holds a different value.

Receipts: `local/packet-identity-chain-fifo-updated.json` and
`local/packet-identity-controls-fifo-updated.json`. Reproduce with `--fifo
--through-update`, adding `--controls` for framing controls. Default caller is
`0x28d50` for this variant.

### Primary-context composition and consistent feature queries

`--fifo --through-update --primary` selects the primary route by clearing
auxiliary byte `+0x2c4`. The same constructed SYSINFO packets now update root
`+0x41538`, preserve the different expected value at `+0x4164c`, set the byte
at `+0x41594`, and reach `0x5674c`, before follow-up message construction.
The complete minimal updater has returned at that point. The 35 identity
patterns all pass; framing controls retain their earlier gate outcomes.
This composes the previously isolated primary-store evidence with the full
FIFO-to-handler path, rather than discovering a new field layout.

The first prototype exposed an inconsistent test setup: `0xffc40` was stubbed
true but `0xffce0` read the default configuration independently, taking the
enum-4 rejection route. These query results cannot both be true for a stable
configuration. The harness now explicitly initializes the common configuration
record through global `0x1d3960`, sets its `+0x44` word to enum 1, and executes
all feature queries, removing the `0xffc40` and `0xffc70` stubs. All eight
regressions pass with this correction, including the older alternate-context
results. Earlier receipts retain their historical scope; new receipts below
use the corrected shared record. Enum 1 is not assigned a PHY-role name.

The type-15 received/expected gate at `0x562f4` is a different message branch,
already covered by the UTGW audit. It must not be used to explain type-0
SYSINFO acceptance. In the tested primary type-0 route, the comparison at
`0x55d1c` is with the **previously received** primary value, not the configured
expectation. A mismatch can still proceed to the updater at `0x5671c`.

Stopping before follow-up construction does not establish message transmission,
attachment or authentication. It does establish that a different expected
address is not an unconditional barrier to recording type-0 SYSINFO under
these explicit conditions. Primary and alternate paths still remain separate.

Receipts: `local/packet-identity-chain-fifo-updated-primary.json` and
`local/packet-identity-controls-fifo-updated-primary.json`. The alternate
`*-fifo-updated.json` receipts were also regenerated with consistent queries.

### Received address reaches internal notification without transformation

`packet_identity_chain.py --notification` executes the primary FIFO path through
notification construction and stops at transport entry `0xed500`. The caller
copies `0x9e2` bytes of the parsed SYSINFO representation into a local structure
at offset `+8` (`0x5674c`–`0x56784`) and calls `0x79040`. That helper prepares
two vectors for the transport:

| Vector | Length | Verified fields |
|---|---:|---|
| Header | 8 bytes | First LE32 word `0x14200006`; second word from root `+0x41610` |
| Payload | `0x1418` bytes | Byte 0 = 0; version at `+8`; unchanged 32-bit received address at `+9`; channels at `+13/+14` |

The combined length is `0x1420`. The header therefore contains halfwords 6 and
`0x1420`, consistent with an internal message tag/length envelope. This is not
an RF opcode or RF message length. The second header word remains the separate
synthetic marker `0x13579bdf` while identity varies; it must not be mistaken
for the received address. The destination handle is loaded from a configured
table at root `+0x462b0` for index zero. Its real runtime endpoint and receiver
are not established here.

All 35 identity patterns reach these exact output fields unchanged. The five
invalid framing cases retain their earlier rejection points. The memcpy stub
now also implements the actual `0x9e2`-byte copy. No entire-payload initialization
or meaning is claimed: this assay checks the specified fields only. It stops
before transport execution, so no notification is actually sent.

The added instructions exceeded the shared helper's 2,500-instruction cap on
the first trial. This variant now resumes that same emulator state for at most
1,000 additional instructions, with no reset or skipped code. Total instruction
budget is bounded at 3,500. Nine focused regressions pass.

Receipts: `local/packet-identity-chain-notification.json` and
`local/packet-identity-controls-notification.json`. `--notification` selects
the primary, FIFO and post-update variants; add `--controls` for malformed
framing cases. This strengthens packet-to-internal-message provenance without
establishing RF decoding, endpoint receipt or NORAD identity.

### Notification destination-table initialization

The sender's table base `root+0x462b0` is independently matched to the loop at
`0x7c89c`–`0x7c8e8`. It queries `0xffd10(1)` for a count and calls `0xed2e0`
with arguments `(2, index, field2, field3, 2, &table[index])`. `field2` and
`field3` come from the enclosing routine's W22/W23; no endpoint/process names
are assigned to them here. The output slot is exactly `root+0x462b0+8*index`,
matching the notification sender's indexing at `0x790b0`–`0x790d0`.

`notification_endpoints.py` executes this loop for counts 0/1/2/4 and three
argument pairs (12 cases). The count query and endpoint factory are stubbed;
the factory records arguments and returns distinct synthetic handles into the
requested slots. This verifies table construction, not live connection setup.
The wrapper `0xed2e0` forwards to `0xecf40`, inserting another value from a
global object at offset `+0xc`; the receiver remains to be established there
or through the enclosing initialization configuration.

A bounded immediate-constant search for the notification length in canonical
UMAC did not identify its consumer. TX contains a same-sized envelope and a
sender using `0x1418`/`0x1420`, so size matching alone cannot name the receiver.
Absence of a literal in UMAC does not exclude a table-driven or differently
compiled consumer. No downstream-process or NORAD interpretation is claimed.

Receipt: `local/notification-endpoints.json`; regression:
`test_notification_endpoints.py` passes, as does Ruff. This is a concrete
initialization link and a recorded negative search, not a completed IPC trace.

### Endpoint factory audit: runtime table selection

Fresh disassembly follows `0xed2e0` into `0xecf40`. The wrapper inserts the word
at offset `+0xc` of the global object reached through GOT `0x17fb98` into
argument W2, shifting the remaining arguments. The factory allocates a
`0x28`-byte handle through `0xfe3b0` and dispatches on the first argument.
For the notification's value 2, jump-table byte `0x4f` at `0x13e9ae`
selects `0xed16c` (`0xed030 + 4*0x4f`). That branch calls `0xffd70(1, index,
&mapped_index)` before common table selection at `0xed050`.

The common path checks the mapped index against the global object's count,
loads a per-kind table pointer and copies its selected word to handle `+4`.
Later instructions select additional words from global tables into handle
`+8/+0xc`. They build metadata at handle `+0x18`: constant byte 2, kind byte,
the original index as a halfword, another argument byte, and a halfword result
from `0x1023d0`. The factory finally publishes the handle through the supplied
output pointer. These are software routing fields, not decoded satellite bits.

This bounded static trace finds no hard-coded process pathname. Identifying
the actual receiver requires tracing the global routing-table initialization
and index-mapping functions. It does not establish that the endpoint is UMAC,
nor that the observed routing tokens encode satellite identity. No transport
was invoked. Earlier endpoint-loop execution tests do not cover this complete
factory; this subsection is explicitly disassembly evidence.

### Public decoder lead check

A fresh web search returned a potentially misleading LDPC implementation:
[Ray-Rose/tomcruise](https://github.com/Ray-Rose/tomcruise). Its directly inspected
README describes a CCSDS AR4JA decoder. It supplies no demonstrated Starlink
parity matrix or Starlink packet decode, so it is not an independent reason to
try that code family against this corpus.

[SDR-X supplement 7](https://sdr-x.github.io/starlink-supplement7/) explicitly
summarizes patent US12003350 rather than reporting a complete payload decode.
Its coding claims cannot establish that our firmware or recordings implement
the exact patented configuration. This check added no independently verified
RF-to-SYSINFO mapping. No new blind RF scan or new collection was run.

# Expected identity and received identity have different immediate sources

## Explicit control-RPC source for an initially empty request envelope

Fresh inspection of `10a000` closes an important upstream boundary. For envelope
type byte `+4 == 1`, `10a1e0` loads the context and payload pointers from envelope
`+0x18/+0x20`. With a context, it calls PLT `a5be0`, independently resolved via
ELF relocation to **`__dynamic_cast`**, using these binary RTTI types:

```text
GenericMacCtrlRpcContext
MacCtrlRpcContext<SpaceX::API::Satellites::MAC::CMInterface2::MacUpRequest,
                  SpaceX::API::Satellites::MAC::CMInterface2::MacUpResponse>
```

If the payload pointer was null and the cast succeeds, `10a510–10a534` allocates
`0xe8` bytes, supplies the typed RPC context's `+8` member to `19c420`, and
installs the constructed request at envelope `+0x20`. The inspected constructor
copies request members; at `19c520–19c53c` it copies the source's `local_id`
member at `+0x60` via `19c1c0` and installs it at the destination's same offset.
Thus an explicit control-RPC context can supply the setup request from which
the expected address is later obtained. This is not an RF-symbol parser.

The schema probe now verifies both RTTI targets, the dynamic-cast import, and
records the request-construction/local-ID-copy instruction windows. These are
static evidence checks, not an execution of allocation, C++ casting or the full
copy constructor. They establish a concrete branch, not that every request
must originate there: callers may already supply a non-null payload.

The envelope subsequently enters a state/event dispatcher at `108fd0`. The
table at `883b50` has seven pointers per state, with handler `108840` at state
1/event 1 (`883b90`). That handler checks envelope type and dispatches to
`1110d0` on one branch; this is the already-inspected active-envelope installer.
These table coordinates are software state/event indices, not RF frame types.
The external RPC transport, remote sender, role-specific admissibility and the
independent RF-to-SYSINFO byte bridge remain unresolved.

## Active and retained requests are two lifetimes of the setup source

The fallback pointer returned by `108b20` is now linked to a request-retention
operation. In `1109a0`, the active envelope is loaded from session `+0xf0`.
After processing, one branch at `110e3c–110e50` transfers envelope `+0x20`
to session `+0x190`, transfers envelope `+0x38` to session `+0x198`, and clears
envelope `+0x20`. This is pointer ownership transfer, not a fresh RF identity
measurement or a second address decoder.

[`umac_request_cache.py`](umac_request_cache.py) executes that transfer window
and the complete getter `108b20` without stubs. **12 cases pass** across three
session indices and four active-envelope conditions. With an active envelope
whose byte `+4` is 1, the getter chooses its `+0x20` pointer; with no active
envelope, or tested types 0/3, it chooses the retained request. Distinct payload
pointers distinguish the branches, and the original transferred pointer is
verified cleared. The outer handler's success/type gates and prior cleanup are
not executed by this probe.

Fresh static inspection also locates an installation path at `1110d0`: it
indexes the session by envelope word `+8`, reads envelope `+0x20`, and stores
the envelope into session `+0xf0` at `11112c`. Caller `10895c` selects this
handler based on envelope byte `+0xe`. The producer of the envelope still needs
tracing; these operations alone do not establish a network sender or transport.
Receipt: `local/umac-request-cache.json`.

One configuration qualification from fresh inspection: query `15cbc0` returns
true not only for configuration member `+0x44 == 2`, but also when the selected
configuration-record pointer is null (`15cbd8 → 15cbf4`, initial w0=1). Existing
mode-2 experiments supply a non-null configuration record. Their results remain
valid, but the shorthand "mode-2 branch" is not a complete description of this
query's behavior before configuration exists.

## Enclosing source established: MacUpRequest.local_id

The object that supplies the converter input at `102188` is identified as
**`CMInterface2::MacUpRequest`**. Its default object is `8c1ec8`, reached through
GOT `8be330`; its vtable `89d178` points through RTTI to the exact type name.
The embedded 1,782-byte `MacUpRequest` descriptor, following the length prefix
at file offset `75044f`, declares field **5, `local_id`**, of type
`CMInterface2.LocalIdentifier`.

The generated parser provides the memory-layout cross-check: its vtable entry
at `89d1c8` points to `195000`. At `195720` it checks protobuf key `0x2a`
(field 5, length-delimited), reads the existing member at object `+0x60`, and,
if needed, creates and installs that member at `195744`. This is the very
`+0x60` pointer passed to converter `d9370` by session setup at `102188–102194`.
Schema/type matching therefore joins a concrete parser member to the converter,
rather than merely associating nearby names.

The earlier call at `102158` obtains this request through `108b20`. That getter
indexes a table with stride `0x1f0`. If the record's pointer at `+0xf0` is
non-null and its byte `+4` equals 1, it returns that object's pointer at `+0x20`;
otherwise it returns the table record's pointer at `+0x190`. These two suppliers
are still upstream trace targets. No external sender or request transport has
been established by this getter inspection.

The supported chain for this branch is now:

```text
MacUpRequest.local_id (tagged API object)
  → d9370 conversion
  → session address record at +0xc8
  → session word +0xd4
  → mode-2 internal link-up request's expected-ID word
  → RX expected-ID context
```

This establishes a **link-setup API source** for that expected-ID branch, not
an immediate SYSINFO decode source. The schema calls this identifier `local_id`;
we should not rename it a remote satellite target without tracing the operating
role and variant. The firmware includes satellite/gateway/UT variants, so its
presence in dish-distributed software does not make every branch a dish receive
path. The separate received SYSINFO identity trace remains valid and distinct.

The schema probe now reproduces both descriptors, four RTTI chains, the parser
member check and the getter/caller instruction windows. These additions are
static binary checks; they do not execute the full request parser or getter.

## Named identifier variants: an important qualification

The previously anonymous tagged object is **`SpaceX::API::Satellites::MAC::
CMInterface2::LocalIdentifier`**. Two independent binary structures support
this identification: the default object's vtable/typeinfo chain, and the
embedded protobuf descriptor at file offset `0x750174` (615 bytes).
[`umac_identifier_schema.py`](umac_identifier_schema.py) extracts the descriptor
and verifies three default-object RTTI chains against the pinned binary hash.

| Converter tag | Schema field | Meaning supported by the schema |
|---|---|---|
| 1 | `satellite_id` | uint32 satellite identifier |
| 2 | `gateway_id` | uint32 gateway identifier |
| 3 | `ut_sid` | uint32 UT SID; converter marks output absent |
| 4 | `ut_ine_id` | Nested UT identifier; converter marks output absent |
| 5 | `ut_network_id` | Nested UT network identifier |
| 6 | `gw_id` | Nested `GatewayID`, with `gateway_id` and `gateway_site_id` |

These fields belong to the same protobuf oneof. Fresh inspection of the
generated parser at `19bdb0` confirms that it derives the field number by
shifting the protobuf key right three bits (`19be14`) and stores that number
at object `+0x1c` when switching variants (`19bf0c`, `19bfd0`, `19c048`).
The nested-type default objects used by converter `d9370` identify as
`LocalIdentifier_UtNetworkId` and `LocalIdentifier_GatewayID`. This is stronger
than assigning names from adjacent strings.

**The session word at +0xd4 is not unconditionally a satellite ID.** The
executed tag-1 branch copies `satellite_id` there. The executed tag-6 branch
copies the nested `gateway_id` into that same output member, while copying
`gateway_site_id` to the following member. The mode-2 request builder later
copies session+0xd4 into the field its diagnostic labels `satellite_id`.
The static link and converter tests establish this possible representation;
they do not prove that the outer mode-2 flow admits every variant. It is
essential to recover the admitted variant before interpreting an observed word.

This refines the earlier expected-ID terminology: it accurately describes the
downstream use, but not necessarily the upstream identifier namespace. Neither
the `satellite_id` field name nor its uint32 representation establishes a NORAD
mapping. Protobuf keys here describe an internal API serialization, not the
location or encoding of identity in Ku-band symbols. The ultimate producer of
this API object and the RF-to-SYSINFO mapping remain open.

Receipt: `local/umac-identifier-schema.json`. The schema extraction test checks
all six field numbers/names, the oneof, nested gateway fields and RTTI. The
generated protobuf parser was inspected, not executed by this new probe.

## Tagged software object upstream of the session address

The global-session branch has a newly traced producer: `102188–102194` loads
an object pointer from `x24+0x60`, supplies `session+0xc8` as destination, and
calls `d9370`. The converter reads the source's discriminator at `+0x1c`.
This destination places converter output `+0xc` at **session+0xd4**, the word
already traced into the mode-2 request's expected-ID field. This is a static
caller-to-callee link plus execution of the complete converter, not a full
execution of session initialization.

| Source tag | Output presence | Output kind at +4 | Written value fields |
|---|---:|---:|---|
| 1 | 1 | 1 | Source +0x10 → output +0xc |
| 2 | 1 | 3 | Source +0x10 → output +0x10 |
| 5 | 1 | 2 | Child pointer at source +0x10; child +0x18 → output +8 |
| 6 | 1 | 3 | Child +0x10 → output +0xc; child +0x14 → output +0x10 |
| 0, 3, 4, 7 | 0 | Unchanged | Other output bytes unchanged |

All unlisted output bytes remain untouched in these branches. In particular,
tags 2 and 5 do **not** populate session+0xd4 through this converter. We must
trace the admitted variant and object lifetime before generalizing the
expected-ID origin. The converter always returns zero for these cases;
return status alone therefore does not indicate a present address.

[`umac_address_variant.py`](umac_address_variant.py) executes `d9370` through
return without stubs: **280 cases**, covering all eight tags, zero, all ones,
a mixed value, and every one-hot bit. Distinct second-word inputs distinguish
the two tag-6 copies; poisoned output and canaries verify fields left unwritten.
Receipt: `local/umac-address-variant.json`.

The tag names are now resolved in the follow-up above; source deserialization
execution and network provenance remain unproved.
This is an in-memory tagged-object conversion, not evidence of those tag numbers
appearing in an RF header. Likewise, the optional target record's offsets
`+0xd8/+0xe0` must not be equated to this layout merely because they resemble
presence/value members. Finding this converter supplies a specific upstream
object and discriminator to trace; it does not yet establish a NORAD mapping.

## Target-context construction and lookup

The UMAC request builder's context is now linked to concrete session-table
objects. Session records have stride `0xf0`; `101560` selects a pointer from
`+0x18` when its second argument is zero, or `+0x70` otherwise, indexed in
eight-byte units. Their counts are at `+0x14` and `+0x68`, respectively.
The code bounds each pointer array to ten entries. These family selectors are
not assigned a radio-direction meaning here.

Function `1020b0` contains construction paths at `102218` and `1024a4` that
request **0xcf4 bytes**, clear that region, initialize bookkeeping, and install
the resulting pointers into the two arrays. This size accommodates the two
`0x64c` records beginning at context `+0x50`, plus trailing bookkeeping.
The two records' optional-ID presence bytes (`record+0xd8`) and ID words
(`record+0xe0`) are initially zero. Thus these constructors do not supply a
meaningful expected satellite address; subsequent population is still required.

[`umac_target_lifecycle.py`](umac_target_lifecycle.py) executes each initialization
window after allocation, including the real pointer installation, then the real
lookup window. All **20 cases** (two families, ten indices) recover the installed
pointer and verify both absent/zero target IDs and surrounding-memory canaries.
The resolved libc `memset` call is stubbed; allocation, outer dispatch,
initialization/session-count checks preceding the lookup, and later population
are not executed. This is synthetic instruction execution, not a captured
control-message decode. Receipt: `local/umac-target-lifecycle.json`.

This narrows the next trace to writes into these installed objects. The lookup
by context member `+0xc` at `101ab0` and its caller `ff314` are additional
navigation anchors, not yet evidence of the target-ID producer. The initial
probe failed because its pre-object canary lay outside mapped emulator memory;
extending the synthetic mapping fixed the harness without changing firmware.

## Upstream search exclusions

A fresh search for construction of the UMAC target record rejected two tempting
offset/size matches. At `f7b6c/f7cc4`, stores at object offset `+0x130` belong
to a dynamic-string length beside its `+0x134` contents, not an established
satellite-ID field. At `164cc8`, `164cdc` and `164d28`, an immediate `0xc98`
is followed by `movk ..., #0xa, lsl #16`: the actual size is **0xa0c98**,
not two `0x64c` target records. Those instructions compare, map and initialize
a larger region; they do not establish the sought target-record copy.

These are static instruction findings, not new execution or RF experiments.
The source of the optional target record remains unresolved. Matching an
offset or the low half of a constructed constant is insufficient provenance.

Fresh disassembly locates a producer for the expected-ID context member used in
the already-tested SYSINFO mismatch gate. This strengthens the distinction
between a configured expectation and a decoded received address. It does not
yet identify where the expectation originates outside this call chain.

All addresses refer to the canonical RX LMAC binary, SHA-256
`9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe`.

| Value | Immediate source | Evidence |
|---|---|---|
| Expected ID at root `+0x4164c` | Input argument structure `+0x5e4` | Function `41d20`, load/store at `41e30/41e34` |
| Received/context ID at root `+0x41538` | Decoded type-15 body address, subject to mismatch gate | Previously executed `562ec–56324` path |

At function entry `41d20`, x19 receives argument x1 and x21 receives argument
x0; x20 becomes x21+0x40000. The new two-instruction producer is:

```asm
41e30: ldr w0, [x19, #0x5e4]
41e34: str w0, [x20, #0x164c]
```

The new bounded emulator probe supplies these live registers and tests zero,
all ones, `0x12345678`, and all 32 one-hot values: **35 cases pass**, including
surrounding-memory canaries. The received-ID member remains unchanged in this
window. This demonstrates a full-width copy, not a hash, mask or NORAD conversion.
It does not execute the preceding function gates or later state changes.

Caller `45470` preserves its second argument in x20, restores it to x1 at
`454f8`, and calls `41d20` at `45514`. The current call catalog supplies further
caller anchors `45d7c`, `45e20`, `466f8` and `46e90`; their input producers and
branch reachability remain the next audit target. Diagnostic strings mentioning
up requests elsewhere in this area are leads, not sufficient proof of a
management-plane origin.

## Follow-up: link-up request path

The next audit traces one upstream path through `45e30`, whose diagnostic
at `10e8c0` names it **mac_beam_slice_handle_up_req**. The actual reference to
that string is at `4669c` in its logging branch. We can now associate the
expected-ID input with an up request, rather than just an unnamed structure.

The internal message dispatcher at `75210` validates a buffer through `ce1c0`.
The inspected type-2 branch reaches `75ee0`: it reads an operation byte at
envelope+8 and calls `467b0`. That operation dispatcher selects value 1 and
supplies `envelope+12` as request body, with a 16-bit length from envelope+10,
to `45e30`. These are internal message types, not the over-the-air SYSINFO
message type numbers.

One path copies the request body to `root+0x4acd8` using the resolved libc
`memcpy` import. A later path at `45d70` passes that cached request to `45470`,
which calls `41d20`, the already-inspected expected-ID initializer. Another
path at `466f0` passes the input request directly. Thus request body+0x5e4,
or this envelope+0x5f0, can supply expected context root+0x4164c.

The new [composed execution probe](identity_request.py) tests the real argument
extraction, cache-copy callsite, cached-pointer calculation and identity-store
windows for **35 IDs**, including all one-hot bits. It stubs only the libc
memcpy port; registers between windows are explicitly initialized according to
the inspected call interfaces. All cases preserve the complete ID. This proves
the local transfers, not full state-machine reachability or an end-to-end
packet execution. The earlier input producer is still unknown: this audit does
not establish whether a remote scheduler, local configuration or another service
originally supplied the up request's identity.

Reproduce with `identity_request.py` using the same dependencies as above;
`test_identity_request.py` is the component test and
`local/identity-request.json` is the ignored execution/disassembly receipt.

## Follow-up: a UMAC producer with the same field meaning and offset

The separately extracted `catson--bin--umac` contains a request-building routine
with a diagnostic at file/virtual address `674ba0` that labels session ID and
**satellite_id**. Its logging branch at `102fe4–10302c` loads satellite ID from
the output object at `+0x5e4`, independently matching the RX request field offset.
This is a strong producer candidate; matching name and offset do not alone prove
the entire cross-process serialization and transport connection.

Fresh instruction inspection locates two assignments to that output field:

| Assignment | Source | Tested behavior |
|---|---|---|
| `102d10–102d18` | Global-context-derived record `+0xd4` | Copies all 32 bits |
| `102fa0–102fbc` | Target record base `root+0x50+index_offset`; presence byte `+0xd8`, value `+0xe0` | Loads value if presence is nonzero; otherwise retains incoming w26 |

The parent branch is selected by a call to `15cbc0`; its semantic meaning is
not established in this audit. Neither the incoming w26 fallback producer nor
the global/target record producers have been resolved. In particular the test
does not justify calling an absent value zero or assigning a satellite identity
to a default constant.

The [UMAC probe](umac_identity.py) maps actual ELF load segments and executes
both assignment windows for **105 cases**: 35 values through each of present,
absent and global-record paths. The input set includes all 32 one-hot values.
The optional-field test initializes w26 to a deliberately distinct sentinel;
every absent case preserves it. Output canaries verify the optional assignment
does not overwrite adjacent fields. These are window executions with prepared
registers, not complete request construction or a real received satellite ID.

The existing control slate also supplies an independent architecture lead:
`catson-dat--common--control_to_lmac_tx` declares `beam0_targets.satellite_id`
as int32 and comments that beam targets come from CM when commanding pointing.
That text is not an executed dataflow connection to either UMAC source above,
and does not demonstrate a NORAD mapping. Preserve the distinction between
documented intent, executed field transfers and unresolved source semantics.

The next decisive step is to trace the UMAC output through its serializer and
transport to the RX internal envelope, then resolve the target/global producers.
The independent RF→decoded SYSINFO-buffer chain remains unfinished.

Reproduction: run `umac_identity.py` with pyelftools, capstone and unicorn;
`test_umac_identity.py` is its component test. The binary hash is checked against
the existing extracted corpus manifest and saved with instruction windows and
method hash in ignored `local/umac-identity.json`. All five tests in this receive
trace directory pass. No native firmware execution, network capture, RF collection
or fixture changes were performed.

## Follow-up: constructed UMAC bytes survive an RX handoff

We now have evidence stronger than matching field offsets. UMAC `1029cc–1029e4`
writes message type 2 and an operation byte to envelope+8. Operation 1 selects
the request construction path, where `102b80` sets the body pointer to
envelope+12. The previously executed satellite-ID store therefore writes
envelope+0x5f0. UMAC `102aa0–102acc` sets envelope/body lengths and passes the
buffer pointer and length to a callback. No separate serialization operation is
visible in that final handoff window.

The callback is no longer wholly unresolved. Two ELF `R_AARCH64_RELATIVE`
relocations connect GOT `0x8bbb70` → table `0x8c0650` → initial function
`0xe2210`. The latter checks initialization, calls `0xe1f50` to prepare routing,
then passes the payload and length to `0x147c70`. This is static evidence of the
initial target; runtime callback replacement is not ruled out, and the final
transport function and receiving endpoint are not yet verified.

The new [cross-binary probe](identity_handoff.py) executes UMAC's actual header,
body-pointer, identity-store and callback-argument windows; manually transfers
the resulting bytes to synthetic RX memory; then executes RX's body extraction
and expected-ID store. **All 35 ID cases survive unchanged**, including zero,
all ones and each single bit. The test applies the two actual ELF relocations
and verifies the callback pointer before the indirect call. It supplies a body
length of 0x63b and total length 0x647; it does not execute construction of all
other fields, full validation, the callback or the intervening state machines.

This establishes byte-layout compatibility and a concrete constructed-field
handoff, not delivery over a live connection. It also narrows the search: the
setup identity arrives as an explicit UMAC request field, rather than being
calculated from RF samples by the inspected RX initializer. Its original UMAC
source and the independent RF-to-SYSINFO route still need tracing.

Reproduce `identity_handoff.py` with capstone, pyelftools and unicorn. Its
component test is `test_identity_handoff.py`; ignored receipt is
`local/identity-handoff.json`. Six receive-trace tests now pass.

## Follow-up: ordinary SYSINFO reaches primary or alternate received context

The received-ID route is broader than the previously tested type-15 UTGW path.
Freshly inspected ordinary SYSINFO handling calls `44da0` at `5671c`, passing
the decoded body. Its helper `44c60` selects a context using
`*(root+0x53378)+0x2c4`: zero selects `root+0x41538`; nonzero selects
`root+0x415a0`. This is an internal context selector, not a proved on-air beam bit.

The handler prefix loads the body address from unaligned body+1 and stores it
at selected-context+0. It also copies body+5/+6 to selected-context+0x5a/+0x5b,
copies the decoded version to selected-context+0x48, and sets byte +7 to 1.
If the previous version matches, it compares address/channels first; the
inspected routes still converge on the address store. There is no NORAD
conversion in these operations.

The new [SYSINFO-to-context probe](sysinfo_context.py) first executes the real
minimal body decoder and bit reader on synthetic known-format bytes, checks its
success status, then explicitly invokes the real `44da0` prefix and selector.
It stops at `44e18`, before later feature tests. **140 cases pass**: 35 address
values × two selectors × two previous-version values. The cases include every
single address bit, zero and all ones, with channels 7 and 9. The other received
context and expected-ID member `root+0x4164c` remain unchanged in this window.

This closes a concrete software link from known-format SYSINFO bytes to received
identity context. It does **not** execute the outer handler's admission checks,
subsequent processing, or the RF-to-buffer decoder. It therefore does not show
that any arbitrary transmitted address would be accepted by a live terminal.

The minimal software representation places the address after its 11-bit
envelope; that previously established serialization offset is still not an
RF carrier/time coordinate. The next needed evidence is upstream: which
integrity-checked receive buffers supply this decoder, and what hardware coding
and mapping produce their bytes.

Reproduce `sysinfo_context.py` with capstone, pyelftools and unicorn; its test is
`test_sysinfo_context.py` and ignored receipt is `local/sysinfo-context.json`.
The earlier pending handoff receipt refresh completed successfully; its method
hash and lint check are current.

Consequently an expected satellite ID observed in firmware memory or telemetry
cannot automatically be treated as freshly decoded RF identity. Conversely, a
configured expectation does not erase the independent SYSINFO address decoder.
We must trace both paths and their comparison. Neither value has a proved NORAD
mapping, and the RF/FEC-to-message-buffer link remains unresolved.

## Missing UMAC target identity defaults to zero on the successful path

The previously unresolved inherited `w26` value has a concrete source on the
successful request-building path. At `1029b8`, UMAC copies the preceding
validation result from `w0` to `w26`. A nonzero result exits; proceeding also
requires the selected session to match. Thus this path reaches construction
with `w26=0`. In the non-enum-2 mode branch, optional target presence at
record `+d8` controls whether record `+e0` replaces that zero before the
request identity store at `102fbc`.

`umac_missing_identity.py` executes from that post-validation boundary through
request construction and the real mode query to the identity store. It supplies
a successful result and matching session, not a stubbed validation verdict
inside a full function. Only the ELF-resolved `memcpy` import is stubbed.
All **140 cases** pass: two target indices, present/absent, and 35 ID patterns.
An initial nonzero `w26` sentinel is overwritten. Absent fields produce zero;
present fields preserve every bit, including an explicitly present zero.

Therefore a zero expected address can result from an omitted setup field. This
does not prove that zero has a universal protocol meaning, nor that any
particular DS7–DS10 visit used this branch. The target record's original producer
and the separate global-record mode remain unresolved. The earlier isolated
assignment-window test correctly preserved an arbitrary fallback; the longer
path now constrains that fallback to zero under these preconditions.

Test `test_umac_missing_identity.py`; ignored receipt:
`local/umac-missing-identity.json`, with binary/source hashes. No new RF scan.

## PPS anchor origin and nominal counter rates

The complete updater `79bc0` calls real register getters `7cfb0` and `7d000`.
For nonzero direction, the local latch is read via I/O-object `+18`, register
`+0c`, and the current counter via object `+20`, register `+30`. Direction zero
uses object `+38`, registers `+04/+0c`. Both getters mask to 31 bits. The peer
PPS value comes from the updater's second argument; its IPC producer is not
yet traced here.

After freshness checks, an already-valid anchor is checked for compatible
elapsed intervals. Nonzero direction uses local rate 540,000,000 and peer rate
480,000,000, adding half the respective rate before unsigned division; zero
direction swaps the rates. If the rounded interval counts agree, the updater
stores the new local/peer pair and sets validity. If they disagree, it clears
validity and returns 13, retaining the old pair. The firmware status-name table
at `d3f80` names code 13 `timing_error`.

`pps_anchor.py` executes the entire updater and both register getters with
synthetic register memory. Only the logging-enable query is stubbed. Sixteen
cases cover both directions, bootstrap, matching increments, 31-bit rollover,
incompatible interval counts, and ignored hardware high bits. All pass; test
`test_pps_anchor.py`, ignored receipt `local/pps-anchor.json`.

**Inference:** the 1PPS diagnostics and 540,000,000/480,000,000 interval constants
support nominal 540/480 MHz counter domains, consistent with the separately
verified 9/8 conversion. This is stronger than inferring units from the ratio
alone, but is not a calibrated measurement or a proved mapping to SDR sample
indices. Exact physical register mapping, peer IPC and absolute epoch remain
unresolved. The existing register and PPS chain concerns receiver-local timing,
not a timestamp field proved transmitted in SYSINFO.

## Burst timestamps cross clock domains through PPS anchors

Fresh instruction inspection changes the earlier description of `79e90`: it is
a **clock converter**, not a timestamp lookup. Its diagnostics explicitly name
peer/local PPS measurements and `conv_peer_l2_to_local_l2`. The object stores
local anchor at `+4c`, peer anchor at `+50`, and validity at `+54`.

For direction argument 1, used by RF feedback at `3abc4–3abcc`, the arithmetic is:

```text
delta = signed_31_bit(input - peer_pps_anchor)
scaled = truncate_toward_zero(delta * 540000 / 480000)
output = (local_pps_anchor + scaled) modulo 2^31
```

Direction 0 reverses the ratio to 480000/540000 while using the same supplied
object's anchor members. The caller masks its input to 31 bits; the function's
signed extraction also discards the high bit. At the half-range boundary,
`0x40000000` is interpreted as a negative difference. Missing valid PPS state
returns status 13 without writing output; the feedback caller proceeds to the
telemetry construction path only on status zero.

`phy_timestamp.py` executes the complete conversion function with only the
diagnostic-enable query stubbed. **360 cases pass**, covering both directions,
valid/invalid PPS state, three anchor pairs, positive/negative/half-range
differences, fractional rounding and high-bit invariance. Component test:
`test_phy_timestamp.py`; ignored receipt `local/phy-timestamp.json`.

The ratio is exactly 9/8 in the feedback direction. These constants alone do not
prove units of Hz, ticks/ms, epoch, or a conversion to our SDR sample clock.
Additional mode-dependent corrections after this call also remain outside this
test. The result supports a PPS-anchored receiver clock interpretation of the
timestamp accompanying identity; it is not evidence for a transmitted 31-bit
time field.

## Feedback dispatch independently verifies type and buffer-size correspondence

`phy_feedback_route.py` executes RX's header-building instructions at
`7a6b4–7a700`, producing bytes `07 00 b8 00`, then manually transfers those
bytes into PHY memory and executes the dispatcher from `3c400`. The dispatcher
reads message byte zero and calls `3ab20` for type 7. That handler admits the
tested path only when its **supplied length argument** is exactly 184.

Thirty cases cover neighboring types 6/8, supplied lengths 0/183/184/185/256,
and two values of the embedded length halfword. Only type 7 with supplied
length 184 reaches the RF-info body path. Changing the embedded length does
not affect this particular gate. This is not a malformed-buffer safety audit:
every test uses a full-size backing allocation, and a transport layer may
validate or derive the supplied length before this dispatcher.

This closes the previously static-only type/size link between the RX builder
and PHY consumer. It does not exercise transport or complete body processing.
Test `test_phy_feedback_route.py`; ignored receipt `local/phy-feedback-route.json`.

The fresh upstream audit found that MODCOD numerical constraints, CGM table
alignment and header-decoder status were already covered in the prior
`firmware-header-analysis.md` audit. No new coding/interleaving constraint was
established, so those results do not authorize another blind RF scan. The
unresolved RF-to-message byte transformation remains explicit.

## PHY burst telemetry receives identity from MAC feedback

PHY `3ab20` is associated with the diagnostic name `process_ut_rf_info_msg`.
Its size check expects `0xb8` bytes, matching RX feedback builder `7a680`.
The RX builder's address at stack `+e8` is message-relative `+58`, because the
message starts at stack `+90`. PHY reads precisely message `+58`, with DL/UL
channels at `+5c/+5d`. This links two executable layouts without guessing from
the name `sat_id` alone.

`phy_identity_handoff.py` executes the RX field stores, manually transfers
the resulting message bytes to PHY memory, and executes PHY's cache and
telemetry-construction windows. **70 cases pass**: 35 address patterns including
every single bit, crossed with message flag `+98` zero/nonzero. When zero, PHY
copies the address to global-state `+2164`; when nonzero, that cache write is
skipped. Both tested telemetry-construction windows copy the message address to
stack `+134` and DL channel to `+178`. Other paths and flag semantics are not
established by these windows.

The diagnostic at `3ae54–3aea8` labels stack `+134` as `sat_id` in a
`phy_fsw_burst_det_info` report. Thus **this PHY telemetry identity is supplied
by the MAC feedback message**, not independently decoded from RF by the
inspected PHY instructions. It can be downstream evidence of received SYSINFO,
but counting it as an independent identity observation would be circular.

The manually transferred buffer contains actual RX-built identity/channel
fields; it does not reconstruct the complete feedback message or exercise its
transport. The PHY size gate is inspected statically, not executed in this
window test. Clock conversion `79e90` (tested separately above), intervening
mode gates and telemetry publication are outside this handoff test. The timestamp undergoes
additional processing before publication and must not yet be assumed identical
to the raw descriptor word.

Test: `test_phy_identity_handoff.py`; ignored receipt:
`local/phy-identity-handoff.json`. Source hashes and instruction windows cover
both canonical RX and PHY binaries. No hardware or new RF collection.

## Burst detection metadata binds SYSINFO to PHY feedback

A newly traced link connects received identity state to hardware-facing receive
metadata. The word copied to selected SYSINFO context `+64` is read from copied
descriptor metadata **+8** (`2716c`), stored at receive-context `+10`
(`27170`, containing-object `+290`), and conditionally snapshotted by SYSINFO
(`45080–4508c`). The previously tested snapshot condition is mode 1 and separate
query value 3.

Feedback builder `7a680` reads the current containing-object `+290` into its
message at stack `+98`. Its diagnostic at `7a8a4–7a8f0`, referencing string
`1173a8`, labels that argument **burst_det_timestamp**. The same builder copies
the selected received address and channels into stack `+e8/+ec/+ed`; the
diagnostic labels those fields `sat_id` and `dl/ul_ch_id`. This is a software
association between identity, channels and a receive descriptor's timestamp.
It is not yet a decoded on-air timestamp or a NORAD association.

In mode 1, `7a734–7a778` compares current burst timestamp against selected
SYSINFO context `+64`. Unequal words bypass feedback construction and increment
a saturating 16-bit counter at the statistics object's `+ca`; equal words
continue. Mode 4 bypasses this particular equality gate (other builder branches
are not bypassed by this finding). This supports an interpretation that the
gate prevents feedback from combining different burst contexts.

`burst_identity_binding.py` composes actual descriptor-copy and snapshot
instructions with the actual equality gate and configuration query. **840 cases
pass**: 35 timestamp patterns, primary/alternate contexts, same/different words,
modes 1/4, and three counter states including saturation. No calls are stubbed
inside these windows, but the phases are explicitly composed with prepared
registers. The complete builder, transport, timestamp-producing hardware and
clock conversion are not executed. Regression test:
`test_burst_identity_binding.py`; ignored receipt:
`local/burst-identity-binding.json`.

This is a stronger RF-facing connection than a field-name match: a received
descriptor word is retained alongside decoded SYSINFO and compared before
identity-bearing PHY feedback. Its units, epoch, rollover period and relationship
to our SDR sample indices remain unknown; do not search RF bits for its raw
32-bit representation on this evidence alone.

## Complete minimal updater: return value indicates change

`sysinfo_update.py` now executes the entire `44da0` function through return for
the minimal version-0 body, including actual configuration queries, with no
call stubs. Across 120 cases (six mode values, two selected contexts, two values
of the separate `ff9e0` query, and five prior-state configurations), the received
address remains stored and valid on return despite a different configured
expectation. The other context and expectation remain untouched.

For this body format, the return is **0 when address, channels and version are
unchanged; 1 when any one differs**. It is therefore a change indicator on these
paths, not an address-mismatch error code. Setting the valid byte from zero to
one alone does not set this return. This corrects a potential misinterpretation
of subsequent caller branches testing the return value.

Mode 1 with the separate query value 3 also copies containing-object `+290` to
selected-context `+64`. The test verifies the transfer but does not assign the
word a timing or identity meaning. Other tested combinations leave that member
unchanged. Directly calling the updater in all six modes does not imply that
the outer dispatcher admits SYSINFO in those modes; the routing table below
remains authoritative for the tested outer path.

Component test: `test_sysinfo_update.py`; ignored receipt:
`local/sysinfo-update.json`. The entire outer message handler, nonminimal body
versions, and the RF-to-buffer decoder remain outside this execution claim.

## Ordinary SYSINFO routing differs from the UTGW identity gate

The earlier type-15 UTGW mismatch result must not be generalized to type 0.
`sysinfo_mode_route.py` now composes the actual minimal version-0 body decoder
with the post-decode dispatcher at `55288`, actual configuration queries, and
the `44da0` store prefix through `44e18`. Only the logging-enable query is
stubbed; the root and decoder output are synthetic. The mode word is the same
configuration tested by the earlier UTGW experiment, not an inferred PHY role.

| Tested configuration | Type-0 result up to the store boundary |
|---|---|
| Mode 0, 2, 3 or 5 | Unsupported-type route |
| Mode 1, primary context | Store received address |
| Mode 1 or 4, alternate context | Direct call to address handler; store in alternate context |
| Mode 4, primary context, root+41650 zero | Rejection route before address store |
| Mode 4, primary context, root+41650 nonzero | Store received address |

All **96 cases pass**, with 28 reaching an address store. Each configuration
tests zero expected, equal addresses, zero received, and unequal nonzero
addresses. The selected context gets the received value; the other context and
configured expectation remain unchanged. These results include expected=10 and
received=0xffffffff: a mismatch does not prevent this prefix's write on the
listed store routes. The minimal-body path's comparison with the *previously
received* primary address at `55d1c` can proceed through logging to the handler.
It must not be confused with a received-versus-expected admission check.

The alternate path passes flag 1 to `44da0`; the primary path passes flag 0.
Both are stopped after the initial context assignment, before subsequent
feature-dependent processing. We do **not** claim full message acceptance or
that every SYSINFO version follows these branches. Nor does executing synthetic
known-format bytes demonstrate that we have decoded such bytes from DS7–DS10.

One prototype failure was a harness composition error: the body decoder reused
the same memory as its bit reader that the outer handler needed as an object.
Restoring the outer object's root pointer after decoding fixes that error;
no firmware instruction was patched to make the route pass.

This strengthens the evidence that received identity is a distinct source from
the configured expectation, while narrowing exactly which modes and message
types support that statement. Next unresolved boundaries are later acceptance
policy and, upstream, the hardware/FEC-to-SYSINFO byte mapping. Reproduction:
`sysinfo_mode_route.py`; component test `test_sysinfo_mode_route.py`; ignored
receipt `local/sysinfo-mode-route.json` includes instruction evidence and hashes.

Reproduce from repo root:

```bash
uv run --no-project --with capstone --with pyelftools --with unicorn python starlink_firmware/apk_fw_v1/reports/2026_09_30_rf_receive_trace/expected_identity.py
uv run --no-project --with pytest --with capstone --with pyelftools --with unicorn pytest -q starlink_firmware/apk_fw_v1/reports/2026_09_30_rf_receive_trace/test_expected_identity.py
```

Ignored receipt: `local/expected-identity.json`, including fresh disassembly,
binary and method hashes, synthetic inputs and observed values. No hardware
access, RF collection or fixture changes.

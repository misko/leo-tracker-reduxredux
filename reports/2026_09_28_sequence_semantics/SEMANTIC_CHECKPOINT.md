# Semantic decoding checkpoint

GMH padding verified: tx routine0xc1ac0 queried bits, adds zeros to align
(bits+8), appends8 zeros, then returns byte count. Caller0xc1294 supplies8;
non-signaling alignment32 bits. 768 emulated cases modes0/1/2 lengths0..255
include real writer word crossings and preserve inputs. Caller loads returned
bytes at0xc12bc and masks6bits at0xc1374 for long prefix: length unit is bytes
on this path. No proof the zero trailer survives later hardware processing.
Evidence local/firmware/gmh-padding-verification.json. Next: MCS entry writer
and upstream field validity/meaning, then RF candidate constraints.

TX header packing verified: tx_lmac 0xc1368..0xc13e0 creates short8/long16
prefixes; bit0/1=0 in non-signaling path, bit2=input flag, bit3=long flag,
bits4..5=unresolved inputs. Short bits6..7=count; long bits6..11=length,
bits12..15=count, consistent with RX diagnostic labels. 400 isolated emulated
cases match; actual writer0xe1430 confirms LSB-first cached placement. Results
local/firmware/gmh-prefix-verification.json. No full builder/FEC/RF roundtrip.
Next: trace remaining input meanings and appended codeword/MCS table writing.

Generator-independent 114-bit check: blind_header_114.py uses GF(2) elimination
on all seven-tap paired-stream relations at eligible within-symbol starts.
5,010 configurations, no exact discovery relation, hence none to evaluate.
Two tests pass with alternate synthetic generators, unseen words, corruption,
random and constant controls. Still restricted to direct serialization,
fixed-mask cancellation and activity-qualified columns; not exclusion of coding.
Next useful work is firmware placement/interleaving or header generation, not
another permutation of the same three guessed generators.

Downlink applicability progress: scheduler 0x92734 supplies ID0 to 0xe9ca0;
failure assertion names mcs_table_mcs_query_dl(MAC_GMH_MCS,...). Success uses
helper0x90020, which counts codewords by record+8 and accumulates symbols with
record+4 (0x90118–0x90134): 114 symbols per complete 32-bit unit. DL root is
0x1b1d90, distinct from 0x1afbe8 used by 0xe8520 and an UL consumer. All three
source-table selectors observed initializing DL have identical ID0 records.
This strengthens relevance of 114, but does not identify the encoder or prove
one unit spans the whole observed header. Evidence downlink-gmh-mcs-path.txt.

114-bit RF probe completed: 10,020 eligible within-symbol combinations with
assumed octal 133/171/165 generators, all stream permutations and both carrier
orders/directions. No exact discovery relation; selected error .413194 becomes
.513889 on separate evaluation frames. No supported decoder. Necessary parity
checks only, not termination-state validation. Result local/moving_header_code_114.json.
Three focused tests and lint pass. User explicitly directs future recording
work to use DS7+DS8+DS9; DS9 manifest located at
reports/2026_09_28_ds9_post_ds8/manifest.json (105 admitted recordings).
Next firmware work should constrain generator/interleaver/header-mode selection;
do not mistake this negative result for rejecting all 114-symbol encodings.

Packed-MCS progress: diagnostic branches identify MAC +4 as symbols/codeword
and +8 as bits/codeword. For all nonzero IDs, PHY second word gives candidate
N=64*(W&511), m=1+((W>>14)&7), K=8*((W>>17)&16383): ceil(N/m)=MAC+4,
K=MAC+8, bit31=even symbol count. Bits9..13 consistently index K/N ratios.
Entry0 in all three MAC source tables is 32 bits/114 symbols, compatible with
(32+6)*3 convolutional encoding. This is not validated RF decoding; next useful
test is a 114-bit terminated-code hypothesis, with applicability/order/scrambler
still unresolved. PHY entry0 duplicates68 and is not its coding definition.

Resolved PHY modcod source to constant 0xaeba0. Actual loader emulation verifies
all 8192 modeled-memory writes. There are 256 word-pairs, 132 unique; entries
133–255 and 68 repeat entry 0. MAC source tables at rx_lmac 0x12fb88/0x12f328
each contain IDs 0–132, supplying the GMH MCS lookup. For all 132 nonzero IDs
in both tables, PHY first word = ceil(MAC record field at +4 / 2) - 1.
Evidence: local/firmware/phy-modcod-table.json and verify_modcod_table.py.
Next: interpret the second packed word and MAC field units. No new RF semantic
fields decoded; ID 0 is a numerical exception, not a validated header mode.

PHY configuration progress: identified `init_modcod_table` at phyfw 0x5edf0
and `init_cgm_table` at 0x5ee40 through assertion-checked calls. Extracted two
256-word constants at 0xaf3a0/0xaf7a0; field meanings unverified. The 512-word
modcod source is loaded through object member 0x2d0 and written pair-swapped,
repeated sixteen times. Next: trace that member's producer, rather than infer
coding parameters from table names. No additional RF fields decoded yet.

Resolved indirect receive call: initialization uses factory 0xbe660 and vtable
0x188aa0; relocation 0x188ab0 resolves the method to 0xbe5b0. The seven-instruction
method reads a 32-bit register value through two pointers. 100 isolated emulated
cases verified exact memory reads and return values. Helper 0xfe6b0/0xfdc60 then
translates that value to a descriptor address. No FEC/descrambling is performed
in this immediate receive-method path. Next target: upstream hardware settings
or firmware blobs rather than treating this method as a software radio decoder.

Receive-path follow-up: routine 0x27100 obtains a descriptor through 0x63f50,
copies its first 16 bytes via verified memcpy PLT entry 0x21e70, then extracts
a separate payload pointer at descriptor offset 0x10 and wraps it for MAC.
Descriptor flag bytes are local interface metadata, not verified air-header
fields. Next target: resolve the virtual-method call at 0x63fb8 and its object
construction. This is static flow evidence, not an end-to-end RF decode.

Bit-reader follow-up: actual initialization, reading, and position-query routines
passed 11,064 reads over 200 byte buffers, including 5,255 word crossings.
Software-interface byte order is little-endian/LSB-first; RF bit order is still
unknown. The direct GMH caller at 0x313fc uses this same initialized reader.
See the firmware-header-analysis follow-up; the next unresolved link is the
PDU buffer's PHY/hardware origin, not the cached-word reader behavior.

Latest code analysis: receive-MAC function 0xc6240 has short/long/signaling
header paths and a conditional table-reading path with 20-bit entries split
into 8-bit MCS and 12-bit codeword-count values according to adjacent diagnostics.
The bit reader at 0xeada0 passed 100 isolated ARM64 emulation cases for its
non-crossing cached-word extraction path. This is downstream MAC evidence,
not yet RF field decoding. Details and limitations:
[firmware header analysis](../../docs/research/starlink-literature/firmware-header-analysis.md).

Firmware acquisition obstacle resolved: the public APKCombo app bundle was
downloaded and both embedded dish bundles parsed. Actual AArch64 `phyfw`,
`rx_lmac`, and `tx_lmac` binaries are now available under ignored
`docs/research/starlink-literature/local/firmware/catson-bin--*`. See the
[updated provenance and extraction findings](../../docs/research/starlink-literature/firmware-leads.md).
This supersedes the APK acquisition status below. No firmware-derived on-air
header interpretation has yet been verified. Next: static code-path analysis.

Latest local progress: [short-header probes](SHORT_HEADER_PARITY.md) tested
frequency prefixes with inferred parity masks and arbitrary within-symbol starts
with an assumed 133/171/165 convolutional code. Neither supplied a validated
decoder; the latter's discovery-selected candidate had 46.7% evaluation syndrome
errors. Public firmware inspection obtained a Linux partition but found no PHY
or lower-MAC runtime binaries. APK bundle acquisition remains unresolved.
These are completed bounded investigations, not running jobs or proof that a
known header is required. The full semantic-decoding objective remains incomplete.

Update 2026-09-28: the user requires public online sources only. The historical
reference request and blocker audits below are superseded as a work dependency:
a known header would help validation but is not a prerequisite for further work.
A public APK teardown reports embedded dish firmware bundles, providing a new
static-analysis lead. See [firmware source review](../../docs/research/starlink-literature/firmware-leads.md).
Acquisition, binary contents, and relevance to the radio header remain unverified.

The objective remains to decode and understand the additional header and short
tail regions. It is not complete. This checkpoint follows the 21-test analysis
suite and the expanded 20-frame full-band sample (seven raw-IQ-derived frames
and thirteen published hard-symbol frames).

Validated evidence includes the 60-state tail alphabet, pilot-referenced header
signs, matching sampled published decisions, and the observable low-phase LFSR.
The exact high-plane template representation does not uniquely identify the
transmitter descrambler. Counter, copy, and short-parity models have not provided
verified fields or an error-corrected header. Strong receiver agreement alone
also admits short-window discrepancies.

The current bottleneck is a discriminating header reference: a known transmitted
header paired with its symbols, a concrete encoder/interleaver definition, or
an implementation that supplies an independently checkable test vector. A user
question requesting an existing reference is pending. No new RF collection is
authorized or planned.

Blocker audit 2: rechecked the checkpoint, latest result files and literature
notes on the next goal continuation. No new labelled header, encoder/interleaver
definition or decoder reference is available, and no analysis process remains
pending. The reference question has not been answered. This turn supplies no
new decoding evidence; the same semantic-validation bottleneck remains. Keep
the goal active for now; neither completion nor the three-turn blocked threshold
has been established.

Blocker audit 3: the next continuation revalidated the checkpoint and unchanged
result files. No reference response or new discriminating evidence is available.
The same missing semantic-validation reference has persisted for three consecutive
audits. Mark the goal blocked, not complete. Resume when a known header test
vector, concrete coding/layout definition, or independently checkable decoder
becomes available. The published report and local datasets preserve the work.

Do not count another parameter sweep on the same inspected frames as independent
confirmation. To resume with a new hypothesis, state what evidence distinguishes
it from the existing alternatives, fit on discovery material only, and verify
an actual field or coding constraint on unused observations. More unlabelled
frames can improve statistics but do not by themselves resolve an arbitrary
fixed-mask/unknown-data ambiguity.

# Additional embedded radio-side firmware in the existing package

The AArch64 ELF executable atlas does not exhaust the package. A fresh read of
the original Catson runtime archive finds six XP70 S-record images. The
[`embedded_radio_images.py`](embedded_radio_images.py) probe verifies the
compressed archive against its recorded hash, reads tar members without
extracting/executing them, validates every S-record checksum and length, rejects
overlapping data records, and records contiguous address spans and entry points.

| Image | Decoded data bytes | Declared entry address |
|---|---:|---|
| xp70_bamboo.srec | 69,340 | 0x4000e0 |
| xp70_gopher.srec | 79,941 | 0x4004b2 |
| xp70_panda.srec | 66,315 | 0x4000ea |
| xp70_peanut.srec | 37,068 | 0x4000d8 |
| xp70_pez.srec | 86,516 | 0x4004b2 |
| xp70_pulsar.srec | 41,614 | 0x4000d8 |

The runtime's `setup_ut.sh` calls peanut/pulsar "Shiraz 1 DBF images" and the
other four "Shiraz 2 DBF images" in its pruning functions (lines 295–313).
Decoded diagnostics independently reference `phased-array/xp70/shiraz`,
`Shiraz2Main.cc`, `driver/util/beamformer`, front-end module register writes,
RX/TX phase settings and beam bounds. These support an array/front-end control
role. They do not prove that these images demap symbols, perform FEC or decode
SYSINFO. The declared entry addresses alone do not establish an instruction set
or justify decoding these bytes as AArch64.

This materially refines the binary inventory: besides `phyfw`, RX/TX LMAC and
UMAC, there is firmware for an embedded radio-side processor. Next useful work
is locating its loader and host command interface in the existing executables,
then checking whether any command exposes sample-stream or demodulator behavior.
No new RF scan is justified by the S-record contents alone.

The startup script also chooses MAC/PHY executable variants using
`/device-tree/chosen/modem_type` and `catson_cut`, with `_v4` and `_catapult`
symlink helpers. This selection must be respected when comparing register maps.
The script was read as archive data; none of its pruning commands were run.

The separate update archive contains six UTERM/TRANSCEIVER boot image variants.
A bounded string inspection found trusted-boot and memory-initialization
diagnostics; their filenames are not evidence of a modem payload decoder.
No claim of absence of modem microcode follows from a filename/string search.

## Host loader follow-up

The Catson `uterm_binbox_user_terminal` executable contains the host-side
loader at `0x4920d0`. Its error path references the source filename
`external/rocket~/src/flight/sat/all/phased-array/BeamformerXp70.cc`
(`0x11303b8`). This is a code-linked diagnostic, stronger evidence of the
subsystem than a filename search alone. The debug reload path constructs
`/tmp/xp70_debug.srec`, calls this loader at `0x49273c`, and, after successful
return, invokes a virtual method through `object+8`, vtable offset `0x40`
(`0x492764–0x492770`). The concrete virtual target remains unresolved; do not
label that call a verified hardware upload yet.

The loader first calls `0xedf6d0`, passing its filename argument and
`object+0x88`. Inspection of that callee shows an ASCII `S` check at
`0xedf784` and line-length checks. The complete S-record parser was not
executed in this follow-up. The loader then routes record bytes into three
host buffers. Its own usage diagnostics name the regions:

| S-record address | Host destination | Diagnostic label | Bound |
|---|---|---|---|
| below `0x200000` | buffer pointer at object `+0xd0`, indexed by address | data | configured buffer byte length |
| `0x200000` through `0x3fffff` | inline object `+0xe8`, indexed by address minus `0x200000` | strs | offset at most `0xdfff` |
| at least `0x400000` | buffer pointer at object `+0xb8`, indexed by address minus `0x400000` | text | configured buffer byte length |

The middle address range is a dispatch range, not a promise that its entire
extent is valid: offsets above `0xdfff` reach an error branch. The loader zeroes
the middle buffer with size `0xe000`. Its text/data vectors are resized from
configured word counts before being treated as byte buffers. These are image
memory coordinates, **not RF carrier indices or control-message offsets**.

[`xp70_host_loader.py`](xp70_host_loader.py) pins the host binary to the atlas
hash and records ELF-mapped strings and instruction windows. It executes the
actual routing instructions with synthetic records: **33 cases**, covering
three byte values, each region, valid endpoints and rejected boundaries.
All destination bytes are checked, including untouched regions. The test does
not execute the file parser, allocation, full loader, virtual method or XP70
image. Receipt: ignored `local/xp70-host-loader.json`.

This supports a beamformer firmware interpretation independently of the
embedded images' own diagnostics. It supplies no new mapping from a satellite
identity field to RF symbols. Follow the concrete virtual target and host
command interface if continuing this branch; do not treat successful host
image parsing as evidence of a payload decoder.

### Refinement: the post-load virtual call is not a proved upload

Following object construction supplies a useful negative constraint. Constructor
`0x4913b0` stores its second argument at beamformer object `+8`. It is called
by `0x50b800`, reached from allocation/factory code `0x50c800`, which receives
that object as its third argument. At `0x489128–0x489134`, the caller passes
its own `x19` context as that argument; the enclosing function preserves its
incoming `x0` in `x19` at `0x488574`. Its diagnostics identify
`BeamformerMeshShiraz.cc`. Thus the post-load call goes back through the owning
mesh object's interface; it is not a direct call into the embedded image.

ELF relocations and RTTI identify the primary `BeamformerMeshShiraz` vtable at
`0x153b608`: typeinfo `0x153b548`, name `0x112fef8`. Its slot `+0x40` resolves
to `0x4784b0`, exactly `mov w0, #0; ret`. The probe now verifies that relocation
chain and executes this complete two-instruction method: it returns zero
without accessing the object. **For this vtable, the method cannot upload
firmware or decode samples.** A derived object's override remains possible;
the runtime dynamic type at the reload call has not been proved. No broader
claim that every variant uses this no-op is justified.

This weakens the prior suggestion that the immediate call after loading might
be the upload operation. A next investigation should follow code that consumes
the populated image buffers, or establish a concrete derived override, rather
than infer upload from call ordering. This adds no RF identity mapping.

### Image-buffer consumer found

The routine around `0x50b200` consumes the same `+0xb8` text and `+0xd0`
data vectors populated by the loader. The text loop at `0x50b290` and data
loop at `0x50b318` load 32-bit words, increment the index, and compare it with
the vector byte length divided by four. Error paths name `ShirazXp70.cc`.

| Image region | Address supplied to write interface for word i |
|---|---|
| text | `0x50000 + 4*i` when local variant flag is nonzero; otherwise `0x48000 + 4*i` |
| data | `0x40000 + 4*i` in both flag branches |

These interface addresses differ from the S-record memory addresses. The
variant flag is derived from owner field `+0xa9c`; no hardware-model names
are assigned to its numeric values here. When the beamformer write method
matches the default implementation pointer, the loop delegates to its owner
(`beamformer+8`), vtable slot `+0x20`, with address in `w1` and word in `w2`.
Nondefault methods take separate branches, not tested here. The owner's actual
write operation and surrounding begin/end calls remain unresolved.

[`xp70_image_transfer.py`](xp70_image_transfer.py) executes argument construction
for **36 cases**: both regions, both flags, indices 0/1/127 and words
0/0x12345678/0xffffffff. It verifies receiver, address, data and target, stopping
**before** all four relevant virtual calls. This tests host little-endian word
loads and address arithmetic, not physical bus byte order, a successful upload,
or RF decoding. Receipt: ignored `local/xp70-image-transfer.json`.

### The owner write path constructs an SCP register message

For the RTTI-identified primary `BeamformerMeshShiraz` vtable, slot `+0x20`
is `0x47e210`. It preserves the supplied address and word, then chooses between
`0x599a50` and `0x599cb0` using object state. The latter has a mode-0 branch
at `0x599d28` that calls owner slot `+0x18`, passing the address in `w2` and
word in `w3`. That slot resolves to `0x594a40` for this vtable.

At `0x594a40`, the word is saved at stack `+0x8c`. The routine constructs a
message at stack `+0xd0`. ELF relocations resolve its vtable to `0x153c390`,
typeinfo to `0x153c350`, and RTTI name to `0x1132970`:
`N6SpaceX3Scp19AppRegistersMessageILNS0_10AppMessage4TypeE1EEE`.
This identifies `SpaceX::Scp::AppRegistersMessage` with template message type 1.
The code stores a 16-bit destination argument at message `+0x18`, the supplied
32-bit address at `+0x1c`, and passes message `+0x21`, the saved word's address
and length 4 to helper `0xfe2c90` (a tail branch to PLT `0x1514e0`). That call
has the shape of a four-byte copy; its import is not resolved by this probe.
These are **in-memory object offsets**,
not serialized or RF offsets. The later call to `0x602b30` is a serialization
candidate; its complete behavior has not been audited here.

The probe now verifies both owner vtable entries and the SCP message RTTI
chain, and records all intervening instruction windows. This extension is
static evidence; the 36 execution cases still end before device writes.
Dynamic owner type, mode-1 routing, the alternative `0x599a50` path and actual
transport remain unproved. No device access was performed.

**Consequence for the identity investigation:** this branch leads from a
firmware image to an outgoing register-control message. It provides no
received SYSINFO field or symbol-to-packet decoder. Deprioritize deeper XP70
loader work unless an independent modem link appears; return to the hardware
packet producer / RX MAC boundary for tracing received satellite identity.

Reproduce: `python3 embedded_radio_images.py` from this directory (system
`zstd` required). Ignored receipt `local/embedded-radio-images.json` records
all six hashes, address spans, entry points, text-hint addresses and startup
line references. Component tests exercise valid S-record decoding and corrupted
checksum rejection. This is a packaging/content audit, not disassembly or
end-to-end RF decoding.

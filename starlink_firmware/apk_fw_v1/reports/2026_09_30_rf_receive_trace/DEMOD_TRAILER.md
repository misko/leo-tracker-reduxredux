# Demodulator metadata adjacent to received packets

This audit asks whether the packet delivery boundary contains a reference that
could connect a software identity message to RF framing. It establishes a
specific metadata container. The follow-up below identifies two measurement
fields; the remaining fields are unresolved. The earlier
audit identified PHYInfo diagnostics; the new experiment executes their entry
selection and byte transfer, including negative inputs.

Binary: canonical `catson-bin--rx_lmac`, SHA-256
`9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe`.
All addresses are ELF virtual addresses for this binary.

## Location and layout

The receive routine calls `26a00` at `272f8`, passing the receive context,
descriptor, and copied descriptor metadata. The parser uses descriptor `+0x10`
as the packet-buffer pointer and the first metadata word as total buffer length.
Metadata byte 7 gates trailer inspection. These are CPU-memory offsets, not
over-the-air bit positions.

```text
packet buffer
  [preceding bytes][PHYInfo entries][8-byte trailer footer]
                                   footer +4: uint16 LE trailer size
  entries begin at buffer + total length - trailer size

demod entry (16 bytes)
  +0: tag 01 or 81
  +1: length 10 hex
  +2..+15: 14 uninterpreted body bytes
       → receive context +1b..+28, unchanged
       → receive context +19 gets canonical marker 01
```

The footer length includes entries plus the eight footer bytes. Other footer
bytes are not interpreted by this audited routine. Total buffer length and
trailer length must be multiples of four; trailer length must be at least eight
and no greater than total length. Each entry length must be a positive multiple
of four within the remaining entry region. For tags whose low seven bits equal
one, this routine additionally requires length 16. The separate type-2 EVM
branch is outside this experiment.

## Executed evidence

[demod_trailer.py](demod_trailer.py) runs `26a00` through return using synthetic
buffers. Parent configuration byte `+1c=0` selects the actual byte-copy routine
`fe9a0`; only the diagnostic logging query is stubbed. No mapping, hardware, RF
capture or external service is used.

| Test | Result |
|---|---|
| Every one of 112 body bits, independently, with each of tags 01/81 | All 224 cases copied exactly; marker becomes 01 |
| Unknown entry preceding/following a valid entry | Valid entry recovered in both orders |
| Disabled metadata flag | No receive-state change |
| Demod entry length 12 instead of 16 | No receive-state change |
| Trailer length 7 | No receive-state change |
| Unknown tags 03/83 | No receive-state change |
| Two distinct valid demod entries | Last entry overwrites the first |

All 232 cases return normally, preserve the input packet, and change only the
expected context bytes. An ignored receipt with instruction evidence and source
hash is at `local/demod-trailer.json`. Component-owned regression test:
[test_demod_trailer.py](test_demod_trailer.py). Alternate libc-copy configuration,
EVM handling, terminal faults and exhaustive malformed-input behavior are not
covered.

## Consequences for the identity investigation

This container gives us a bounded next target: trace consumers of exactly the
14 copied bytes and the canonical marker. It does not justify searching our RF
recordings for a 112-bit word. Trailer location in a received buffer does not
prove transmission on air; the metadata may be attached by the modem.

The tag's high bit is discarded by this selection path. It therefore cannot be
recovered from the stored marker, even if hardware assigns it a meaning.
Copying preserves byte order; no descrambling, endian swap, or field decoding
occurs on this tested path.

Missing/invalid entries do not clear the old context within this routine. The
follow-up below establishes a caller reset and consumer validity gate on the
audited receive-loop path. Arbitrary context snapshots still cannot be associated
with the latest SYSINFO identity without their validity and execution context.

No satellite identity, frame number, timestamp or channel number has yet been
identified in this body. The SYSINFO address decoder remains separately
supported; an RF-to-SYSINFO mapping is still unproved.

## Consumer audit: two measurement fields identified

The consumer `58ca0` follows `root+53378` to the containing object. Its receive
context begins at `+280`: the prior marker/body offsets `+19/+1b` are consequently
`+299/+29b` in this object. At `58d14–58d18` a nonzero marker selects `590ac`.
This resolves an important pointer-base ambiguity when searching for consumers.

Define `b` as the 14-byte body, with all integer loads little-endian:

| Body bits | Firmware calculation | Supported interpretation |
|---|---|---|
| Bytes 0–1, unsigned 16-bit `A` | For nonzero A: `20*log10(A/2048) + 1.05 - 18` | Diagnostic calls this **CE RSSI**; physical reference/units beyond the logarithmic scale unverified |
| Bits 4–14 of the 16-bit word at bytes 8–9, unsigned 11-bit `Q` | `Q/32 - 36.12 - 18.06` | Diagnostic calls this **SNR** |

The constants are stored doubles at `111f28`, `111f30`, `111f38`; the call at
`59290` resolves through ELF PLT relocations to imported `log10`. The zero-A
branch bypasses the logarithm. The subsequent branch assigns zero to the RSSI
working register; that path is not a measurement of negative infinity.

The SNR code spans approximately −54.18 to +9.78875 in steps of 1/32. This is
the software conversion range, not proof of a calibrated receiver range.
For A=2048 the CE RSSI formula gives −16.95; do not label it dBm without a
verified calibration reference.

At `5957c–595b4`, the diagnostic names the converted RSSI, while its Beam value
comes from the containing object's byte zero and its SID from a separate
object's `+12` halfword. They are **not extracted from these trailer fields**.
The SNR diagnostic at `594e0–59518` uses the same separate labels. SID here must
not be substituted for satellite identity or NORAD catalog number.

[demod_metrics.py](demod_metrics.py) executes the conversion windows with only
the resolved `log10` import supplied by Python. **2,181 cases pass**: all 2,048
SNR codes, amplitude boundaries and single-bit values, and all 112 body basis
bits. The bit-basis check confirms these two calculations use 27 body bits;
it does not prove the other 85 bits are unused elsewhere. These tests are
deterministic firmware arithmetic checks, not correlations with RF data.
Receipt: `local/demod-metrics.json`; regression test:
[test_demod_metrics.py](test_demod_metrics.py).

This weakens interpreting the whole trailer as an identity or timing header.
It strengthens its role as receiver-quality metadata. The remaining body bytes
and producer are still worth tracing; the RF symbol-to-message bridge remains
unresolved.

## Lifetime audit: consume, invalidate, then clean up

The two inspected receive loops call packet ingestion `27100`, parse with
`312b0`, and then call `3c550` (sites `28c28` and `28e48`). In `3c550`:

1. `3c574` calls the metric consumer `58ca0`, with the selected object pointer
   from containing-object `+300`, a root-derived pointer `root+e5a0`, and a
   halfword from containing-object `+308`.
2. `3c58c` clears **both** marker bytes at containing-object `+299/+29a` using
   an unaligned halfword store through a base adjusted by `+200`. This explains
   why searching only for byte stores at `+299` missed the reset.
3. It resets nearby packet state and calls buffer cleanup `310d0` at `3c598`.

The metric consumer itself follows `root+53378`, checks the demod marker at
containing-object `+299`, and enters the conversion branch only when nonzero
(`58d08–58d18`). The body remains in memory after invalidation, but that gate
prevents this consumer from using it on the next call unless a marker is set
again. This revises the earlier open question: retention by the trailer parser
does **not** imply that this normal cleanup path reuses stale measurements.

[metadata_lifetime.py](metadata_lifetime.py) executes `3c550` through return,
instrumenting its two callees to observe order and arguments. It separately
executes the real consumer marker gate before and after cleanup. All 256 demod
marker values crossed with EVM markers 0/1/255 pass: **768 cases**. The measurement
call sees the original markers; the cleanup call sees zeros; the old body is
preserved; the subsequent demod gate is closed. Only the documented state-reset
bytes change. Receipt: `local/metadata-lifetime.json`.

This proves the bounded reset/gating behavior, not an end-to-end received
SYSINFO transaction. The full metric consumer and buffer cleanup are stubs in
the reset test; complete-loop scheduling, all exceptional paths, and which
selected object a specific identity message supplies remain unverified. No
satellite address is decoded from this metadata. The scientific conclusion is
that these measurements have a software-managed validity interval associated
with packet processing, rather than being a persistent identity word.

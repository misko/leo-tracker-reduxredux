# Recorded DS9 bundle reader v1

This component reads the native TSV authority for a saved DS9 scanner plan. It
requires an externally supplied SHA-256 for `native.tsv` and verifies that hash
before parsing the `FORMAT` row or any authority value. The expected digest is
exactly 64 lowercase hexadecimal characters; the separately supplied Analysis
identity is a nonzero `sha256:<64 lowercase hex>` value.

The reader accepts only `leo-recorded-ds9/v1`: 7.5 MS/s, coherent dual RX,
7.5 MHz analog bandwidth, historical zero profile CRC, transition flags 11,
and 120 ms visits. It bounds the file at 16 MiB, targets at 8, visits at
16,384, and lines at 2,048 bytes. It requires canonical integer spellings,
bounded decimal syntax with complete finite C-locale conversion, exact field
counts, one qualified saved timing bracket, contiguous target indexes, causal
and nonoverlapping original counters, target/frequency agreement, and exact
raw-byte arithmetic.

Every relative raw path is lexically normalized, resolved with `realpath`,
checked to remain under the canonical bundle root, required to name a regular
file, and size-checked. The reader does not hash raw IQ; the recorded provider
does that at selection before exposing any block. This split validates every
row and path before source construction while retaining the provider's
read-before-use raw digest check.

On success `RecordedBundle` owns:

- session, recording, calibration, plan, and native TSV authority;
- the saved exact-counter `timing::Bracket` and declared UTC bracket width;
- original target rows, `leo_scanner_recorded_visit` rows, and aligned event/raw
  digest records with canonical paths;
- `CorrectedGeometryProfile`; and
- historical `ingest::Authority` derived from the same target rows.

A scanner plan may borrow `plan_rows.data()` only while the bundle remains
alive and unchanged. No candidates, supports, tracks, or location answers are
reader inputs.

## Qualification

The host and ASAN/UBSAN suites pass their synthetic adversarial cases and the
actual exported one-visit and 32-visit metadata. The ARM build passes the
component suite under QEMU and on the physical CPU. The accepted physical v4
run took 0.023866836 seconds wall, 0.023568 seconds CPU, 1,640 KiB maximum RSS,
and exited zero. No RF or device source was opened.

A second physical run parsed the staged visit-301 `native.tsv` using its
external `963b4930...` digest and resolved the staged 7,200,000-byte raw file
whose declared digest is `3530f06a...`. It passed in 0.024142849 seconds wall,
0.023856 seconds CPU, and 1,644 KiB maximum RSS. The test interface accepts two
external bundles, so this run supplied the same one-visit bundle in both slots;
it is a physical visit-301 parser check and does not claim a physical 32-visit
parse.

The earlier `physical.log`/`physical.time.json` are intentionally retained as a
rejected test artifact. The v3 test compared the parser's correct canonical
path with the lexical `/var/tmp` path; on the target `/var/tmp` is a symlink to
`/tmp`. The production parser was unchanged. The v4 test compares against
`realpath` and is the accepted physical result in `physical-v4.*`.

This component does not run the scanner, create the recorded provider, or
claim end-to-end recorded Analysis results. Those compositions consume this
validated value-owned bundle separately.

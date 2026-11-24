# Detached visit attestation for preserved original compressed prefixes

Use only the existing DS30-0163 and DS30-0419 local tmpfs chunks that
stopped at the idle deadline. For each, verify the measured stage
receipt, checkpoint, original manifest and signed index before
decoding. Open no RAID source, no later member, and no receiver or
solver. The earlier full-member admission outcomes remain unchanged.
[DS30-0163 partial](first-member-0163-idle.md) ·
[DS30-0419 partial](first-member-0419-idle.md)

In original index order, take the maximal contiguous prefix of visit
rows whose indicated decoded bytes are fully emitted and whose SHA-256
matches the signed row. Preserve all issued rows in that prefix,
including empty or excluded visits. Stop before the first short,
missing, or bad-hash row. The original signed manifest and index must
be valid in their entirety. Cross-check the output bytes and the
partially emitted trailing data with a second streaming decoder.
Publish only a detached local byte extent and ordered visit witness,
with original timing, target and receiver metadata. Preserve the
unattested trailing-byte count separately in the receipt.

A truncated frame cannot enter normal acquisition. The resulting
evidence covers the explicitly listed visits. Full compressed digest,
frame checksum, full-member completion and recording acceptance are
outside this test. No detector outputs can inform the visit boundary.

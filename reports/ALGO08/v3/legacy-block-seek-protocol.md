# Selective decoding of unmodified legacy Zstandard IQ

Freeze before timing. Use only the existing resident DS30-0016 member 0. Its
released manifest, index, compressed file, identities and all bytes stay in
place. The released reader first verifies the full decoded member, checksum and
every window. Build a detached table of compressed/decoded block extents and
the Huffman origin for each literal block. Supply an independent table pin and
bind the exact original manifest/member/index digests and original 8 ms decoded
prefix commitments. No new RF, archive reads or waveform file writes.

Only one standard checksum-enabled frame, no dictionary, and entirely
zero-sequence compressed Huffman blocks qualify. Native libzstd block decoding
may consume an intersecting block and at most its last new-table predecessor.
Bind the original entire compressed object and ordinary index before processing;
validate full SHA for full visits and prefix SHA for short visits. Unsupported
layouts or missing maps take ordinary decode. An explicitly corrupt map must
refuse strict reads, and malformed original content must fail through either
route. Test a changed sidecar and one bit in an original encoded block that the
strict schedule never sends to the decoder, on a private in-memory duplicate.

Use identical frozen signed 20/8 ms DSP with both antennas and full two-scan
anchors. Require exact requested CI16 and every ordered emitted native lane
including empty and residual output. Compare stock full reads with the selective
reader in both orders on CPU 2 at nice 15 and I/O priority 7 under the shared
lock. Charge complete authenticated input, parsing, decoded digest checks, DSP
and evidence checks. Separately report stock authority generation and one-time
map cost, required bytes and table origin work, scratch and encoded bytes never
skipped at the auth boundary. No solver, full recording claim or release change.

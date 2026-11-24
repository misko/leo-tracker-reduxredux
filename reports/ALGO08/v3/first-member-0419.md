# DS30-0419 first payload deferred at original-source admission

The first signed original payload had **0 of 19,328 pages resident**.
The exact-segment tmpfs search returned no candidate. The recording's
nominal NVMe spool path resolves through a symlink to the original
XFS RAID volume. The raw prefix trial was deferred without reading
or staging any waveform bytes. [Frozen scope](first-member-0419-protocol.md) · [Metadata receipt](measurements/first-member-0419.json)

The prior authenticated inventory names 14 original segments. The
probe used only `segment-00000000` and member index 0, named
`iq-000000.ci16.zst`. Its signed extent is **79,163,761 compressed
bytes** covering **64 chronological visits** and **102,400,000 decoded
bytes**. The selected original segment manifest matched its signed
inventory digest. Its first **173,738-byte** index matched the
declared SHA-256, contiguous visit order and exact decoded extent.
The receipt records the original compressed and decoded digests
as manifest commitments. Observing residency required only the
regular payload descriptor, its metadata and the pinned Linux
`cachestat` helper. The mount is `/dev/mapper/vg_bulk-bulk`,
major/minor **252:5**, at `/srv/bulk`.

The privileged same-device tmpfs directory census used the exact
signed segment basename and returned no errors. No alternate
segment, payload or recording was probed. The zero-page result
ended admission before any `RWF_NOWAIT` call, mapping, read-ahead
advice or waveform copy. An unsupported or racing cache-only copy
would require separate evidence of zero backing I/O even if the
entire extent were observed resident.

This is a source-availability result with zero receiver benchmark
children, solver children or new RF. The saved solver was measured
separately on the original signed detector packet. Two component
tests passed.
[Saved solver timing](nomination-handoff-0419-local.md)

# First-use map authority without prepared maps

The research first-use entry can now produce replay custody from an
original capture that has no prepared maps. It uses the ordinary signed
recording input and the same verified history and replay libraries. The
original DS30-0016 result used a previously prepared plan to compare every
produced map byte for byte. That comparison remains available as an
optional qualification mode. Its recorded clocks belong to that earlier
mode. [Earlier complete qualification](legacy-first-use-0016.md)

Pass the ordinary history-risk arguments with
`--legacy-first-map-history`, `--legacy-first-map-replay` and each
library's `-sha256` argument. Leave the two optional plan arguments unset
for fresh production. Supplying both `--legacy-first-map-plan` and
`--legacy-first-map-plan-sha256` additionally requires exact parity with
that independent plan.

Each member starts from its original manifest, signed chronological index
and complete encoded digest. A supported member finishes its original
frame checksum, all per-window digests and complete decoded digest before
the producer determines the emitted map kind and pin. The existing
independent reader then opens the derived literal or exception map and
verifies a prefix against its original digest. Reopening borrows the
same authenticated immutable snapshot. An authentic but unsupported
compression layout drains the released ordinary verifier on the same
snapshot when available. Its custody row declares `ordinary` with no
detached map path or digest. Routine replay reads that member through
the ordinary verified path.

The producer derives its complete custody only after the normal receiver's
signed raw authority agrees with the original ordered per-window digests and
every enrolled member has been consumed. Failure before that boundary clears
provisional map state. After scientific publication succeeds, a private
directory accumulates all verified maps and the complete custody document,
then moves into place atomically. The acquisition receipt pins the new
custody digest for replay. The original input and existing replay format
remain intact.

Eighteen component and adjacent tests passed. A fresh synthetic recording
with literal, unsupported and exceptional members produced two maps and one
ordinary custody row on exactly one encoded descriptor read per member.
Independent consumers checked every emitted prefix and the fallback's zero
and truncated visits. The same custody passed optional parity mode. A later
committed compressed-byte mismatch and a repinned unsupported frame with a
bad original checksum both cleared the earlier provisional map without a
partial bundle. A waveform-blocked installed startup probe reached the
actual scanner with no plan or original IQ opens. No full original recording
was rerun.

- [Installed no-plan startup](measurements/legacy-first-use-authority-setup.json)

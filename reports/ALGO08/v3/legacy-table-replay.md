# Huffman table replay across an original matched block

The final DS30-0016 legacy member contains a seven-byte match in the same
block that defines the Huffman table for the next block. The prototype
restored the table from the unchanged original compressed bytes and decoded
the dependent block byte for byte. It also reproduced all 40 complete
stock-authenticated visits and every requested sample in the unchanged 20/8 ms
recipe on this isolated member.

In a fresh native context, the original block 232 supplied its authentic
97,627-byte literal section. Appending a zero sequence count let libzstd
regenerate 131,065 literal bytes in scratch and retain the table. Direct
native output requests for block 232 were refused. The fresh context then
decoded all 131,072 bytes of block 233 without requesting block 232's output.
Where the schedule requested samples within block 232, the reader used the
131,072 certified exact decoded bytes from the detached sidecar and verified
the resulting full window or prefix SHA-256. The synthetic scratch output
never enters a sample span.

The released reader authenticated the exact 49,036,352 encoded bytes, frame
checksum, original manifest and index, all 40 decoded window SHA-256 values,
and all 64,000,000 decoded bytes before sealing the sidecar. The single mixed
block's decoded length follows from the authenticated total decoded extent
minus the exhaustive literal census. This certification refuses multiple
mixed blocks without independent per-block lengths. It does not infer lengths
from the maximum block size. A synthetic unit case exercises a valid nonfinal
mixed block of 125,056 decoded bytes.

| Boundary | Stock wall / CPU, ms | Selective wall / CPU, ms |
| --- | ---: | ---: |
| Ready 20/8 ms, stock first | 179.420 / 179.417 | 147.513 / 147.511 |
| Ready 20/8 ms, selective first | 185.154 / 185.150 | 141.872 / 141.869 |
| Independent stock authority | 107.962 / 107.952 | |
| Additional sidecar certification and sync | | 31.924 / 31.924 |
| Contiguous full verification through sidecar | | 139.917 / 139.904 |

Ready wall improved **17.8% and 23.4%**. Both ready arms authenticated every
encoded byte. The selective arm decoded 261 requested blocks and eight table
dependencies, one of them the scratch replay. It admitted 30.72 MB of exact
decoded samples. That path observed eight full anchors, 28 short visits and
four original exclusions. Its 72 ordered signed lane outputs include 28
positive lanes and five residual candidates. They match stock. This is the
original schedule rule initialized on this one member. It does not replay
the prior recording's counters. The one-time certification cost includes
rechecking original encoded and per-window digests when creating the sidecar.
The ready measurement assumes a prebuilt sidecar.

The detached file is 152,689 bytes including 131,072 exact exception bytes.
The native decoder plus scratch capacity is 324,732 bytes. Both stock and
strict refused a flipped byte at encoded offset 10,492,784 in an unused suffix
of scheduled short visit 264 before issuing any visit. Changed detached bytes
also failed their independent pin. The original source was untouched. No
prior waveform member, backing archive or RF input was read.

The reusable C integration calls
`legacy_configure_origin(context, ordinal, literal_section_bytes, decoded_literals)`
once after `legacy_open`. The decoder automatically reestablishes that
table when its current table differs. `legacy_origin_replays(context)`
counts seed restorations. Clients continue splitting output spans at
exceptions and must independently certify all detached output bytes and
per-block extents. The module's `SelectiveException(..., replay_table=True)`
covers the exact single mixed block proven here. Multiple exceptional output
blocks with independent length authorities can use the same native table
configuration when at most one is a reused table owner.

Six component tests passed. Use the installed release interpreter and
`python -Bm reports.ALGO08.v3.legacy_table_replay_trial NEW_TMPFS_ROOT`
under the shared Gauss lock on CPU 2 at nice 15 and ionice 7. The trial
requires the installed storage module and checks the frozen release receiver
and native 8 ms binary. This experiment covers one original member and does
not establish first-use or complete recording speed.

- [Protocol](legacy-table-replay-protocol.md)
- [Physical receipt](measurements/legacy-table-replay-0016.json), SHA-256
  `8ce228b3e2a96840442daa1ec2557633f65ad0f05e31996906590106444ed2e8`

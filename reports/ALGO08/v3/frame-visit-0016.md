# Single-file Zstandard visit frames on physical DS30-0016

On one resident 64-visit member, a checksummed Zstandard frame per visit with
a block flush at 8 ms preserved every sample word and index row in the
unmodified installed reader. With a separately pinned seek table and a
previously verified capture, the selective 20/8 ms reader reduced wall time by
23.6% and 24.4% in opposite orders while authenticating the complete encoded
file. Capture through independent first full readback and 20/8 ms detection
took 521.108 ms for ordinary capture and 508.756 ms for visit frames. The
writer alone was 6.540 ms slower with visit frames. The single-order first-use
comparison does not establish a material first-use gain.

| Measured boundary | Ordinary wall / CPU, ms | Visit frames wall / CPU, ms |
| --- | ---: | ---: |
| Level-1 writer through seal | 155.632 / 155.629 | 162.172 / 162.153 |
| Independent installed full readback plus mixed detection | 364.998 / 364.981 | 346.128 / 346.093 |
| Capture through first complete mixed detection | 521.108 / 521.085 | 508.756 / 508.699 |
| Ready mixed detection, ordinary first | 260.995 / 260.979 | 199.405 / 199.401 |
| Ready mixed detection, frames first | 262.159 / 262.148 | 198.325 / 198.304 |
| Complete all-20 ms detector check | 505.293 / 505.273 | 513.244 / 502.130 |

Source hydration and authentication precede both writers and use the same
owned immutable CI16. Ready comparisons use the same frozen compressed ingress
for each arm and the released paired decoded hash implementation where the
ordinary iterator hashes the full decoded member. No exact in-memory sample
comparison is timed in either ready arm. Native 20/8 ms DSP cost was
122–124 ms in both arms. The ready candidate authenticated 78,553,091 encoded
bytes, fed 34,251,464 bytes to Zstandard, and decoded 44.8 MB versus the
ordinary 102.4 MB. Its complete encoded read and hash took 31.0–31.5 ms CPU.
Selective decoding and decoded span authentication took 41.0–41.7 ms CPU.
Eight full anchors checked full window bytes and the Zstandard frame checksum.
Fifty short visits checked decoded prefix SHA-256 against the frozen table.
The ready reader hashes the unused encoded suffixes as part of the full-file
commitment. Independent first readback validates the decoded contents and
checksums of every frame.

The ordinary and framed IQ files occupy 78,554,951 and 78,553,091 bytes.
Including index, manifest and the 12,458-byte seek table, the complete
footprints are 78,731,260 and 78,741,856 bytes. Both captures together used
157,473,116 bytes of tmpfs scratch. The optional table binds the exact fresh
manifest, original index and complete encoded member. It records consecutive
frame offsets, prefix ends and decoded prefix digests. The prototype takes a
trusted external SHA-256 pin for the table and leaves released manifest and
index schemas intact. It does not install a new custody or production format.

Both archives retained all 64 ordered rows and 102.4 MB of exact sample words.
The mixed receiver issued 116 signed lane calls after six original visit
exclusions, with 43 positive lanes and four residual candidates. The full
20 ms receiver issued the same 116 lanes with 61 positive lanes and 24
residual candidates. Within each detector, the ordered native tuples and
selected probe digests match across storage formats, including empty lanes.
The strict reader rejected a byte change in the seek table. Both readers
rejected a byte change at offset 10,757,653 inside the unused suffix of
scheduled short visit 8 before issuing a visit.

The run used only DS30-0016 member 0 from the authenticated resident tmpfs
stage, CPU 2, nice 15, I/O best-effort priority 7 and the shared Gauss lock.
The installed reader and both native receiver binaries are pinned in the
receipt. All nine component tests passed. An initial same-member run used a
full-anchor suffix for the corruption witness and included ordinary-only
owned-word comparison in ready timing. The final run selects the corruption
site from the actual short schedule and removes word comparison symmetrically
from ready timing. Initial and corrected receipts are retained.

- [Protocol](frame-visit-0016-protocol.md)
- [Corrected receipt](measurements/frame-visit-0016.json), SHA-256
  `0f20009514737da994f1f819bb54080dd38a360233259e0cddacf7edf97c382c`
- [Initial receipt](measurements/frame-visit-0016-initial.json), SHA-256
  `48ee39e5cd2722ae5e2a3468bbef4dc5e46f0650b9308ff8fd678f258f520450`

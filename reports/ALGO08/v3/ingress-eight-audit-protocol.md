# Verified 20/8 ms acquisition attribution on one physical member

Freeze the exact existing DS30-0169 member-zero fixture under
`/dev/shm/leo-receiver-ceiling-0169-results01` and the genuine mixed
20/8 ms reference from `/dev/shm/leo-independent-8ms-0169-result02`.
The signed member has 64 issued visits, 51 admitted stereo visits,
16 full and 86 short antenna calls. Use the existing native objects,
complete acquisition path, aperture, original signed clocks and schedule.
No copy or waveform access outside this existing private tmpfs fixture.
Check full payload, index and manifest residency before and after.

Run one fresh profiled acquisition worker under the shared Gauss CPU2
lock, nice 15, I/O priority 7 and one numerical thread. Pay every
original compressed, decoded-window and decoded-member hash, framing
check, signed index and manifest. Preserve every native row, original
IQ digest, rank, score, epoch, CFO, candidate and clock. Require exact
reference equality before interpreting timings.

Use the earlier measured reader callbacks for compressed descriptor,
index authentication and decoding, Zstandard read/owned bytes, parallel
window and member SHA, retune parsing, support gate and authority seals.
Split manifest/source setup, each native aperture and the Python callback.
Inspect whether the released decoder's full-window bytes are copied to a
separate detector input or viewed in place. Count detector aperture bytes,
decoded whole-member bytes and unused sample-byte ranges separately.
Track which kernel outputs and checks require those bytes even when the
detector cannot read them.

Reconcile nonoverlapping inclusive and nested scopes to actual complete
acquisition. Keep process startup, profiling and final audit writes in a
separate clock. A new reader proposal earns a two-order matched test only
if it can plausibly remove at least 25 ms/member of measured resident CPU
without discarding original checks or duplicating previous negative
allocation, bounded ring, decoder or batch-index studies. A second
independent member is considered only after a positive matched result.
Full-recording figures are conditional costs, never a new raw comparison.

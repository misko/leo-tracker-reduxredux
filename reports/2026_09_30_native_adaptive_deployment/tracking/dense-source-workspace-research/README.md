# Dense source-group workspace research

This isolated research candidate removes the remaining per-hypothesis
allocations in tracking's `one_per_source` step. Production sources and public
contracts are unchanged. The baseline is the separately qualified
source-key-view implementation, not the earlier owning-string implementation.

## Measured need

A report-local global-allocation probe around `one_per_source` ran one complete
11,747-candidate DS9 reconstruction. All probed variants emitted the exact same
public output, SHA-256 `6819cb39151bb2cbe894e5d427244aa95d1eae73e17469e5033659d2b0a30084`.

| implementation | calls | input indexes | selected distinct keys | allocations | allocated bytes |
|---|---:|---:|---:|---:|---:|
| owning string control | 9,923 | 1,054,816 | 397,121 | 1,461,860 | 107,716,432 |
| borrowed source-key view | 9,923 | 1,054,816 | 397,121 | 407,044 | 25,415,744 |
| dense workspace | 9,923 | 1,054,816 | 397,121 | 0 | 0 |

The owning count is exactly one temporary key allocation per input, one map
node per distinct key, and one result-vector allocation per call. The key-view
count is exactly the latter two terms. Inputs average 106.30 points and 40.02
distinct keys per call; maxima are 383 and 157.

Dense binding runs once for each of eight lanes. It sees 3,563 unique source
groups and makes 3,579 allocations/481,456 bytes for its ordered map and two
vectors. The three lane workspaces add an estimated 24 allocations/85,512
payload bytes. Storing one dense ID per point adds 93,976 bytes on this input.
Thus the experiment replaces 407,044 repeated allocations and 25.4 MB of
allocator traffic with about 3,603 one-time allocations and 0.66 MB of
explicit payload. These byte counts exclude allocator metadata.

The first candidate stores the dense ID in both each `Point` and the binding
vector. On the tested 64-bit host and 32-bit ARM ABI this grows `Point` from 32
to 40 bytes because of alignment. The separately retained `sidecar.cpp`
variant moves the immutable point-to-group vector into `SourceWorkspace` and
keeps `Point` at 32 bytes; the qualified candidate and its artifacts remain
unchanged.

## Algorithm and lifetime

After the lane's existing candidate sort, `bind_source_groups` borrows every
explicit immutable source-group string. Empty IDs receive owned `time:<ns>`
keys. Fallback storage reserves before retaining its first view. One ordered
map merges equal keys, including a synthesized fallback that equals an
explicit `time:` key, then assigns dense IDs in the map's lexical order.

Each lane owns a `SourceWorkspace` containing a sentinel-filled best-index
array and reserved touched-group/result vectors. A selection scans indexes in
the original order and applies the unchanged weight, absolute residual and
candidate-ID rank tuple. It sorts touched dense IDs, which reproduces ordered
map enumeration, copies the selected indexes, resets only those touched slots,
and performs the unchanged final time/candidate sort. No floating-point
operation or ranking order changes.

`one_per_source` returns a reference to workspace result storage. Both callers
immediately pass it to `split_contiguous`, which materializes an owned
vector-of-vectors before any refined selection can reuse the workspace. The
focused test retains that owned result across another workspace call. The
workspace is local to `reconstruct_lane`; parallel lane callbacks never share
it.

## Qualification status

The focused host and ASAN/UBSAN tests pass 10,000 randomized cases in forward
and reverse order (20,000 comparisons), explicit/fallback collisions, embedded
NUL and long keys, identical rank ties, duplicate indexes, repeated
empty/subset/disjoint/full calls, owned split lifetime, and two concurrent
lane-local workspaces. A full sanitizer reconstruction is clean and exact.

All 60 causal five-second public CLI prefixes are byte-identical between the
source-view and dense candidates. The comparison completed in 25.79 seconds.
Three interleaved host tail-prefix measurements per implementation give mean
warm times of 0.36728 seconds for source-view and 0.32658 seconds for dense,
an 11.08% reduction. This shared-host result is a bounded diagnostic, not an
ARM performance claim.

The ARM focused binary passed physically in 3.920 seconds wall time, 4.121
seconds CPU, and 1,808 KiB peak RSS. In root-owned physical ABBA measurements,
source-view warm reconstruction averaged 16.45827 seconds and the dense
candidate averaged 15.09322 seconds, an 8.294% reduction. Cold reconstruction
averaged 23.19485 versus 23.51529 seconds, so the dense candidate was 1.382%
slower. Every run passed both exact prefix comparisons.

The ABBA sequence was CPU-only and serial. A separate application
lifecycle/deployment check using less than one CPU second ran between the first
view and first candidate measurement; no process overlapped a timed run and no
RF was used. Separate full 11,747-candidate ARM runs emitted byte-identical
676,954-byte outputs for view and candidate, both SHA-256
`6819cb39151bb2cbe894e5d427244aa95d1eae73e17469e5033659d2b0a30084`,
which also matches the host output. Whole-process times were 23.69659 seconds
for view and 24.13312 seconds for candidate. Those one-shot full times are
scientific parity evidence, not the repeated warm-path comparison.

The sidecar layout passes the same focused differential test and is
byte-identical to the frozen candidate over all 60 causal prefixes. Ten
interleaved shared-host tail-two runs per layout found essentially unchanged
warm time (0.31848 seconds candidate, 0.31779 seconds sidecar; -0.217%) and a
small cold reduction (0.32566 to 0.32115 seconds; -1.386%). That cold result is
directionally consistent with removing the ARM candidate's layout regression,
but the host experiment does not establish an ARM benefit. No sidecar ARM
artifact was built and no promotion is claimed.

No hardware action was taken by this component agent, and no application
freshness, IQ, detector, or RF claim follows from this research result.

`profile.json` preserves the allocation measurements. `prefix-parity.json`,
`host-timing/`, `sidecar-host-timing-20/`, build/test logs, source copies, and
host/ARM artifacts retain the remaining evidence and reproduction inputs.

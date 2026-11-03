# Exact lane-local Hough CSR research

This isolated research copy tests the exact dirty-cell design proposed by the
preceding peel-work diagnostic. Production remains unchanged at tracking source
SHA-256 `f2fb20b646287e4ef0392131a48e3dff337b14db69ef09564eae1b0439b659bc`.

For each lane, the candidate builds a dense FP64 histogram and a CSR list of
the original point indexes contributing to every Hough cell. Contributor
indexes are appended in the same ascending point order used by the control.
After a track retires points, their cells are marked dirty. On the next full
peak scan, each dirty cell is rebuilt from zero by visiting its still-available
contributors in that original order. Untouched cells retain their prior bits.
There is no subtraction, reassociation, reduced peak scan, changed comparator,
or changed hypothesis order.

The focused test covers the exact first peel, ill-conditioned ordered sums,
multiple points in the same bin, partial and complete retirement, an empty
histogram, and equal peak values before and after retirement. The inherited
tracking tests and both focused tests pass under ASAN/UBSAN.

Scientific parity passes. The candidate's stateful result matches its unchanged
cold reconstruction for all 60 causal DS9 prefixes, and its complete 64-track
serialization matches the control at SHA-256
`6819cb39151bb2cbe894e5d427244aa95d1eae73e17469e5033659d2b0a30084`.

The host performance result rejects this layout. With allocation reporting
compiled out of both timing binaries, the 60-prefix stateful total is 28.369 s
for the CSR candidate versus 10.455 s for the control, a 2.81x regression.
Whole-process wall time is 40.80 s versus 20.43 s. The candidate therefore does
not meet the prerequisite for an ARM build or run.

Allocation evidence comes from a separate diagnostic binary. The largest lane
retains 39,625,408 bytes for the dense histogram, offsets, contributors and
dirty map, plus 17,392 bytes of point-to-chunk lookup and 8,444 bytes of
temporary build storage. It replaces only the prior 4,096-byte per-slope bin
vector, for 39,647,148 net additional peak bytes. The two largest lanes need
76,027,260 bytes (72.51 MiB) if two workers overlap. Adding the already retained
88,221,442-byte forward-bin cache gives about 156.64 MiB of tracking cache and
CSR payload before other application state and allocator overhead.

The timing run does not attribute the regression among CSR construction, dense
cell traffic, dirty checks and indirect contributor reads. It does establish
that the measured reduction in additions is insufficient for this concrete
layout on the host. No production promotion, ARM build, public contract,
fixture, hardware, or RF change followed.

Reproduce from the repository root:

```sh
base=reports/2026_09_30_native_adaptive_deployment/tracking/hough-peel-csr-research-v1
bash "$base/build.sh" host /var/tmp/leo-hough-peel-csr-host
/var/tmp/leo-hough-peel-csr-host/prefix-control \
  reports/2026_09_30_native_adaptive_deployment/tracking/candidates.tsv \
  5 100663296
/var/tmp/leo-hough-peel-csr-host/prefix-candidate \
  reports/2026_09_30_native_adaptive_deployment/tracking/candidates.tsv \
  5 100663296
/var/tmp/leo-hough-peel-csr-host/prefix-candidate-allocation \
  reports/2026_09_30_native_adaptive_deployment/tracking/candidates.tsv \
  5 100663296 --tail-two
bash "$base/build.sh" sanitize /var/tmp/leo-hough-peel-csr-sanitize
```

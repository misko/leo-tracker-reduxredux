# Exact dense dirty-cell Hough research

This isolated experiment evaluates the compact exact reuse design proposed
after the CSR rejection. Production remains unchanged at source SHA-256
`f2fb20b646287e4ef0392131a48e3dff337b14db69ef09564eae1b0439b659bc`.

The candidate retains one slope-major FP64 histogram and one dirty byte per
cell. The first peel accumulates in the control's slope/ascending-point order.
When a track retires points, their cells are marked and zeroed once. The next
peel traverses available points in the same ascending order and adds a weight
only when its destination is dirty. The unchanged full peak scan clears dirty
flags. Untouched cells retain their prior bits. The implementation never
subtracts or reassociates values and does not alter peak ties, hypotheses or
peel order.

Scientific parity passes. The focused test covers the exact first peel,
ill-conditioned ordered sums, duplicate-bin contributors, partial and complete
retirement, empty input, and equal peak values before and after retirement.
The candidate matches unchanged cold reconstruction for all 60 causal DS9
prefixes. Its complete 64-track output matches the control at SHA-256
`6819cb39151bb2cbe894e5d427244aa95d1eae73e17469e5033659d2b0a30084`.
Focused and inherited tracking tests pass under ASAN/UBSAN.

The host performance gate fails. With allocation logging compiled out of both
timing binaries, the 60-prefix stateful total is 23.305 s for the candidate and
10.814 s for the control, a 2.16x regression. Final warm tail time is 0.793 s
versus 0.328 s. Whole-process wall time is 35.03 s versus 21.58 s. This layout
is faster than the rejected CSR candidate but remains substantially slower than
the existing direct accumulation.

Allocation reporting uses a separate binary. The largest lane adds 16,608,878
peak bytes after replacing the control's 4,096-byte slope buffer. The two
largest lanes add 33,213,679 bytes (31.68 MiB). Combined with the existing
88,221,442-byte forward-bin cache, two-lane cache and histogram payload is
about 115.81 MiB before other application state and allocator overhead.

The result rejects dense cross-peel histogram retention on the host. The dirty
test and retained 14.1 MiB histogram per lane cost more than the avoided FP64
adds and zeroing. No ARM build or run, production promotion, public contract,
fixture, hardware, or RF change followed.

Reproduce from the repository root:

```sh
base=reports/2026_09_30_native_adaptive_deployment/tracking/hough-peel-dense-dirty-research-v1
bash "$base/build.sh" host /var/tmp/leo-hough-peel-dense-dirty-host
/var/tmp/leo-hough-peel-dense-dirty-host/prefix-control \
  reports/2026_09_30_native_adaptive_deployment/tracking/candidates.tsv \
  5 100663296
/var/tmp/leo-hough-peel-dense-dirty-host/prefix-candidate \
  reports/2026_09_30_native_adaptive_deployment/tracking/candidates.tsv \
  5 100663296
/var/tmp/leo-hough-peel-dense-dirty-host/prefix-candidate-allocation \
  reports/2026_09_30_native_adaptive_deployment/tracking/candidates.tsv \
  5 100663296 --tail-two
bash "$base/build.sh" sanitize /var/tmp/leo-hough-peel-dense-dirty-sanitize
```

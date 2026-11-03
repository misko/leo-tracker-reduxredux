# Exact touched-bin Hough prefix research

This isolated research copy tests a low-memory alternative to retaining dense
Hough histograms. For each prior peel it retains the exact top-64 cells and the
old-point availability mask. On an append-only prefix it rebuilds only cells
touched by positive new evidence: old values are accumulated from zero in the
original point order, followed by the new points in their original order. The
top set is selected from updated touched cells plus untouched prior top cells
with the original comparator. Hypotheses and winners are always recomputed.
The next peel uses cached state only while its old-point availability mask is
bit-for-bit equal; a mismatch switches that lane to the frozen full histogram
path.

The approach is exact but slower on the measured host. All 60 causal DS9
prefixes match cold reconstruction bit for bit. The last append uses the
incremental path for 49 peels, the full path for 15, and encounters four mask
divergences. Despite this coverage, stateful reconstruction totals 19.0246
seconds versus 15.5752 seconds for the same-machine production control, a
22.1% regression. Scanning the old bin indexes, testing touched membership,
and maintaining the reduced frontier costs more than the avoided additions and
full-cell scan on this CPU.

The host unit covers equal-valued top-cell ties with every top cell touched,
and the inherited tests cover reorder, expiry, configuration and capacity
fallback. No sanitizer, ARM build, physical run, production edit, or golden
change followed: the experiment failed its performance triage before those
stages. `qualification.json` binds the source, executables, fixture and raw
results. `build-host-o3` is the qualified build directory; the earlier
`build-host` directory is an unqualified intermediate made before the final
test and counter freeze.

Reproduce the qualified host research binary from the repository root:

```sh
base=reports/2026_09_30_native_adaptive_deployment/tracking/hough-prefix-research
flags='-std=c++17 -O3 -fno-fast-math -fPIC -Wall -Wextra -Wpedantic'
g++ $flags -I"$base/source" -c "$base/source/tracking.cpp" \
  -o "$base/build-host-o3/tracking.o"
ar rcs "$base/build-host-o3/libleotracking.a" \
  "$base/build-host-o3/tracking.o"
g++ $flags -I"$base/source" "$base/source/test_tracking.cpp" \
  "$base/build-host-o3/libleotracking.a" -o "$base/build-host-o3/test-tracking"
g++ $flags -I"$base/source" "$base/source/tracking_prefix_benchmark.cpp" \
  "$base/build-host-o3/libleotracking.a" \
  -o "$base/build-host-o3/tracking-prefix-benchmark"
"$base/build-host-o3/test-tracking"
"$base/build-host-o3/tracking-prefix-benchmark" \
  reports/2026_09_30_native_adaptive_deployment/tracking/candidates.tsv \
  5 100663296
```

The production source remains `native/adaptive/tracking/tracking.cpp` and does
not contain this experiment.

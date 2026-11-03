# Location scoring research variants

The fourteenth recipe argument `immutable` (requires `bank`) binds the CLI's
owned fixture to a private immutable-orbit session. The owner must keep arrays
alive and unchanged until unbind/rebind or context destruction. Rebinding
invalidates caches even at the same address/generation. Changed metadata falls
back to checked scoring; normal public API callers retain mutation checks.
This avoids repeated state validation and bank authority copies only when the
owner explicitly supplies the stronger lifetime guarantee.

Horizon queries prepare each track's inclusive knot range once before scanning
satellites. Prepared and ordinary queries are compared against the original
predicate, including nonfinite control points and out-of-range times. These
optimizations do not change the horizon criterion or the point budget.

The thirteenth recipe argument `float-pair` is a **rejected performance
experiment**. Its scalar float endpoint estimates use conservative error
allowances and restore the double path when uncertain. Randomized differential
tests and both full host traces pass, but the paired ARM benchmark is about
19.5% slower. Keep it disabled; the tested error allowance is not an all-input
formal numerical guarantee. Sources and receipts remain available for review.

The twelfth recipe argument `bank` enables `LEO_RESEARCH_ENDPOINT_BANK`.
Unlike the rejected general hash cache, it directly indexes track/satellite
pairs and lazily stores just the two held-out endpoint states at each time
offset. The state-block pool is capped at 32 MiB per worker; partition metadata
and an orbit-authority copy consume additional bounded memory. Changed orbit
bytes, grid, generation, partition or held-out endpoint times invalidate the
bank. Single-satellite warm-start calls bypass it. Capacity exhaustion or an
unsupported grid uses unchanged interpolation. Site-dependent predictions and
scores are never cached. It remains opt-in research, not a real-time default.

The horizon prefix now reuses the identical shared-knot dot products across
adjacent intervals, preserving short-circuit comparisons. The bound loop also
computes its Doppler scale and pair normalization before iterating observations;
this avoids repeated ARM divisions without reassociating the arithmetic.
`bound-hoisted-arm-v1` records their symmetric short hardware comparison;
`regional-arm-hoisted-300s-v1` records a complete 400-point ARM run in
235.644 seconds with unchanged selection and full associations. Combined
detector/search cadence is still unqualified.

`build_arm_score_pgo.sh generate LIBRARY ABSOLUTE_OUTPUT` builds an atomic
instrumented scorer for physical ARM training. Capture its `score.gcda` under
the same output directory, then use the `use` mode to build the optimized
binary. Source hashes must still match. Keep training and timing separate;
evaluate on disjoint points and run component tests on ARM. This recipe keeps
`-fno-fast-math` and does not change the numerical search policy.

The bound time-offset loop uses a running stencil index and int32-to-double
conversion, while retaining an int64 loop increment. This removes ARM software
division/conversion from the hot loop without changing the offset grid. The
component test compares generic and planned interpolation on moving states
with negative offsets, non-unit steps and both int32 endpoints. The
`bound-counter-arm-v1` qualification report records the paired hardware timing;
short-run speedups are not continuous-scan qualification.

The eleventh recipe argument `cache` enables experimental context-owned bound
state memoization. A fixed one-million-entry direct-mapped table stores orbit
states keyed by exact time bits and satellite index. Each context also retains
an orbit-authority copy and compares the requested satellite range on every
call, so same-generation mutations invalidate cached values. Changes to the
generation or knot geometry invalidate as well. Allocation/capacity failure
falls back to interpolation. The large memory footprint and random lookup cost
must be measured; passing equality tests does not justify enabling this mode.
The recorded 16-site ARM comparison rejects this cache variant: it is slower
and uses about 197 MiB RSS versus about 25 MiB for the uncached build.

The tenth recipe argument `profile` enables per-partition setup/bound/full-work
diagnostics on stderr. Calls to the clock inside the bound loop perturb timing;
use these only to locate costs, never as interchangeable throughput trials.
`profile_search_point.cpp` evaluates the first Sacramento search point with the
capped objective and emits only its aggregate score. It links against the
instrumented research library and leaves the normal production build unchanged.

The ninth build argument `horizon` enables `LEO_RESEARCH_HORIZON_PREFIX`.
It evaluates the existing cubic control-point horizon criterion once per
satellite/knot interval/site, then uses prefix counts to answer each track's
inclusive time-range query. The exact velocity terms and comparisons are
preserved. The scratch allocation is bounded to two million 16-bit entries;
unsupported size or allocation failure falls back to the original predicate.
Nothing is reused across sites or orbit snapshots. Tests cover time ranges,
velocity-only eligibility, satellite partitions and site replacement.

The seventh recipe argument `planned` selects held-out indexes once per track
and reuses existing Hermite stencils during bound evaluation. The eighth
argument `capped` enables a CLI search-only objective shortcut: initialize the
incumbent threshold at the existing 800-Hz loss cap. The internal sentinel is
never an association result. Search JSON contains objective values only; full
association scoring must run separately at the selected site. Ordinary `score`
mode remains unchanged. These options are opt-in research experiments.

The optional sixth build argument `subset` enables
`LEO_RESEARCH_SUBSET_BOUND`: up to eight distinct, evenly spaced held-out
observations provide an SSE bound about their own mean, normalized by the full
held-out count. The endpoint-pair check runs first; additional interpolation is
needed only when it cannot reject the candidate. Ties and numerically uncertain
cases retain full scoring. This is separate from the existing pair experiment
and remains opt-in. Example arguments after the recipe name:
`arm /var/tmp/leo-modular-location-arm /var/tmp/leo-subset-arm warm progress subset`.

`heldout_bound.hpp` is an opt-in candidate-rejection experiment enabled only
when the scorer is compiled with `LEO_RESEARCH_HELDOUT_BOUND`. For held-out
endpoint residuals a,b and total held-out count N, the RMS for any fitted
constant is at least `abs(a-b)/sqrt(2*N)`. A satellite is skipped only if this
bound, with a numerical guard, exceeds the incumbent held-out RMS at every tau.
Survivors use the unchanged full scorer. Nonfinite/unbounded orbit inputs
disable the shortcut. This remains research: corpus equality and the guard are
not a general floating-point proof over every representable input.

The optional CLI-only `LEO_RESEARCH_SCORE_WARM_START` first recomputes the
previous site's winning satellite at the current site. It never reuses the old
score or omits the full catalog search. Both flags are absent from the default
build. Build the experiment against qualified location objects with:

```sh
TMPDIR=/var/tmp bash tests/native_adaptive/location/research/build_heldout_bound.sh \
  host /var/tmp/leo-modular-location-host /var/tmp/leo-heldout-warm-host warm
```

Use `arm` and the ARM object directory for hardware builds; omit `warm` to test
the bound alone. The recipe runs component tests on host. Compare full score
JSON and regional traces against the default CLI before interpreting timings.
Append `progress` after `warm` to emit one JSON record to stderr per completed
regional search point. The normal stdout search result is unchanged. This lets
a deadline-limited run retain verifiable progress without claiming a complete
search. `tools/evaluate_search_progress.py` compares the retained prefix against
a pinned host trace and requires a successful exit plus the complete final JSON
before declaring the full search qualified.
Evidence is in `reports/2026_10_01_native_replay_qualification/heldout-bound-v1/`
and `heldout-warm-v2-arm/`. No default behavior or public ABI changes.

This directory contains opt-in experiments. The production location build does
not compile these sources.

`score_interpolation_stencil.cpp` replaces only the scorer object in a separate
research archive. It includes the unchanged production scorer under a private
reference symbol, then precomputes the knot index and Hermite coefficients for
each observation/tau pair once per track. The satellite, track, tau and
observation iteration order, horizon eligibility test, state arithmetic,
finite-output check, residual reduction and tie breaking remain unchanged.
Stencil construction is lazy, so empty satellite partitions and tracks rejected
by the horizon test retain the reference behavior without allocating or
interpolating.

Build and test it with the component-owned recipe:

```sh
tests/native_adaptive/location/research/build_score_interpolation_stencil.sh \
  host /tmp/leo-location-stencil-research-host
tests/native_adaptive/location/research/build_score_interpolation_stencil.sh \
  sanitize /tmp/leo-location-stencil-research-sanitize
tests/native_adaptive/location/research/build_score_interpolation_stencil.sh \
  arm /tmp/leo-location-stencil-research-arm
```

The host ABBA comparison is bounded to at most eight four-run sequences:

```sh
tests/native_adaptive/location/research/run_score_interpolation_stencil_abba.sh \
  /tmp/leo-location-stencil-research-host \
  reports/2026_09_30_native_adaptive_deployment/tracking/native-e2.loc1 \
  /tmp/leo-location-stencil-research-host/abba 4
```

The research test compares planned interpolation bit for bit with the public
generic interpolator at knot boundaries, the final knot and nonintegral times.
It covers nonfinite state propagation, invalid and overflowing snapshots, a
final-knot rounding rejection, empty partitions, fully rejected tracks, and
exact candidate/reference scoring. The full fixture comparison additionally
requires identical one-worker and two-worker JSON output.

This experiment does not alter the location ABI, eligibility, tau grid, search
policy, golden fixtures, or production defaults. Allocation failure for the
additional per-track scratch remains a research qualification item before any
production proposal.

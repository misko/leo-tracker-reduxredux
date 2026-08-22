# Exact-transform integration plan for known-pilot analysis

Date: 2026-08-22

Status: implementation complete and qualified; production deployment is release-gated

Qualification results and the parameter decision are recorded in
[`../../reports/2026_08_22_t1_glrt_hardware_aligned_parameter_study.md`](../../reports/2026_08_22_t1_glrt_hardware_aligned_parameter_study.md).

## Decision summary

Keep **one scientific GLRT64 method** and one parameterized known-pilot engine.
Do not introduce separate `standard_fft_glrt`, `research_fft_glrt`, or
`glrt4096` detector methods.

The engine should have two numerical implementations:

1. `direct_phase_bank_v1`: the current implementation, retained permanently as
   the numerical oracle and irregular-geometry fallback; and
2. `exact_transform_v1`: a deterministic execution plan which uses a uniform
   FFT for GLRT and, when both exact and cheaper, a sparse FFT for the first CFO
   refinement.

Standard and Research remain profiles of that engine. They select different
probe schedules, acquisition grids, candidate budgets, and GLRT transform
sizes, but they do not fork the detector implementation.

For the current 2.5 MS/s geometry, the transform implementation can replace
the direct GLRT in active Standard and Research execution after qualification.
It must not delete the direct implementation. The first CFO refinement can use
the transform selectively. The small conditioned-CFO grid should remain direct
initially, and coarse timing/CFO acquisition remains a separate native-kernel
problem.

## What is—and is not—a GLRT version

Four concepts should remain distinct:

| Concept | Examples | Identity rule |
|---|---|---|
| Scientific method | GLRT64 exact versus rolled control | One method, `PilotMethod.GLRT64` |
| Analysis profile | Standard, Research | Configuration, not a new detector |
| Numerical implementation | direct phase bank, exact uniform FFT | Explicit implementation identity |
| Search resolution | 512, 4096, or another transform size | Parameter of the same GLRT |

The intended end state therefore has **one public GLRT method, two internal
numerical implementations, and two currently reviewed profiles**. Historical
direct products remain readable. New accelerated products belong to a new
pipeline release and implementation digest, but they should retain the current
public method name and product schemas.

`GLRT-512` and `GLRT-4096` are useful display labels for grid resolution. They
must not become separate Python implementations or `PilotMethod` members.

## Current profiles

The active configurations already share `TrajectoryFeedbackConfig` and the
same acquisition and pilot-scoring functions.

| Parameter | Standard production | Research v1 |
|---|---:|---:|
| Probe duration | 20 ms | 20 ms |
| Probe offsets per 50 ms | 0, 25 ms | 0, 15, 30 ms |
| Coarse CFO step | 80 kHz | 10 kHz |
| Fine radius / step | 80 kHz / 500 Hz | 10 kHz / 100 Hz |
| Conditioned radius / step | 2 kHz / 100 Hz | 1 kHz / 25 Hz |
| Retained/scored basins | 10 / 10 | 32 / 32 |
| Segmentation basins | 10 | 6 |
| GLRT symbols | 64 | 64 |
| GLRT transform size | 512 | 4096 |
| Inner workers | 4 | 2 |

Research's much denser coarse grid and larger candidate inventory dominate its
extra cost. Accelerating GLRT-4096 is valuable, but it does not make the
81-hypothesis coarse search free and cannot recover a basin discarded before
GLRT scoring.

## Implemented numerical boundary

The lean implementation binds `exact_transform_v1` to the new
`standard-v2-production-2` release instead of adding a public configuration
switch that no production caller needs. The direct oracle remains callable by
tests and is the automatic fallback for unsupported geometry. The release's
implementation digest names the selected kernels:

```text
coarse              = folded-anchor-native-v1
fine refinement     = sparse-uniform-fft-v1-or-direct-grid-v1
conditioned refine  = direct-grid-v1
GLRT exact/control  = uniform-fft-v1-or-direct-phase-bank-v1
```

The planner may fall back based on input geometry, but its rules must be
pinned in code and independent of machine load, CPU model, timing results, or
library availability. Identical configuration and IQ must select identical
kernels on every supported host.

Do not put a benchmark-driven choice in the hot path. Benchmarking chooses the
rules for a new mode version; it does not make a different choice on each run.

## GLRT execution rule

Use the FFT when all of the following hold:

- exact and control matrices have identical shape and timestamps;
- each row's selected symbol times lie on one uniform lattice;
- every row has the same within-frame lattice;
- the selected symbol count does not exceed the configured transform size; and
- the configured grid uses the existing `numpy.fft.fftfreq` ordering.

Zero-pad each frame row to `glrt_size`, transform along symbol time, sum
power—not complex phase—across frames, divide by the existing coherent ceiling,
and preserve the existing first-maximum tie rule. If any condition fails, call
`direct_phase_bank_v1`.

This rule supports both current profiles without special cases:

- Standard: 64 symbols, FFT size 512;
- Research: 64 symbols, FFT size 4096; and
- future sizes such as 1024, 2048, or 8192, provided the public configuration
  validation accepts them.

The implementation should expose one paired entry point so exact and rolled
control always use the same grid and backend. The unpaired historical helper
should delegate to the same engine or remain test-only; it must not evolve into
a second production implementation.

## First CFO-refinement execution rule

For a constant grid

```text
f[k] = f0 + k * delta_f
```

the sparse FFT is exact when `N = sample_rate / delta_f` is an integer. The
arbitrary starting frequency `f0`, including receiver calibration, is handled
by one base rotation. Selected pilot products are placed at their sample-index
residues and transformed once per supported frame.

Exactness alone does not imply a speed-up. Select the FFT only when:

- the CFO grid is finite, positive-step, and exactly uniform;
- `sample_rate / delta_f` is integral within a pinned numerical check;
- requested bins do not repeat within the sampled Nyquist interval; and
- a versioned static work rule predicts less work than direct evaluation.

For a first implementation, inputs whose selected indexes would collide modulo
`N` may fall back to direct evaluation. A later implementation can accumulate
colliding products by residue and remain mathematically exact, but current
Standard and Research geometry does not need that complexity.

A useful deterministic work comparison is:

```text
direct work     proportional to frames * requested_bins * selected_samples
transform work  proportional to frames * N * log2(N)
```

The constant and safety margin must be fixed by a benchmark receipt and then
pinned in `exact_transform_v1`. Do not time both implementations at runtime.

Current evidence gives the following initial policy:

| Grid | N | Initial policy |
|---|---:|---|
| Standard 500 Hz, up to 321 bins | 5,000 | FFT |
| Standard 500 Hz edge, 161 bins | 5,000 | FFT |
| Research 100 Hz, 201 bins | 25,000 | FFT; bounded end-to-end qualification passed |
| 250 Hz over ±80 kHz, 641 bins | 10,000 | FFT |
| 50 Hz over ±10 kHz, 401 bins | 50,000 | Direct unless a batched FFT proves faster |
| Noncommensurate step such as 333 Hz | not integral | Direct |

The conditioned refinement should stay direct in `exact_transform_v1`.
Standard requests only 41 bins and Research only 81; their natural transform
sizes would be 25,000 and 100,000. A bounded prototype found those FFTs slower
than the existing direct grid. This decision can change in a later numerical
mode without changing GLRT semantics.

## What happens when geometry changes

### Different probe windows

Changing probe duration changes the number of supported Starlink frames, not
the within-frame GLRT lattice or the natural CFO transform length.

- Longer probes add rows. GLRT and refinement cost and scratch grow roughly
  linearly with supported frames.
- Shorter probes reduce repeated-frame support and may hit the existing
  minimum-frame outcome.
- GLRT continues to sum frame powers noncoherently. A longer probe does not
  silently change it into a cross-frame coherent detector.
- Scratch must be bounded from the configured maximum probe samples before
  accepting a job.

Probe offsets and subwindow schedules affect how many independent probes are
run; they do not create another GLRT implementation.

### Different GLRT sizes

For the current 4.4 microsecond symbol spacing, GLRT bin spacing is:

```text
delta_f = 1 / (4.4 microseconds * glrt_size)
```

| Size | Grid spacing |
|---:|---:|
| 512 | 443.9 Hz |
| 4096 | 55.5 Hz |
| 8192 | 27.7 Hz |
| 16384 | 13.9 Hz |

Larger zero-padded FFTs sample the same 64-symbol response more finely; they do
not add observations. The 64-symbol aperture is about 281.6 microseconds, so
its physical response width is on the order of 3.55 kHz. Very large FFT sizes
can improve peak interpolation but cannot manufacture equivalent resolving
power. Any larger size still requires gate and look-elsewhere qualification.

To add actual information, change the supported symbol aperture or combine
frames under an explicitly justified phase model. Either change defines new
detector science and is outside this numerical replacement.

### Different CFO steps and radii

- Smaller step increases the natural FFT size as `sample_rate / step`.
- Wider radius increases the direct grid cost but barely changes the FFT cost
  while the same transform size is used.
- A very fine but narrow grid can favor direct evaluation because most FFT bins
  would be discarded.
- A nonuniform or noncommensurate grid uses the direct fallback. Do not add a
  chirp-z dependency until measured workloads justify it.
- Denser fine or conditioned grids improve localization only after a coarse
  basin survives. They do not solve coarse inventory loss.

### Different coarse grids and basin counts

Coarse step, separation, and retained count change the hypothesis inventory,
not just numerical resolution. They must remain explicit profile parameters.

The first native coarse improvement should precompute reference energies,
support inverses, and received-energy inverse denominators once per probe.
Unit-magnitude CFO derotation makes those denominators identical across every
CFO row; merely sharing the power prefix still repeats millions of square
roots. Compare a row-streaming kernel with a fully materialized
`probe x CFO x sample` bank so a nominal batch does not evict Gauss's 36 MiB
last-level cache.

Research's 10 kHz coarse grid deserves a later filter-bank study, but it should
not delay the exact GLRT replacement. A new coarse formulation must continue
to preserve all normalized folded scores and basin ordering against the native
and Python oracles.

## Persisted identity and compatibility

The transform path is mathematically equivalent but not byte-identical to the
direct summation. Observed differences reached approximately `9e-14` for GLRT,
`6e-15` for fine refinement, `3e-11 Hz` in interpolated CFO, and `3e-15` in
candidate scores on bounded synthetic and reviewed real-IQ checks.

Therefore:

1. preserve all existing product schemas and `PilotMethod.GLRT64`;
2. retain readers for historical direct products unchanged;
3. bind deterministic dispatch to a new stage implementation revision;
4. name the transform kernels in `receiver_standard_implementation_digest`;
5. issue a new code-backed Standard pipeline release;
6. let Research obtain a new pipeline-definition digest from the revised stage
   graph and release identity; and
7. never reuse a direct-path cache entry for transform-path output.

The path-stage implementation version advances from
`standard-v2-production-1` to `standard-v2-production-2` when the release is
activated. That does not require renaming the public GLRT method or inventing a
parallel product namespace. If review concludes that a public product's
algorithm-version field semantically promises the floating evaluation order,
introduce a new product algorithm version instead of weakening that promise.

Do not round output merely to recover old content digests. If canonical
rounding is scientifically desired, qualify it as its own numerical version
against both direct and FFT results.

## Delivery sequence

### Milestone 1 — split the oracle from dispatch — complete

- Rename the current paired implementation internally as the direct oracle.
- Add deterministic capability checks and retain the legacy direct oracle.
- Add deterministic capability checks and backend counters for benchmarks.
- Make no production profile change.

Exit: all current tests and golden products remain byte-identical in direct
mode.

### Milestone 2 — exact GLRT transform — complete

- Add one parameterized paired FFT implementation for sizes 512 and 4096.
- Test random arrays, nulls, exact pilots, controls, ties, boundary windows,
  different frame counts, and deliberately irregular timestamp fallbacks.
- Shadow direct and FFT results on Standard and Research fixtures.

Exit: identical selected bins and gate decisions, classified score drift, at
least 10x GLRT-pair speed-up for 512, and a material gain for 4096.

### Milestone 3 — cost-aware first refinement — complete

- Add the sparse exact transform and direct fallback.
- Pin a static selection rule from unloaded Gauss benchmarks.
- Cover central and truncated edge grids, arbitrary `f0`, and commensurate and
  noncommensurate steps.
- Leave conditioned refinement direct.

Exit: identical fine-grid winning bins and basin ordering across the bounded
corpus, with a whole-probe improvement for Standard. Research enables its
100 Hz transform only if end-to-end measurements improve.

### Milestone 4 — activate Standard — qualified, release-gated

- Activate exact dispatch in the new release without changing Standard search
  parameters.
- Keep four inner workers while measuring the numerical change; do not combine
  kernel and scheduling experiments.
- Run the one-second protected gate, one complete path, then the four-path
  60-second replay.

Exit: no unexplained inventory, gate, trajectory, or null-control changes;
bounded RSS; deterministic output ordering; and a reviewed runtime receipt.

### Milestone 5 — activate Research — qualified, release-gated

- Give Research a new definition digest through the revised release graph.
- Use GLRT-4096 through the shared FFT path.
- Resolve the 100 Hz fine-grid crossover from real 32-basin workloads.
- Keep two inner workers until the dense profile is benchmarked under the
  database scheduler's outer concurrency.

Exit: the same research candidate inventory and downstream segmentation input,
with separately reported coarse, refinement, and GLRT costs.

### Milestone 6 — coarse native kernel

- Batch geometry and normalization work before attempting wider parallelism.
- Precompute the CFO-invariant denominator and support data.
- Benchmark row streaming versus small full-bank batches and compiler versus
  explicit AVX2/FMA implementations.
- Tune worker policy only after the final kernel shape is known.

Exit: at least 2x coarse-stage improvement, unchanged basin inventory, and an
end-to-end whole-machine scheduling policy rather than an isolated worker-count
maximum.

## Qualification matrix

Every accelerated mode should cover:

| Dimension | Required cases |
|---|---|
| GLRT size | 512, 4096, one larger supported size |
| Probe support | insufficient, 2 frames, typical 14–15 frames, longer bounded window |
| Fine step | 500, 250, 100, 50, and noncommensurate 333 Hz |
| Fine extent | central full grid and both truncated search edges |
| Signal | null, random, exact pilot, rolled control, near tie, near gate |
| Geometry | uniform fast path and deliberately irregular direct fallback |
| Profiles | complete Standard and Research configurations |
| Concurrency | 1, configured default, and reviewed higher worker count |
| Persistence | configuration/implementation digests, serialized ordering, cache separation |

The acceptance comparison classifies every mismatch as representation-only,
score drift, rank change, CFO-bin change, gate change, or downstream membership
change. Only the first class is expected from the exact transforms. Gate and
membership changes require scientific review; test tolerances must not be
expanded merely to admit them.

## Final operating model

After qualification:

- Standard runs GLRT64/512 through `exact_transform_v1`, uses the 500 Hz sparse
  FFT for first refinement, and retains direct conditioned refinement.
- Research runs GLRT64/4096 through the same transform code, and uses the
  cost-selected first-refinement backend for its 100 Hz grid.
- Direct phase-bank GLRT remains callable by tests, compatibility replays, and
  geometry fallback, but is not the normal current-geometry path.
- Historical products remain historical; they are never silently recomputed or
  relabeled.
- Future windows and hyperparameters select behavior through one explicit,
  versioned planner rather than by adding another GLRT implementation.

This fully replaces the current GLRT **execution path** for today's Standard
and Research geometry. It deliberately does not replace the numerical oracle,
conditioned refinement, coarse acquisition, or the scientific work required to
qualify materially different apertures and hypothesis inventories.

# Standard-v2 analysis review — simplification and performance

Working document. Not a contract, not a plan, not committed guidance. Read
`docs/analysis/standard-v2-analysis-path.md` first for how the pipeline
currently works; this document only argues about what to change.

Status of each item is marked:

- **[free]** provably identical output, no golden re-verification;
- **[golden]** same mathematics, different floating-point summation order —
  needs a reviewed golden receipt under the existing process;
- **[design]** changes what the pipeline computes or claims; needs review.

---

## A. Where the time actually goes

Measured on this host (24 cores, `.venv` numpy), replaying the coarse
acquisition kernel in isolation:

```text
serial                          59 ms per 20 ms probe
ThreadPoolExecutor,  2 threads  32 ms/probe   1.83x
ThreadPoolExecutor,  4 threads  17 ms/probe   3.53x
ThreadPoolExecutor,  8 threads  10 ms/probe   5.87x
```

Per-probe cost breakdown:

| Stage | Work per probe | Share |
|---|---|---|
| Coarse anchor grid | 11 CFO x 12 symbols x 2 convolutions over 50,000 lags | **~99%** |
| Fine + conditioned CFO | 321 + 41 grid points on <=3333 samples/frame | ~0.5% |
| Detector workspace (x4 basins) | 15 frames x 300 symbols x 2 templates x 11 taps | ~0.3% |
| QAM (x4 basins) | 15 x 300 cached 8x11 solves | ~0.2% |

4800 probes per four-path session x 59 ms = ~283 s of pure coarse acquisition,
plus a second full pass in trajectory feedback. The ledger records the real
four-path run at 687 s. Consistent.

**Conclusion: coarse acquisition is the runtime.** Anything not in
`_folded_anchor_scores_derotated` is rounding error.

---

## B. Highest leverage: close to free

### B1. The energy convolution is CFO-invariant and computed 132x instead of once — [golden]

`src/leo/analysis/starlink/acquisition.py:688`

```python
energy = np.convolve(np.abs(derotated) ** 2, np.ones(reference.size), mode="valid")
```

`derotated = values * rotation[index]` where `rotation` is unit-modulus, so
`|derotated|**2` is identically `|values|**2`. At 2.5 MS/s every anchor symbol
has `reference.size == 11`, so `np.ones(11)` is the same kernel every time.

This identical 50,000-point convolution is recomputed **11 CFO hypotheses x 12
anchor symbols = 132 times per probe**. It is exactly half of the coarse-stage
convolution work.

Fix: hoist it out of both loops, computed once per probe from `values`.

Payoff: ~2x on the dominant stage.

Risk: not bit-identical, because `|x * exp(j*theta)|**2` rounds differently
from `|x|**2`. The mathematics is exactly unchanged.

### B2. The coarse grid should be one BLAS matmul, not 132 small convolutions — [golden]

The correlation at lag `l` for CFO `f` is

```text
SUM_m values[l+m] * conj(p[m]) * exp(-j*2*pi*f*(l+m)/fs)
  = exp(-j*2*pi*f*l/fs) * SUM_m ( values[l+m] * conj(p[m]) ) * exp(-j*2*pi*f*m/fs)
```

Only the magnitude is used, so the leading `exp(-j*2*pi*f*l/fs)` cancels
identically. What remains is: build `y[l,m] = values[l+m] * conj(p[m])` once per
symbol (a strided view times a length-11 vector), then multiply by a fixed 11x11
CFO matrix `W[m,k] = exp(-j*2*pi*f_k*m/fs)`.

Identical FLOP count. But it becomes one `(50000 x 11) @ (11 x 11)` complex
matmul per symbol — BLAS, cache-friendly, internally threaded — instead of 11
separate direct-convolution passes plus 11 full-probe derotations of 50,000
samples.

Payoff: stacked with B1, plausibly 5-15x on coarse acquisition.

Risk: summation order changes. Prototype against
`tests/analysis/test_standard_performance_equivalence.py`, which exists exactly
to police vectorized-versus-scalar equivalence.

### B3. The trajectory seeder runs three times to produce the same seeds — [free]

`src/leo/analysis/starlink/trajectories.py:313` calls
`_local_seed(indexes, times, frequency, high, config)`. `_local_seed`
(`trajectories.py:368`) takes **no `degree` argument**; it always fits a
degree-1 line. But `_fit_method_degree` is invoked once per degree in `(1, 2,
3)`, so the entire O(n^2)-pairs-with-a-polyfit-inside seeding loop runs three
times per (method, window) and produces byte-identical seeds.

Fix: hoist seeding above the degree loop.

Payoff: 3x on the tracker's hot spot.

Risk: none. Provably identical output.

---

## C. Where the design is more complicated than the science requires

### C1. Eight detectors are really three, and five cannot change any decision — [design]

Written as one statistic, the bank collapses:

```text
T(nu) = SUM_f | SUM_{s in S} c[f,s] * exp(-j*2*pi*nu*tau_s) |^2
        / SUM_f ( SUM_s |c[f,s]| )^2

anchor8         = T(0) with S = 8 spread symbols        the nu=0 slice
glrt32 / glrt64 = max_nu T(nu) with S = 32 / 64         the same thing, searched
differential*   = the lag-1 phase estimator of the same c
edge_tracker    = SUM |c|^2, the same c with no combining at all
symbolwise      = the acquisition's own verify score, already computed
```

Under a common signal model, GLRT with a chosen aperture dominates anchor-8 and
both differentials. Anchor-8 is a special case with `nu` pinned; the
differentials discard coherent gain to buy CFO immunity that GLRT obtains by
searching.

The pipeline already acts on this: `select_trajectory_representatives` skips any
family without a GLRT-64 member. **Seven of the eight detectors' trajectory fits
are computed, deduplicated, persisted, and can never trigger a replay.**

Suggestion: make GLRT the single detection lane with a swept aperture
(32/64/128), keep QAM as the one genuinely independent confirmer, keep
symbolwise because it is free, and demote anchor-8, the differentials and
edge-tracker to an opt-in diagnostic flag. Product surface drops from 8 curves
to 3; the trajectory bank drops from 8 independent fitting problems to 2.

Counter-argument to weigh: the bank was built to answer "do independent methods
agree?" and it did — every family independently highlights 26-39 s on the
reference recording. C1 argues that question is now answered, not that asking it
was wrong.

### C2. `edge_tracker` alone forces a 4x workspace, and the workspace ignores requests — [design]

`src/leo/analysis/starlink/pilot_methods.py:503` builds the correlation
workspace over `np.arange(2, 302)` — all 300 symbols, unconditionally, both
templates, regardless of which subsets the detectors requested. The union of
every detector except `edge_tracker` is symbols 2..65 plus 8 anchors, roughly 70
symbols.

The workspace is ~4x larger than needed, and the only reason it needs to be that
large is the weakest detector in the bank.

Fix: compute the union of requested symbol sets. Combined with C1, ~4x smaller.

### C3. Non-GLRT families silently consume the replay budget — [free]

`src/leo/analysis/starlink/trajectory_feedback.py`,
`select_trajectory_representatives`:

```python
for family in bank.families[:maximum]:      # maximum = 16, ordered by start_s
    ...
    if not glrt64:
        continue                            # slot already spent
```

Families are ordered by start time and truncated to 16 **before** the GLRT-64
filter. A run with many early symbolwise-only or edge-tracker-only families can
fill all 16 slots and suppress GLRT-64 replays later in the dwell — silently,
with no truncation counter reflecting it.

Fix: filter to GLRT-64-bearing families first, then take 16.

Severity: latent. Only 4 families exist on the reference recording, so it has
never bitten. It is exactly the failure that appears on a busier dwell.

### C4. The pipeline estimates frame epoch every probe and throws it away — [design]

`TrajectoryObservation` (`trajectories.py:15`) carries `sample_start`, `time_s`,
`tracking_cfo_hz`, `score`, `control_score`, `margin`. **No epoch.**
`local_epoch_sample` is persisted in the pilot document and never enters
tracking.

This is the largest scientific opportunity in the codebase and costs no new
signal processing. A Doppler-shifted emitter scales carrier and symbol clock by
the same factor, so

```text
d(epsilon)/dt = -(CFO / f_carrier) * fs      samples of frame-epoch drift per second
```

At 20 kHz CFO on an ~11.7 GHz carrier, v/c is about 1.7e-6, giving roughly **250
samples of epoch drift across a 60 s dwell**, against an epoch refined to +/-1
sample and wrapping every 3333. Comfortably measurable. Consequences:

- **A second independent tracking observable.** Two branches at the same CFO but
  different epochs are different emitters. The current tracker cannot tell them
  apart, and this is precisely the multi-target disentanglement the working
  record calls unqualified.
- **A free physical consistency check.** The ratio of CFO drift to epoch drift
  yields an independent estimate of the carrier frequency. A stationary
  interferer or a processing artefact fails it. This is a specificity check of a
  kind the pipeline currently has none of — stronger than any rolled-code
  control, because it tests kinematics rather than code.
- **Zero additional computation.** The number is already estimated, ranked on,
  and persisted.

### C5. One control per probe forces a global hack; K controls remove it — [design]

Each probe yields a single `margin = verify - control`, a one-sample estimate of
the null. The tracker then reconstructs the null globally: pool all negative
margins across the dwell, robust sigma via MAD, gate at 5 sigma (`_high_gate`).

That global step exists only because the per-probe null is a single number.
Templates are cached by `(rate, edge, roll)`, so extra rolls cost correlation
only, and the workspace already computes two templates in one pass.

Suggestion: score K of about 4-5 distinct rolls per probe. The margin becomes a
per-probe z-score with a local mean and variance, so:

- the global 5-sigma MAD gate disappears entirely — one statistic, locally
  normalized;
- the gate stops depending on how much of the dwell is signal-bearing. Today a
  dwell that is mostly signal has few negative margins and therefore a poorly
  estimated sigma;
- `low_gate = 0` and `high_gate = 5 sigma` collapse into one threshold with an
  actual interpretation.

A case where slightly more arithmetic makes the logic substantially simpler.

### C6. QAM computes the most precise CFO in the system and discards it — [free]

`analyze_pilot_qam` returns `residual_cfo_refinement_hz` from a weighted,
unwrapped phase-slope fit across 300 symbols x 15 frames — an aperture about 5x
longer than GLRT-64's. Then `pilot_methods.py:388`:

```python
PilotMethodScore(PilotMethod.QAM_ACCURACY, qam_accuracy, None, qam_accuracy,
                 0.0,                       # residual CFO, hard-coded zero
                 acquired_cfo_hz)
```

The refinement is dropped, and QAM contributes a track observation sitting at
the acquisition's frequency.

Fix: pass it through. It is clipped to +/-2 kHz and only meaningful when the
pilot is genuinely present, so it is a refinement of an existing lock rather
than an acquisition — exactly what a tracking observable should be. Likely the
lowest-variance CFO point in the bank.

---

## D. Plumbing

### D1. Wire reuse for stage 5 — the single biggest practical change — [design]

`src/leo/pipeline/derivation.py` has the complete stage-derivation key
(algorithm version, configuration digest, environment digest, implementation
digest, scope, raw chunk-closure digests), and the catalog enforces
`legacy | computed | reused`. But `ProcessingService.run_once` registers
everything as `legacy` and never looks up a prior derivation.

Practical consequence: **tuning a trajectory gate re-runs acquisition.** Every
tracker iteration costs the full ~687 s even though stages 0-5 are provably
unchanged — their derivation key does not move.

Reuse for `path-pilot-scan` alone converts tracker development from ~11 minutes
per iteration to seconds. Handoff 04 owns this. From a "what unblocks the
science" standpoint it outranks every optimization in section B, because it
changes the loop rather than the constant.

### D2. Merge stages 6 and 7 — [design]

Stage 7 needs both the pilot scan and the bank. The split means the largest
document in the pipeline (1200 probes x 4 basins x 8 scores) is serialized,
digested, parsed and re-serialized for digest verification an extra time. The
split's only justification is independent reuse granularity, which does not
exist yet (D1). Splitting again later is cheap if reuse makes it worthwhile.

### D3. The presentation product duplicates every scientific document — [design]

`PathPresentationAnalyzer` embeds full `power_timeline`, `waterfall`,
`pilot_scan`, `trajectory_bank`, `trajectory_feedback` and `trajectory_table`
documents by value. Every large document is stored **twice per path** — 8 copies
of the pilot scan per run.

Suggestion: reference product digests instead of embedding. The PNG renderer
already reaches for the full source separately via `subject_png_source`.

### D4. Concurrency is under-configured, not mis-architected — [free]

An earlier draft of this review claimed the in-stage `ThreadPoolExecutor` was
GIL-bound and should be a process pool. **Measurement disproves that.** NumPy
releases the GIL inside `np.convolve`, which is 99% of the work, so the thread
pool scales (1.83x / 3.53x / 5.87x at 2 / 4 / 8 threads on this 24-core host).

The real problem is that three separate concurrency knobs are all set for a much
smaller machine:

| Knob | Where | Default | Effect |
|---|---|---|---|
| Worker processes | `deploy/systemd/leo-worker@.service` instances | 2 enabled | Concurrent jobs |
| Per-class lease caps | `processing_resource_capacity` table, seeded by migration `e63b8f41a2c7` | streaming 16, cpu 8, memory 4, **heavy 4** | Global ceiling per resource class |
| In-stage thread pool | `TrajectoryFeedbackConfig.maximum_workers` | **4** | Coarse-second batches inside one pilot-scan/feedback job |

On a 24-core host, `maximum_workers = 4` leaves most of the machine idle inside
the stage that is 99% of the runtime. Raising it is the cheapest real speedup
available and requires no code change — only a pipeline-release configuration
change. See section F.

Caveat: the three knobs multiply. `heavy = 4` concurrent jobs each running
`maximum_workers = 20` threads is 80 threads on 24 cores. Choose the product,
not each knob independently.

### D5. Four overlapping status enums — [design]

`StageOutcome`, `NumericalStatus`, `StandardScientificStatus` and
`ScientificConfidence` all encode variations of complete / no-result /
insufficient / partial, with hand-written mappings between them
(`_derived_science_outcome`, `_report_outcome`, `_path_status`). Each mapping is
a place for silent semantic drift. One enum with an explicit lattice would
remove three translation layers.

---

## E. Smaller correctness and clarity notes

| # | Note | Where | Class |
|---|---|---|---|
| E1 | GLRT peak is `argmax` on a 444 Hz grid with **no parabolic interpolation**, unlike the fine CFO search which uses `_quadratic_peak`. Three extra flops would cut CFO quantization error 5-10x and directly tighten trajectory residual RMS. Cheapest accuracy win available. | `pilot_methods.py` `_glrt_pair.evaluate` | golden |
| E2 | `tools/compare_edge_pilot_methods.py:271` carries a **third independent `_glrt` implementation**, alongside `src` `_glrt` and `_glrt_pair`. The two in `src` are deliberately cross-checked by `test_standard_performance_equivalence.py`; the tools copy is not. Drift risk in the lane that gets iterated on. | tools/ | free |
| E3 | `_merge_groups` re-fits `left_model` for every left group on every pass, and one merge happens per pass, so O(k^3) `polyfit` calls. Caching models per group makes it O(k^2). | `trajectories.py` | free |
| E4 | `_retain_separated` rejects on `epoch_close AND cfo_close`. Correct as intended, but named "separation" and reads as "must be separated in both". Worth a comment stating the disjunction. | `acquisition.py` | free |
| E5 | Two different things are called "anchor": acquisition uses `range(2,302,26)` (12 symbols), the detector uses `linspace(2,301,8)` (8 symbols). Distinct concepts, identical word. | `acquisition.py` / `pilot_methods.py` | free |
| E6 | The probe schedule is parameterized as `subwindow_ms` + `probe_ms` with an integrality constraint (`1000 % subwindow_ms`) and a 40% duty cycle motivated nowhere. The physically meaningful knobs are frames per probe and probes per second; deriving samples from those removes a class of configuration errors. | `probes.py` | design |

Note on apparent duplication that is **not** a defect: the scalar/vectorized
kernel pairs (`normalized_frame_score` vs `_normalized_frame_scores`, `_glrt` vs
`_glrt_pair`, `_folded_anchor_scores` vs `_folded_anchor_score_grid`) are a
deliberate oracle pattern policed by `test_standard_performance_equivalence.py`.
Keep them.

---

## F. Suggested order

**Do first — changes the development loop, not just the constant**

1. Raise the concurrency knobs to match the host (D4, section G below). No code
   change, immediate.
2. Wire reuse for `path-pilot-scan` (D1). Everything else iterates faster after.

**Then — free wins, no numerical risk**

3. Hoist the seeder above the degree loop (B3).
4. Filter families by GLRT-64 before the 16-cap (C3). Latent bug.
5. Pass through the QAM residual CFO (C6).

**Then — large speedups, need a reviewed golden receipt**

6. Hoist the CFO-invariant energy convolution (B1). ~2x.
7. Restructure the coarse grid as one BLAS matmul (B2). The main event.
8. Parabolic interpolation on the GLRT peak (E1).

**Then — simplify the science; a design decision, not a refactor**

9. Add epoch as a tracking observable and the CFO/epoch-drift consistency check
   (C4). The one item that changes what the pipeline can claim.
10. K rolled controls, per-probe z-score, retire the global 5-sigma MAD gate
    (C5).
11. Collapse eight detectors to GLRT + QAM + symbolwise, rest behind a
    diagnostic flag (C1, C2).

**Housekeeping**

12. Merge stages 6/7 (D2), de-duplicate the presentation product (D3), unify the
    status enums (D5).

---

## G. Concurrency: the three knobs

### G1. In-stage thread pool — the one that matters

`src/leo/analysis/starlink/trajectory_feedback.py:53`

```python
maximum_workers: int = 4
```

Consumed by `_bounded_parallel_batches` (`trajectory_feedback.py:372`) in both
`path-pilot-scan` and `path-trajectory-feedback`. Each unit of work is one
one-second coarse window of probes.

It is **not** hardcoded at the call site — it flows from the pipeline release
configuration:

```text
production_standard_v2_configuration()          analyzers.py:741
  -> release_configuration["stages"]            cli/processing.py:883
  -> catalog.add_pipeline_release(configuration=...)
  -> execution.pipeline_configuration
  -> _stage_config(configuration, stage_key)    service.py:1114
  -> AnalysisContext.stage_config
  -> _feedback_config(context.stage_config)     analyzers.py:953
  -> TrajectoryFeedbackConfig(maximum_workers=...)
```

`_feedback_config` accepts any field of `TrajectoryFeedbackConfig`, so
`maximum_workers` is already a supported per-stage configuration key. To set it
to 20, add it to `production_standard_v2_configuration()` beside the existing
`path-waterfall` override:

```python
configuration["path-pilot-scan"] = {"maximum_workers": 20}
configuration["path-trajectory-feedback"] = {"maximum_workers": 20}
```

Then register a **new** pipeline release ID. The configuration is part of the
release authority digest, so an existing release cannot be edited in place; that
is the immutability rule, not an obstacle to work around.

Expected: measured scaling was 5.87x at 8 threads on 24 cores. Twenty threads
should land somewhere around 10-14x on the coarse stage, with falloff from
memory bandwidth.

### G2. Per-resource-class lease caps

`processing_resource_capacity`, seeded by migration
`migrations/versions/e63b8f41a2c7_harden_standard_pipeline_authority.py:171`:

```text
streaming 16   cpu 8   memory 4   heavy 4
```

`claim_job` (`repository.py:1386`) refuses to hand out a job whose resource
class already has `maximum_leases` live leases, under a per-class advisory lock.
The three heavy stages — waterfall, pilot-scan, trajectory-feedback — are
therefore capped at 4 concurrent leases **globally**, no matter how many worker
processes run.

Changing it is a data change (`UPDATE processing_resource_capacity`) or a new
migration. Prefer a migration so the value is versioned with the schema.

### G3. Worker processes

One `leo process worker` process claims exactly one job at a time
(`run_once`). Concurrency comes from running more systemd instances:

```text
systemctl enable --now leo-worker@3.service leo-worker@4.service ...
```

`deploy/systemd/README.md` currently documents enabling two.
`worker_resource_classes` exists on `ProcessingService` but is **not wired to
any CLI flag or environment variable**, so every worker claims every class.
Adding that flag would let a small pool of heavy workers coexist with many cheap
ones.

### G4. What 20 actually buys, per scenario

A single four-path session has 43 nodes but limited DAG width: 4 paths x 2
independent chains, so about 8 jobs can be in flight, of which at most 4-8 want
a heavy lease.

| Goal | Change |
|---|---|
| One session, fastest wall-clock | **G1 only.** `maximum_workers = 20`. Leave workers at 2-4 and heavy at 4. Threads inside the stage are where the parallelism actually exists. |
| Many sessions concurrently | G3 (more worker processes) + G2 (raise `heavy`), and *lower* G1 so the product stays near core count. |
| Both | Keep `worker_processes x maximum_workers` at roughly the core count. On 24 cores: 4 heavy leases x 5 threads, or 2 x 12, or 1 x 20. |

The failure mode to avoid is setting all three high at once: 4 heavy jobs x 20
threads is 80 threads on 24 cores, which costs throughput to context switching
and cache pressure rather than gaining it.

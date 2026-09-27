# Next experiment: nuisance-conditioned fixed-point rescue

This is a source-derived plan after the frozen raw-score rescue failed its
constructed-control gate.  It is not implemented, frozen, or evaluated.  The
failed source and result remain unchanged.

## Why the next scorer must change internally

The raw-score rescue produced false positives on three distinct constructed
tone waveforms.  Each false pair passed both native margins, had status zero,
15 supporting frames per point, identical local epochs and physical CFOs, and
an exact 20 ms separation.  More consistency checks on the same raw fixed-point
statistic therefore cannot address the observed failure.

The native blind detector behaves differently.  It converts the complete
selected 20 ms CI16 probe to FP64 complex samples, fits the existing stationary
tone nuisance model, optionally subtracts the fitted tone in FP64, and only
then performs acquisition and final scoring.  The current guided path converts
only GLRT support and scores raw samples.  Python `conditioned_glrt64_score`
also means conditioned on a supplied timing/frequency hypothesis; it does not
fit this nuisance model.

The smallest credible change is a separate rescue-only native port that runs
the exact blind nuisance transform followed by one fixed full-aperture GLRT.
It must skip coarse timing, fine CFO acquisition, conditioned CFO search and
the five-cell epoch lattice.  Threshold changes or post-positive tone filters
would not preserve the blind detector's tested interference treatment.

## C port

Use a new library and workspace.  Do not change or mode-switch the frozen
`NativeGuidedBoundary` used by the primary `NativeTradeoffDetector`.

```c
typedef struct leo_nuisance_guided_workspace leo_nuisance_guided_workspace;

leo_nuisance_guided_workspace *leo_nuisance_guided_create(
    uint32_t rate,
    const leo_presence_complex *exact,
    const leo_presence_complex *control,
    size_t template_count);

void leo_nuisance_guided_destroy(leo_nuisance_guided_workspace *workspace);

int leo_nuisance_guided_probe_ci16(
    leo_nuisance_guided_workspace *workspace,
    const int16_t *natural_dual_rx_dwell,
    size_t dwell_sample_count,
    uint32_t receiver,
    uint32_t probe_index,
    double predicted_local_epoch_sample,
    double scored_cfo_hz,
    double expected_physical_cfo_hz,
    leo_nuisance_guided_result *result);
```

The workspace owns one `leo_presence_workspace` and a packed CI16 buffer for
one 20 ms probe.  The call validates the complete natural layout, receiver,
probe, rate, `FE_TONEAREST`, scoring CFO range, and the qualified dual-CFO
support bound `0.5 / 4.4 us + 1e-6 Hz`.  It then performs these operations in
order:

1. Pack the chosen same-RX probe from natural `[sample, receiver, I/Q]` layout
   into the workspace's contiguous CI16 buffer.
2. Load every packed sample once into the presence workspace as FP64 complex,
   exactly as `leo_presence_run_ci16` does.
3. Clear the profile and nuisance receipts, set nuisance enabled, and invoke
   the unchanged `tone_nuisance(workspace, window_count, packed_ci16)`.
4. Normalize the caller's timing on the physical `rate / 750.0` period.
5. Invoke the unchanged internal `glrt` once with `frame_limit=16` and
   `final_scoring=1` on the possibly tone-subtracted FP64 samples.
6. Derive tracking CFO as `scored_cfo + glrt_residual`; apply the existing
   8 kHz status rule to tracking CFO minus the separate expected physical CFO.
7. Assign the caller's result only after all validation and computation pass.

The existing V2/V3 measurement function cannot be called after nuisance
subtraction.  Its `convert_glrt_support` step copies raw CI16 samples over the
tone-subtracted support and would silently restore the failed raw statistic.
The new core must load the complete probe once, fit/subtract once, and call
`glrt` directly without re-ingestion or re-quantization.

The result should contain the established observation fields plus:

- unchanged supplied scoring/acquired CFO;
- unchanged supplied expected physical CFO;
- raw GLRT residual, tracking CFO, and physical-CFO innovation;
- integer epoch and fractional offset, exact/control scores, margin, support,
  bounds, fractional completion and status;
- the complete existing nuisance receipt: enabled/applied, spectral fraction,
  fitted-power fraction, fitted frequency and nuisance CPU time;
- pack, FP64 conversion, GLRT, total CPU and total wall timing;
- explicit `glrt_evaluations=1` and zero acquisition/lattice counters.

## Python and controller ports

Expose a narrow context-managed class:

```python
class NativeToneGuided:
    def __init__(self, rate: int, edge: str, library: Path | None = None): ...
    def guided(
        self,
        raw,
        *,
        receiver: int,
        probe_index: int,
        predicted_local_epoch_sample: float,
        scoring_cfo_hz: float,
        expected_physical_cfo_hz: float,
    ) -> ToneGuidedObservation | None: ...
```

Create a new rescue-controller variant that receives two explicit ports:

```python
ToneConditionedSameRxRescueDetector(
    primary=unchanged_native_tradeoff_detector,
    rescue_engine=separate_native_tone_guided,
)
```

The primary continues to use its qualified guarded TG11 engine.  The rescue
engine is used only for the candidate's probe-zero seed and probe-two
confirmation.  Preserve the frozen receiver selection, one-acquisition cap,
ten-rank order, Python proposal score, timing transport, identity gates and no
cache injection.  Do not mutate the frozen raw-score rescue or relax the new
controller's two-port distinction.

## Numerical profile and data ownership

Build with the same pinned scientific flags and FP32 FFTW backend as the stable
native detector.  The nuisance spectrum and the final 128/512 transforms use
that backend's FP32 transforms; nuisance least-squares amplitude/subtraction
and GLRT accumulation remain FP64.  Substituting the deployment iterative FFT,
a new strided nuisance estimator, or a re-quantized post-subtraction CI16
buffer would create another numerical detector.

With `LEO_PRESENCE_TONE_CI16=1`, nuisance energy and three lag sums must consume
the packed original CI16 using the unchanged exact integer products and
reduction order.  The least-squares fit and subtraction must consume and modify
only the workspace FP64 copy.  Caller IQ stays immutable.  Workspaces are
serial and non-reentrant; independent threads require independent instances.

## Cost structure

Earlier real-visit medians provide only a planning decomposition:

| Rate | Full CI16 conversion | Nuisance stage | Final GLRT | Sum |
|---:|---:|---:|---:|---:|
| 2.5 MS/s | 0.0278 ms | 0.0438 ms | 0.1736 ms | 0.2452 ms |
| 5 MS/s | 0.1024 ms | 0.1029 ms | 0.1493 ms | 0.3545 ms |

These sums are not measurements of the proposed call.  They exclude
natural-layout packing, Python/ctypes overhead and any added work when a tone
fit reaches least-squares subtraction.  At the allowed maximum of twenty
native points, the same medians imply roughly 4.9/7.1 ms before those omitted
costs.  The first prototype should intentionally repeat full load+nuisance per
guided call.  Reusing a prepared nuisance buffer across hypotheses adds token,
lifetime and invalidation complexity and should follow only if complete-call
measurement shows the repetition is material.

## Component qualification before saved IQ

1. When nuisance is not applied, compare every scientific field bit-for-bit
   with frozen raw guided scoring at the identical supplied coordinate.  Cover
   both rates, edges and receivers; zero input; fractional seams; and CFO
   extrema.
2. On deterministic strong-tone and pilot-plus-tone inputs, run the unchanged
   blind detector once, then score a returned blind candidate at its exact
   epoch plus fractional offset and acquired CFO.  Require the nuisance receipt
   and final exact/control/margin/tracking fields to match the blind candidate
   bit-for-bit.  This checks the working-sample transform as well as the public
   receipt.
3. Require all three distinct tone waveforms from the failed control audit to
   remain inactive under the unchanged margin, support, status and identity
   gates.  Exercise both original and mirrored receiver orientation.
4. Verify scoring CFO is returned exactly, expected physical CFO remains
   separate, boundary support retains the qualified `1e-6 Hz` guard, and
   physical innovation beyond 8 kHz sets reacquisition status without clamping.
5. Verify support and fractional bounds, one GLRT evaluation, zero acquisition
   work, output untouched on error, caller-IQ immutability and RX1 terminal
   guard-page safety.
6. Verify deterministic results under repeat calls and concurrent calls on
   separate workspaces.  The same workspace is documented as serial.
7. Pin templates, profile flags, compiler, FFTW binary, all presence/nuisance
   sources, wrapper sources and the result binary in a build receipt.

Only after those component checks should a newly frozen control run compare the
unchanged primary, the failed raw rescue as a retained reference, and the new
nuisance-conditioned rescue.  Any constructed tone activation rejects the new
variant before diagnostic or recorded-development IQ.  Passing controls would
show that the exact blind nuisance transform addresses the observed failure;
it would not prove that the Python timing/CFO proposal is unbiased or that the
earlier 18--22x planning speed estimate is achieved.

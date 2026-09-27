# Independent source review: nuisance-conditioned rescue

This review covers the preregistered design and the initial C/Python sources.
It is source-only: no saved IQ, detector execution, or DSP timing was used.

## Scope of the parity claim

The C core follows the same final-scoring path as the blind detector when it is
given the same blind candidate representation: the original integer epoch,
the original fractional offset, and the original acquired CFO. It calls the
unchanged `glrt` with `frame_limit=16` and `final_scoring=1`, then derives
tracking CFO as acquired CFO plus the returned residual. This can support a
bit-for-bit qualification test for exact/control score, margin, residual and
tracking CFO.

That claim must remain coordinate-specific. The ordinary rescue supplies a
Python acquisition epoch and CFO and intentionally omits blind conditioned-CFO
search and the five-cell timing lattice. Its result is the blind final
statistic evaluated at the caller's hypothesis, not a reproduction of the
candidate that blind acquisition would have selected.

The separate `guided_components` API is necessary for the strict oracle test.
A blind fractional fit may retain an offset outside `[-0.5, 0.5]`; normalizing
the combined `epoch + offset` can move an integer sample between the two
components. The absolute sampling locations are mathematically equivalent,
but rotation arithmetic and floating-point addition order can differ. Tests
must pass the blind candidate's integer epoch and fractional offset separately
when demanding bit equality. A test using only their summed and renormalized
phase may report legitimate rounding differences and cannot substantiate the
same representation claim.

For the production-like `guided` port, Python's nonnegative
`fmod`/`floor(phase + 0.5)` split matches the C `normalize_phase` policy at the
supported rates, including the fractional physical period seam. Seam and exact
half-sample cases still deserve explicit component tests.

## Nuisance data path

The implementation preserves the important blind-detector ownership and
reduction details:

1. It validates a complete natural-layout 120 ms dwell and packs the requested
   20 ms receiver/probe into the existing contiguous CI16 selection buffer.
2. It loads the complete packed probe into the presence workspace as FP64
   complex samples before nuisance processing.
3. It passes the packed original CI16 buffer, with adjacent I/Q samples, to the
   unchanged `tone_nuisance`. Passing the natural stride-four receiver view here
   would mix receivers and invalidate the integer lag sums; the current source
   does not make that error.
4. With `LEO_PRESENCE_TONE_CI16=1`, whole-probe energy and the three lag sums
   retain the exact integer-product implementation and its original reduction
   order. With `LEO_PRESENCE_TONE_BLOCKED=1`, least-squares amplitude and
   subtraction retain the blocked FP64 order on the workspace copy.
5. The final GLRT consumes the tone-subtracted FP64 samples directly. No V2/V3
   conversion helper, CI16 requantization, or raw-support overwrite occurs.

The build wrapper takes the complete frozen scientific flag list from
`native/profile.json`, compiles the same FP32 FFTW backend, hashes that source,
the FFTW header and shared library, all deployment presence sources, templates,
and its own sources, and links no deployment `fft.c`. This is the required
numerical profile. The frozen build receipt should retain its exact command,
compiler, profile and FFTW hashes in addition to the binary hash.

The result ABI now explicitly records one GLRT evaluation and zero coarse,
fine, conditioned and epoch-lattice evaluations. Python rejects nonzero search
counters. This closes an earlier auditability gap without changing the scorer.

## Final-scoring state and support

Neither final scoring nor final support counting depends on the blind
acquisition's selected frame state. With `final_scoring=1`, `glrt` starts from
frame zero rather than `acquisition_first_frame`; with
`LEO_PRESENCE_GLRT_SYMBOL_DIVERSITY=1`, it alternates early and late symbol
regions independently of `acquisition_regions`. `final_support_frames` uses the
same epoch, offset, count and diversity fallback rules. The direct port can
therefore reproduce the blind final candidate without copying acquisition
support state.

The port correctly keeps scored/acquired CFO distinct from expected physical
CFO. It validates the qualified residual-support boundary, reports the raw GLRT
residual and physical innovation separately, and sets reacquisition status from
the unchanged 8 kHz physical-innovation rule without changing either CFO.
Tests should include both sides of the inclusive 8 kHz gate and the
`0.5 / 4.4 us + 1e-6 Hz` support boundary.

## Qualification requirements and remaining limits

Before the source freeze, component qualification should demonstrate:

- exact blind-candidate parity by passing the original epoch and fractional
  fields separately, at both rates and edges, for nuisance-applied and
  nuisance-not-applied generated inputs;
- raw-guided parity when nuisance is not applied, while distinguishing any
  summed-coordinate normalization roundoff from a scoring change;
- full nuisance receipt parity, including enabled/applied flags, frequency,
  spectral fraction, fitted-power fraction and nuisance CPU accounting;
- deterministic zero search counters, one GLRT evaluation, support/bounds,
  error-with-output-untouched behavior, caller-IQ immutability, RX1 terminal
  probe bounds and repeat-call determinism;
- independent workspaces for concurrent calls, with all workspace construction
  and destruction serialized because FFTW planning/destruction is outside its
  thread-safe execute-only contract.

The tone nuisance fit is a single stationary sinusoid. Passing the three known
tone controls would show that this exact blind preprocessing addresses the
observed raw-rescue failures. It would not establish rejection of multitone,
modulated narrowband interference, signal-plus-tone mixtures, or an unbiased
Python proposal. Those remain evaluation strata, and the constructed-control
stage must still stop on any required negative activation.

The controller preserves primary state ownership, fixed first-inactive receiver
selection, one Python acquisition, ten ordered candidates, probe-zero/probe-two
fresh confirmation and no rescue cache injection. Full nuisance observations
are retained separately from the mapped decision evidence. This is sufficient
for scientific receipts provided the frozen runner serializes every attempted
call, including rejected native points, and accounts for rescue work separately
from copied primary-controller counters.

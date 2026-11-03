# Acquisition coupling audit: no imposed carrier/frame equality found

The reviewed public acquisition path does **not** impose
`CFO / actual_RF = positive_arrival_phase_rate / Fs`. It estimates timing and
frequency from the same IQ and scores, so statistical dependence and selection
effects remain possible. This audit does not identify the cause of the local
positive phase/CFO relationship in the sealed phase-v2 audit, establish a
physical clock constraint, or validate a new localization observable.

One predeclared synthetic check completed all 11 cases, with exactly 66
candidate GLRT evaluations, 50,000 samples per case, two passing component tests,
and 0.5312 seconds total. No real IQ, orbit/position fit, reference coordinate,
production write, old executable script, retry or extra case was used.

## Reviewed call chain

The pinned public source root is
`/opt/leo-fast-auto/f141dbb30321bc8f9e8183576c511431ea60a6b3/worker/src/leo`.
The pre-run [protocol](/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_17_dsx01_iteration9/estimator_coupling/protocol.json) binds the numerical code and inspected
sources. Additional read-only trace receipts are in [static-audit.json](/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_17_dsx01_iteration9/estimator_coupling/static-audit.json).

1. [acquire_symbolwise](</opt/leo-fast-auto/f141dbb30321bc8f9e8183576c511431ea60a6b3/worker/src/leo/analysis/starlink/acquisition.py:634>) searches a joint epoch/CFO surface, retains separated basins, refines epoch at a coarse CFO, then refines and conditions CFO at that epoch. Verification uses other pilot symbols. Receiver frequency calibration changes the absolute CFO search coordinate; it does not change Fs or retime frames.
2. [fast_scan_detector._evaluate_probe](</opt/leo-fast-auto/f141dbb30321bc8f9e8183576c511431ea60a6b3/worker/src/leo/scanner/fast_scan_detector.py:131>) passes the acquired epoch and absolute CFO into the integer scorer and `refine_glrt64_epochs`, and copies both returned fractional epoch and CFO into the response. The parallel legacy `scanner/detector.py` imports the corresponding routines from `pilot_methods`; the fast path imports the owned `fast_scan_scores` implementation.
3. [refine_glrt64_epochs](</opt/leo-fast-auto/f141dbb30321bc8f9e8183576c511431ea60a6b3/worker/src/leo/analysis/starlink/fast_scan_scores.py:117>) scores five integer timing locations around the retained anchor. Each timing score maximizes over a residual-frequency grid. A three-point log parabola selects the fractional epoch; a further score at that epoch returns fractional CFO and margin. Thus fixed acquisition conditioning does **not** mean that the timing score holds residual CFO fixed.
4. In the [correlation workspace](</opt/leo-fast-auto/f141dbb30321bc8f9e8183576c511431ea60a6b3/worker/src/leo/analysis/starlink/fast_scan_scores.py:451>), `frame_start = epoch + round(frame * Fs / 750)` and the fractional offset determines sampled positions. CFO enters a complex derotation at those positions. Neither actual RF, orbital state nor an RF/Fs equality enters this function. The band-limited sampler has no CFO argument. Finite interpolation and derotation need not commute exactly; this is a numerical dependence, not an imposed clock equation.
5. [Persistent candidate construction](</opt/leo-fast-auto/f141dbb30321bc8f9e8183576c511431ea60a6b3/worker/src/leo/scanner/persistent_hop_standard_analysis.py:307>) copies `fractional_tracking_cfo_hz`. [Scanner projection](</opt/leo-fast-auto/f141dbb30321bc8f9e8183576c511431ea60a6b3/worker/src/leo/application/scanner_trajectory.py:64>) obtains physical support from the integer epoch plus signed fractional offset and copies that CFO directly to `measured_cfo_hz`. [Support geometry](</opt/leo-fast-auto/f141dbb30321bc8f9e8183576c511431ea60a6b3/worker/src/leo/application/persistent_hop_trajectory.py:337>) repeats the same frame lattice and computes the mean pilot support center. Actual RF is copied from probe metadata, not used to compute phase or CFO. The reviewed path contains no later continuous-frequency or joint refinement.

The first positive-arrival frame epoch and CFO support center remain distinct.
The sealed 693-point inventory measures their separation as about 8.82–9.48 ms;
this audit does not replace either time coordinate. Public projection retains
passed candidate alternatives. In the earlier winner-only audit, both CFO and
phase came from the same selected peak, so candidate competition and gates are
additional shared selection mechanisms.

## Native frequency grid and existing continuous controls

The fractional **epoch** is continuous; the native residual **CFO** remains an
FFT-grid argmax. [The scorer](</opt/leo-fast-auto/f141dbb30321bc8f9e8183576c511431ea60a6b3/worker/src/leo/analysis/starlink/fast_scan_scores.py:617>) returns
`fftfreq(512, d=symbol_step_s)[argmax]`, then adds acquired CFO. At 4.4 µs symbol
spacing its step is `1 / (4.4e-6 * 512) = 443.89204545 Hz`, namely the
227272.7273 Hz symbol-rate alias period divided by 512. Its origin is each
candidate's acquired CFO, which itself was refined by acquisition; the final
absolute CFO values therefore do not share one fixed global grid. The local
variable named `continuous` in the fractional closure denotes continuous epoch,
not continuous frequency.

An ideal independent uniform rounding error on this grid would have standard
deviation 128.14 Hz, comparable to the downstream 125 Hz density width. That is
a scale comparison, not a demonstrated DSX error law or justification for
altering its likelihood. It cannot explain kilohertz residuals by itself.

This possibility has already been partly tested. The saved
[38-probe continuous replay summary](/home/mouse9911/gits/leo-tracker-reduxredux/reports/three-track-20261016/evidence/raw_cfo_replay_summary.json)
reports median CFO change +53.8113 Hz, maximum absolute change 157.9198 Hz and RMS
change 71.9050 Hz. Mean tested orbit residual remained +2837.7185 Hz. The
[old report](/home/mouse9911/gits/leo-tracker-reduxredux/reports/three-track-20261016/report.md:92) already rejects native
binning as the explanation of that selected kilohertz discrepancy. These are
historical replay results, not a new all-source continuous-refinement result.
The prototype `glrt_refinement_prototype.py` explicitly states that it has no
production caller or persisted-contract user. Its continuous DTFT peak and
iterative timing/CFO refinements must not be attributed to the persisted public
scanner path.

## Frozen synthetic control

The [protocol](/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_17_dsx01_iteration9/estimator_coupling/protocol.json) and all three source hashes were frozen before
calls. A fixed true epoch of 500.25 samples and the nominal
`epoch + round(frame * Fs / 750)` lattice generate a clean lower-edge template.
An independently chosen within-frame modulation warp is applied about the frame
epoch, followed by an explicit carrier rotation. The nominal frame period is
not warped. This deliberately separates generator parameters without imposing
RF/Fs equality; it is not an ADC, propagation or complete hardware clock model.

The ±2000 ppm modulation warp is a synthetic stress, roughly 1000 times a
2 ppm fractional-rate effect. It is not a measured DSX error and cannot establish
real phase/CFO independence or its coupling magnitude. Known anchors and carrier
conditioning bypass coarse acquisition, with no noise, competing signal or
gate-selection trial. All outcomes, including the complete score grids, are
retained in [results.json](/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_17_dsx01_iteration9/estimator_coupling/results.json) and the 11 individual `case-*.json`
receipts.

| Injected carrier Hz | Modulation warp ppm | Conditioning Hz | Estimated epoch samples | CFO error Hz |
|---:|---:|---:|---:|---:|
| −100000 | −2000 | −100000 | 499.474056842 | 0 |
| −100000 | 0 | −100000 | 500.492361295 | 0 |
| −100000 | +2000 | −100000 | 501.064048080 | 0 |
| 0 | −2000 | 0 | 499.474056842 | 0 |
| 0 | 0 | 0 | 500.492361295 | 0 |
| 0 | +2000 | 0 | 501.064048080 | 0 |
| +100000 | −2000 | +100000 | 499.474056842 | 0 |
| +100000 | 0 | +100000 | 500.492361295 | 0 |
| +100000 | +2000 | +100000 | 501.064048080 | 0 |
| +100000 | 0 | +98000 | 500.492848057 | −224.431818 |
| +100000 | 0 | +102000 | 500.493611916 | −219.460227 |

All cases bracketed successfully. With correct conditioning, the estimated epoch
is invariant across −100/0/+100 kHz carrier for every declared warp. The last two
cases reuse identical IQ; their ±2 kHz conditioning change moves the epoch by
only +0.000486762/+0.001250621 samples relative to correct conditioning, while
the acquisition-relative frequency grid leaves approximately −224/−219 Hz CFO
errors. This demonstrates some estimator-coordinate dependence in this example,
not an RF-scaled retiming law. The unwarped perfect-template example has a
visible +0.242361295-sample epoch bias, about 96.94 ns. Treat it as combined
synthetic interpolation/log-parabolic refinement bias, not a true timing
accuracy statement or an isolated diagnosis of either step.

The component tests verify explicit carrier rotation after warp and identical IQ
for the conditioning-only controls. They do not validate the public estimator
against a complete physical signal generator. No additional cases or favorable
selection were allowed after observing these outputs.

## Relation to earlier warp controls and limits

The old `within_frame_scale_control.py` injected +2000 ppm and searched readout
warps at a fixed carrier through the offline continuous prototype. Its matched
synthetic carrier error was below 0.5 Hz. The separate saved three-real-probe
`late_within_frame_scale.json` experiment changed CFO by approximately +0.05,
−4.36 and +2.90 Hz at its selected best warps relative to continuous zero-warp
replay. Those tests do not test carrier-independent epoch generation or prove
DSX sample-clock errors. Only their source/evidence bytes were read here; no old
script or `/tmp` executable was imported or run.

Potential shared-estimator confounds remain: the common IQ/template ambiguity
surface; CFO profiling at every timing proposal; finite frequency bins and
candidate-dependent origins; interpolation and peak-shape approximation;
unmodeled symbol-clock mismatch; multipath or multiple signals; and choosing
both observables through the same peak and margin gate. None is established as
the cause of the phase-v2 strata. There is no justification here to impose a
universal phase/carrier clock constraint or change the localization model.

The hashes attest current pinned code and persisted evidence. They do not prove
the exact historical detector bytes used when the DSX data were acquired. The
previous phase provenance audit already records this limit for surviving old
generators. Current source transport semantics and clean controlled behavior
are the scope of this result.

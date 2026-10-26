# Exact-scope64 residual-cell refinement

The known24-visit single-source control has approximately16.5Hz correlated CFO
scatter. Inspect the immutable deployed124afbbc implementation:500Hz acquisition
fine-grid quadratic interpolation,100Hz conditioned acquisition grid, and512-bin
GLRT64 residual maximum at443.892Hz spacing. The first saved-only stage checks
whether all48 selected final errors are inherited from acquisition with zero
GLRT residual and their maximum absolute error exceeds the4Hz total within-window chirp. If this diagnosis is
not confirmed, stop without new correction/detector outcomes.

The intervention changes ONLY the residual-frequency argmax of the SAME static
64-symbol correlation score. It does not change the saved acquired CFO, integer
epoch, fractional offset, candidate/rank, physical window, symbol aperture,
within-symbol demodulation, frame-power sum, coherent-ceiling normalization,
candidate selection, or original gate decision. Symbols2..65, original14/15-frame
support and exact timing are retained. This is not full re-demodulation at a new
CFO, a new waveform law, or physical validation of template-generated IQ.

From original complex correlations z[f,s], maximize sum_f|sum_s z[f,s]
exp(−2πi delta*t[f,s])|² divided by the deployed coherent ceiling. The original
512-bin target and rolled-control scores/residual must replay within1e−10 and
1e−7Hz. Form the exact finite-lag autocorrelation polynomial and maximize it in
the original winning bin's half-cell (±221.946Hz). A bounded scalar solve has
max64 evaluations and x tolerance1e−5Hz. Do the same for the rolled-control peak
in its OWN original winning cell with its own unchanged normalization.

Independently evaluate the direct complex sums and find a positive-to-negative
derivative root in the SAME cell. Target/control numerical qualification is
separate: require frequency agreement≤.01Hz, score agreement≤1e−10, negative
curvature, original-bin score preservation and distance>.05Hz from a cell edge.
No bracket, boundary, flat or reference failure remains unqualified. No wider
search, retry, increased aperture or retuned tolerance. This is local-cell
numerical closure, not a global peak/source guarantee. Neither a larger exact
score nor corrected margin creates a new detection/admission decision.

The reusable `refiner.refine` numerical port accepts samples/fs/edge/acquiredCFO,
integer epoch/fractional offset/original residual and original exact/control
scores. It returns diagnostics and compact correlations, no storage or truth.

Primary panel: regenerate all original24 paired IQ windows from their immutable
generator/seeds and require exact IQ hashes. Reuse saved candidates without any
detector replay. Persist all original selections/stages and fixed-candidate
refinements, including failures. Corrected frequency is acquiredCFO plus the
continuous target residual; raw and circular error to generated midpoint are
evaluation only. Effective measurement time remains distinct from midpoint.

Fresh held control:8 paired20ms calls before any result, CFO bases100037 and
−100113Hz ×signed slopes±200Hz/s ×global start times0 and7seconds. Epoch127,
amplitude1000,phase.3rad, same deployed sampled-frame/rounded-anchor law and
global integrated chirp. New fixed noise uses SeedSequence([2026102802,index]),
complex RMS300ADC, independent receiver noise on the same physical waveform.
Each original detector candidate list is saved before refinement; choose the
original complete maximum-margin gated candidate, lower-rank tie, without truth
backfill. No original candidate means explicit failure, not another peak.
The16 receiver outputs are not16 independently generated waveforms.

Old full-frame/local_pilot_refinement and FastPilotWorkspace already tested
continuous CFO, joint epoch/rate, odd/even frames and effective times; RX2 cohort
remeasurement did not establish a qualified general localization gain. This
experiment instead isolates the unchanged deployed scope64 residual grid.

Pure owned tests compare finite-lag/direct/FFT scores, signed residuals, known
within-cell maxima, boundary refusal, phase/amplitude invariance, derivatives
and invalid geometry. Actual input smoke regenerates one archived IQ hash but
does not refine a panel observation or call a detector before preflight.
The historical environment lacks SciPy. An initial import-only preparation
failure is retained and charged1second; the scalar solve is a short NumPy-only
golden-section routine and the independent direct derivative uses bisection.
Neither objective, bracket nor numerical criterion changed before freezing.

Maximum300 cumulative numerical worker-seconds INCLUDING preparation/tests,
one worker/BLAS1, at most8 NEW paired detector calls,0 old detector replays.
All64 receiver slots retained. No graph/satellite/position fitting, recorded IQ,
new RF, prior changes, candidate/epoch reselection, scientific retries or cap
extensions. Freeze sources, authority, laws, seeds and tolerances, then require
B exact preflight. Historical source/interpreter identity is checked before/after.
Live stdout stays outside measurement/. Source artifacts remain immutable;
RF outputs seal before saved-only reporting and independent terminal audit.

# Joint physical identity and finite source-revision coefficient model

Use the exact frozen groups and older banks for scans0 and16. Within each
group sum track log likelihoods conditional on ONE common physical candidate
and ONE shared revision coefficient, then marginalize over both. Singleton
tracks retain all original candidates and their own coefficient. Preserve every
common candidate in grouped supports; this is the previously declared shared-
identity restriction, not pruning by current likelihood. Keep a zero-coefficient
control and require parity with the existing JointIdentity implementation.

For each candidate at each trial position/time, form older-minus-original
Doppler and subtract its training mean per track. Prediction is original plus
beta times this direction. Profile a separate track CFO conditional on each
candidate/beta using original Student-t4/100Hz and1MHz weak CFO prior. Thus CFO
handling differs from the historical plug-in-mean residual calibration and
must be tested again. Use the exact symmetric DS7/DS8-learned discrete weights,
with no DS11 tuning. Visibility follows the original candidate geometry.

Controls: zero coefficient; matched linear direction with identical training
RMS and training slope sign, using its own frozen historical weights. Recompute
directions and their derivatives at every trial point. Profiled-CFO envelope
gradients and candidate/coefficient mixture responsibilities give the total
gradient. Derivatives include centering and RMS-normalization dependence.

Before optimization, test all three variants at the original endpoints.
Require zero-control score/gradient parity<1e-6 with JointIdentity and centered
finite-difference gradient discrepancy<.02 in every variant. Record full
evaluation runtime. Do not score geographic error or optimize in this stage.
Each scan benchmark is single-thread capped90seconds. No new IQ, RF, orbit
updates, reference use or held prediction claims.

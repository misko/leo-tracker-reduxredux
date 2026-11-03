# Local information retained under free shared drift

Use all eligible tracks in original screen scans0,4,8,12,16,20,24,28, at the
original IID training endpoints and frozen training-MAP identities from the
same-source CFO audit. Compute E/N/timing predicted Doppler Jacobians with the
existing finite-difference steps. Training rows only. Remove one constant per
track and profile the scan's timing direction to obtain baseline horizontal
information. Use equal expected Student-t4/100Hz information per observation;
the common factor cancels in retention ratios. This is a local conditional
design proxy, not observed curvature, covariance calibration or uncertainty.

Compare projections removing one linear drift direction per receiver, or one
shared linear direction per repeated conditional NORAD across receivers/RF.
Only confident>=0.90 identities with at least two tracks receive source drift;
other tracks retain the baseline model. Center times separately per track,
consistent with profiling each track's CFO. Shared source errors are expressed
in canonical11.2GHz units. Remove nuisance spans via SVD, not a ridge tuned
to geographic truth. Report both generalized eigenvalues of retained EN
information relative to baseline, source/track coverage and all rank failures.

No position fitting, held observations, reference error, correction subtraction
or model promotion. Projection represents an infinite-variance/free-drift
limit; it is not a test of a finite calibrated prior or a full correlation
likelihood. Run single-thread under90seconds. Check projection algebra with
synthetic confounded and orthogonal nuisance examples before real inputs.

# DS7 wave 3: diagnose mismatch and test temporal transfer

The active user goal is sub-kilometre accuracy on DS7. Wave 2 made verified
progress but did not achieve it. Its immutable receipts remain unchanged.
This wave does not substitute an especially favorable prefix for the full
goal or use reference coordinates as estimator inputs.

## Predeclared work

- SOL: training-conditioned candidate/residual and fixed-parameter held
  predictive audit of the first eight independent fits and joint fit.
  Maximum 180 analyzer seconds, one CPU/BLAS thread, no IQ access.
- Terra: verify exported time, receiver/lane and canonical-frequency
  conventions against cached public inputs. Maximum 120 seconds of metadata
  analysis, no IQ access.
- After that audit, Terra may prepare the last chronological group of eight
  (`group8-11`, singles 81–88), using the unchanged original export and bank
  policy. This group is selected by chronology before its predictions or scores
  exist, to test temporal transfer beyond the already examined first group.
  Preparation stops at 1,200 seconds total, 90 seconds per export and 240
  seconds per bank; one CPU/BLAS thread, nice 19, 4 GiB coordination allowance.
  Failed attempts remain recorded; incomplete inputs stay unavailable.
- Any model change or fit receives a separate frozen specification before
  launch. The diagnostic audit alone does not authorize free clock states,
  truth-directed weighting, geographic bias correction or candidate selection
  using held observations.

Only existing cached tracking products and numerical banks are used. No RF,
raw IQ, source-store mutations or QNAP writes. Privileged processes use their
own-UID timeouts and ordinary process-group cleanup. Workers do not read pose,
coordinator scores or full mint coordinates. The coordinator scores only sealed
predictions. The unsurveyed, exposed, repeated-site limitation persists.

## Additional prerequisite experiment

After the preparation benchmark, SOL may test nonlinear receiver-drift recovery
on synthetic observations generated from the frozen first-single bank and its
sealed baseline prediction. This addresses the specific gap left by the earlier
conditional Jacobian test; it is not a real DS7 clock-position fit. Freeze the
generation and fit rules first, retain the full candidate mixture, and use only
training-selected candidates and offsets for synthetic generation. Receiver
slopes are in physical native Hz/s, explicitly normalized by 11.2 GHz/actual RF.
Zero and +/-1 Hz/s are synthetic test amplitudes, not measured hardware bounds.
Maximum 180 analyzer seconds total, 60 per case, one CPU/BLAS thread, nice 19,
no source-store or IQ access. Predeclared recovery tolerances are 100 m position,
0.05 Hz/s drift and 0.05 s recording time. Passing does not supply independent
calibration or automatically admit a real clock model.

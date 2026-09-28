# Training-only recombination of record timing solutions

Use the complete outside-union data and both unchanged covariance models.
Apply the same procedure to all14 source units: three separate panels, all45,
and each dataset exclusion, for decay0 and10. No reference-based selection.

At the previously selected source position, replay each prior qualified source
fit's timing for each record through a one-record instance of the unchanged
CovariancePosition public interface, with held=False. For each record choose
the timing with maximum training score. Resolve exact ties in favour of the
previous selected start. All replays must be finite; verify the selected-state
sum against the published training score within1e-7. Verify the recombined
sum against the full objective within1e-7 and require no training loss.

Refine the recombined point with the unchanged joint model and L-BFGS-B settings:
maxiter140/maxfun200, ftol1e-14, gtol1e-8, maxls30; bounds +/-12km and +/-5s.
Qualify only success, interior parameters and gradient infinity norm <=0.01.
Retain the previously qualified source point as an explicit fallback; select
the highest training score among it and a qualified refinement. The baseline
is prior evidence, not a newly executed fit or an extra new start.

At each selected donor position, replay/recombine timings from the prior
qualified target adaptations, then refine target timings/offsets with geography
fixed. Prior unqualified target starts are excluded by the existing gate.
There is no old-target fallback at a changed position. If the new target fit
does not qualify, preserve that failure and do not fabricate held results.

No new timing grid, data, model, candidate selection, penalty or geographic
start. No retries or relaxed gates. Only training scores construct seeds.
Replay held scores after selection; compare with the published outside-union
fits and with matched new separate-panel fits. Check source position gradients
at1m/0.5m against full-objective differences, tolerance0.002. Geographic scoring
follows sealed execution and uses the same exposed unsurveyed reference.

Each scientific process capped180s/4GiB, BLAS1/nice19, at most two workers.
No RF, waveform reads, propagation or provider fetch. No component code changes.

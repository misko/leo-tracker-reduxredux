# Frozen timing-grid audit on separate DS7/DS8/DS9 panels

Use all 15 outside-union records from each dataset, both unchanged covariance
models (decay 0 and 10), and the selected points from timing recombination.
This diagnostic applies identically to all six separate-panel fits. Pooling
is not repeated in this experiment. No new data or candidate propagation.

At the prior selected position, evaluate each record's training objective at
its selected timing and all 41 timings from -5 to +5 seconds in 0.25-second
steps. Use the unchanged public one-record model with held=False. Require
finite scores. Choose the highest score, preferring the prior timing on exact
ties. Archive every point. The inherited start label `recombine` now denotes
this grid-assembled seed; it is not a replay of the prior experiment.

Check the sum of prior-timing scores against the prior selected full training
score within 1e-7, and the sum of selected record scores against the full new
seed within 1e-7. Require no loss. Refine geography and timings jointly with
unchanged L-BFGS-B settings: maxiter140/maxfun200, ftol1e-14, gtol1e-8, maxls30;
bounds +/-12km and +/-5s. Qualification requires optimizer success, interior
parameters and gradient infinity norm <=0.01. Retain the previously qualified
fit as an explicit fallback, selecting only by training score. No retries.

Evaluate held predictions only after source selection and seal each stage.
Reconcile records/tracks/counts, replay training scores, and check positional
gradients at 1m and 0.5m against full-objective differences (tolerance0.002).
Compute geographic errors against the same exposed unsurveyed reference only
after execution. Compare with the immediately preceding separate-panel fits.
This fixed grid cannot certify global optimality or resolve narrower missed
modes. Do not treat training gains as geographic success.

Six fit processes and six selected-point audits, at most two concurrent,
each capped180s/4GiB, BLAS1/nice19. No RF collection, waveform reads, provider
fetch or component changes. Preserve failures and existing results.

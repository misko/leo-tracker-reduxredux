# Separate fixed-point timing-gradient step study

The original experiment is terminal: all 108 fits completed, but nine of 36
selected-point audits failed the predeclared 0.002 gradient discrepancy gate
at a 0.001 s centered difference. Preserve every original receipt and failure.
Do not refit positions or timings, change the likelihood, rerun the original
audit into its old paths, or label the original failed audit successful.

Evaluate all 36 selected points, including the 27 originally successful ones,
with fixed timing-difference steps 0.001, 0.0005, 0.00025, 0.000125,
0.0000625, 0.00003125 seconds. Record all derivatives, analytic differences,
and whether each interval crosses a 0.25 s interpolation-grid node. This
distinguishes step dependence from a persistent derivative discrepancy.
No result-based step selection or optimizer rerun.

For a separately reported fine-step check, require BOTH finest steps to stay
inside one interpolation interval, each analytic discrepancy <0.002, and
their mutual numerical-derivative difference <0.002 for every timing.
Record this flag separately from the original audit status. Also replay the
frozen training score within 1e-7 and compare held rows with the original
successful audit where available. Publish all failures under either criterion.
If the fine-step checks pass, held scores may be reported with that explicit
qualification; never claim the original 1 ms checks all passed.

Each review process retains 180 s/4 GiB caps, BLAS1/nice19, one scientific
worker and >=5 GiB available memory. No optimization, data changes, new
reference scoring, RF, waveform reads, provider fetch or propagation.

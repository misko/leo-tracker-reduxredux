# Carrier-dependent phase-drift test on the frozen ranked excerpts

Use exactly the72 ranked_waveform_position excerpts and their first eight frames.
No new extraction, quality selection, geographic tuning or RF. Reproduce the
saved common-frequency held-pilot errors before comparing the new model.

Compare cached zero residual, saved long-pilot common-frequency fit, and a joint
model with phase `2*pi*t*(f - offset_MHz*ppm)`. Offset is the nominal pilot
carrier offset from pilot-band center; ppm is a carrier-dependent phase slope,
not an independently calibrated sample-clock estimate. Independent complex gains
per frame/carrier; same gain/frequency fit symbols22–221, held symbols222–301.
No phase coherence assumed between frames.

Bounds f±1500Hz, slope±100ppm. Three L-BFGS-B starts at(saved_f,-50/0/+50ppm),
scaled coordinates f/1000 and ppm/100, analytic gradients, max100 iterations/
160 evaluations, ftol1e-13/gtol1e-8. Select lowest training loss among successful
fits with projected gradient<=1e-6. Retain boundary fits and report all failures;
no replacement or geographic fit in this experiment. Numerical cap120seconds,
single thread/process.

Report equal-excerpt held NMSE changes, frequency shifts relative to the common
fit, slope estimates, bound counts, and every row. The held result must support
the extra parameter before any geographically evaluated change is considered.
The same previously exposed panel, track and acquisition conditioning remains.

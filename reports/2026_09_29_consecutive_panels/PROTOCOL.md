# Consecutive four- and eight-scan localization

Evaluate three chronological blocks per dataset, using all frozen manifest
recordings as the ordering authority. Sort by capture_start_utc_ns, then
session_id. For N recordings, eight-scan blocks start at zero-based indices
0, floor((N-8)/2), and N-8. Each paired four-scan block uses the first four
recordings of its eight-scan block. This is consecutive manifest membership,
not a claim of uninterrupted RF observation or constant dwell/sample rate.
There are 18 joint fits, 72 distinct recordings, and 108 panel memberships.
Do not choose or replace blocks using geographic or held-score outcomes.

One-based eight-scan ordinals: DS7 1–8, 41–48, 81–88; DS8 1–8, 29–36,
58–65; DS9 1–8, 49–56, 98–105. Four-scan ordinals are the first four in each.
Require complete audited checkpoint 09-full-ready before binding inputs.
Retain original eligibility exclusions and the explicit DS9-F028 recovery
where applicable; no recording substitution or outcome-based exclusion.

Use the unchanged shared-track-scale likelihood, decay zero, Student-t4,
100 Hz scale, weak offset prior, causal candidate banks and whole-visit
training/held partition. Fit one position and one timing per recording.
Use generic E/N starts (0,0), (3,-3), (-3,3) km, with all timings zero.
No complete-dataset fitted position or timing initializes any panel.
Use the byte-identical full-DS7 scientific runner and launcher: L-BFGS-B
maxiter 140/maxfun 200, ftol 1e-14, gtol 1e-8, maxls 30; position +/-12 km,
timing +/-5 s. Select highest training score among successful interior fits
with gradient infinity norm <=0.01. Preserve every failure and abstention.

Verify seals, exact manifest slices, nested/disjoint membership, training
score replay within 1e-7, four E/N finite-difference checks within 0.002,
track/observation counts and independent spherical-distance arithmetic.
Report each panel error, median across the three panel errors per size and
dataset, sub-km count out of three, all starts, and matched held-score change
on the first four scans for eight minus four. A median of joint panel errors
is not a single-scan median. Nested four/eight results are dependent and the
three blocks per dataset are not independent-site validation.

One scientific worker at a time, BLAS1/nice19, 12 GiB address-space ceiling,
300 s per process and MemAvailable >=14 GiB. No overlap with input workers
or the complete DS9 model. No automatic retries, RF collection, waveform
reads, propagation or provider fetch. Source selection precedes geographic
scoring. Results use the exposed unsurveyed site reference and do not claim
surveyed accuracy or calibrated confidence.

# Frozen geographic sensitivity to differential receiver drift

Evaluate all three declared allocations (symmetric, RX0 anchor, RX1 anchor)
on the original eighteen consecutive four/eight-scan DS7/DS8/DS9 panels.
Keep the original candidate banks, track eligibility, training masks, q=0.20
trend mixture, 100 Hz noise and 2000 Hz/s background slope scale. Use the
published correction with training-only qualification and unchanged-data
fallbacks. No cone, timing-like term or correlated residual is added.

Each arm/panel fits shared E/N position and one timing per scan with bounds
±12 km and ±5 seconds. Four starts: origin, (+3,−3) km, (−3,+3) km, each with
zero timings, and the published q020 training-selected solution. Fit L-BFGS-B
with maxiter 140, maxfun 200, ftol 1e-14, gtol 1e-8 and maxls 30.
Qualify optimizer success, no bound within .001 in native units, and maximum
absolute training gradient ≤.01. Select the highest training score among
qualified starts. Never select using held outcomes or reference error.

Audit each selected fit by replay within 1e-7 and central finite differences
on every coordinate at steps (.001,.0005) km or (.0000625,.00003125) seconds.
Require discrepancies <.002, agreement between timing steps <.002, and no
timing interpolation-node crossing. Retain failures without retry/substitution.
Also replay the previously scored correction at the old location and retain
every track's held score, responsibility and calibration receipt.

Run all eight correction/composition tests before freeze. One sequential child
at a time, BLAS1/nice19, each capped at 90 seconds and 4 GiB with ≥5 GiB available
RAM before launch. Execute in bounded batches of at most six arm/panel units;
inspect each batch before continuing. Never restart completed units. All 54
arm/panel units remain in scope; incomplete batches are not final comparisons.

Report error and held prediction against q020 separately, including every
panel and start/audit failure. Require all three early/middle/late panels for
each median. Four/eight panels overlap; do not count them as independent trials.
The exposed unsurveyed reference is reporting-only. Correction allocation is
an assumption about unidentifiable common drift, not measured calibration.
Shared donors induce dependence; plug-in likelihoods do not integrate correction
uncertainty. No new RF, raw IQ, propagation or provider fetches.

# Candidate-frequency calibration audit

The assumed candidate likelihood is substantially miscalibrated on the existing
12-scan development panel. Its nominal 50% nearest-peak regions contain 93.34%
of eligible checking observations. This is evidence against using its raw
composite score as calibrated confidence; it does not establish a better location
model or explain the geographic error by itself.

The audit uses the chronological training-only winner from each sealed scan,
never selecting a mode using checking observations or GPS. It reconstructs
predictions with the original training offset and verifies input/source seals
and training-mean parity. Of 13,530 checking groups, 7,933 have exactly one
active prediction and at least one admitted peak. All other groups remain in
the denominator reported for eligibility; this assay supplies no calibration
conclusion for them. Each scan's empirical 50% coverage is between 91.16% and
95.65%. Pooled 90% and 95% coverage are 96.96% and 97.66%.

For n admitted peaks, radius w on the frequency-alias circle of period T,
u=2w/T and S(w) the wrapped-Cauchy central mass with scale 200 Hz, the assumed
nearest-peak CDF is

    F(w | n) = 1 - [(1-p)(1-u)^n + p(1-S(w))(1-u)^(n-1)], p=0.5.

This accounts for accidental closeness among multiple peaks. The initial
singleton-only assay also shows excessive central coverage, but covers a much
smaller population. Monte Carlo checks of the extended CDF pass for n=1,3,7
at four quantiles; the singleton analytic central mass agrees with numerical
integration within 1e-8 for ten cases. These checks validate the calculation,
not its real-data assumptions.

No eligible within-visit adjacent pairs were separated by at most 250 ms.
The requested temporal-dependence diagnostic is therefore uninformative;
zero pairs must not be read as zero dependence. No independence-based
significance test is claimed. The CDF mismatch could reflect signal probability,
scale, detector selection, nonuniform/dependent alternative peaks, or several
of these. Location, identity and offset are plug-in estimates.

Prior evidence supports caution: margin calibration transferred inconsistently;
the frequency-peak assay associated unstable frequency estimates with weak pilot
support; sequence assistance added little over the stronger long-pilot baseline.
Those waveform assays do not prove the same failure occurs in these production
candidates. Cross-RX differences also cannot identify absolute common error.

Next, fit candidate-set signal probability and scale on other datasets using
the complete candidate sets, with each source group counted once and scans
weighted equally. Test both predictive density and this count-conditioned CDF
on the excluded dataset before any geographic refit. Treat this as calibration
of a surrogate observation model, not an automatic accuracy improvement. Do not
set p from this panel's observed coverage or tune against GPS. A calibrated
model must still demonstrate geographic gains under the frozen cold protocol.

Artifacts: `checking-calibration-v1.json` (singleton),
`candidate-count-calibration-v1.json` (all peak counts), their SHA256 sidecars,
and `candidate-count-calibration-v1.png`. Each reconstruction took approximately
15.6 seconds. No fitting, new RF, production change, or baseline replacement.

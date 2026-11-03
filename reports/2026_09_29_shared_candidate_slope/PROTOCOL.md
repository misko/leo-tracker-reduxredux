# Marginal shared candidate slope

Frozen before fits. Nine existing eight-scan DS7/8/9 panels. Training-baseline
MAP assignments with candidate probability times signal responsibility >=0.5
define groups by recording and physical candidate number. Groups with >=2
tracks share a zero-mean Gaussian canonical-frequency slope, with fixed standard
deviations 0.5 and 2 Hz/s. These conservative widths are below the roughly
9.46 Hz/s median absolute residual slope in DS7 early; do not select by accuracy.
Other tracks remain exactly the baseline mixture. In a grouped track, only
the designated candidate component receives the shared slope. All alternative
candidates and the unassociated background retain their original predictions.

Marginalize the common slope over the PRODUCT of the group's mixture densities;
do not multiply independently marginalized tracks. Fit shared E/N and eight
recording times. Score held data as full-group joint minus training-group joint,
at fixed fitted parameters. Groups are training-selected, so this is exploratory
conditional inference, not an untouched-data predictive validation.

Use normalized Gauss-Legendre quadrature for a Gaussian truncated at +/-6 sigma,
128 nodes initially; audit against 256. The omitted Gaussian tail is ~2e-9.
Require train and held score discrepancies <=0.01 and max gradient discrepancy
<=0.01. If this fails, retain the failure rather than claim improved accuracy.
Audit analytic parameter gradient by finite differences (tolerance0.02).
Fit one start at cached optimum, bounds E/N +/-12km and each time +/-5sec,
max100 iterations/160 evaluations, wall cap120sec per panel/width. Qualify only
optimizer success, max projected gradient<=0.01 and no boundary. Retain all
outcomes. No new RF, reference-based tuning, or production changes.

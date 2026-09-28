# Additional numerical verification, before geographic scoring

After the all24 fit returned and was sealed, verify its selected position
gradient using central differences of the full profiled training score at
±0.001 km and ±0.0005 km, holding recording timings fixed. Compare with the
reported analytic/envelope gradient, require absolute disagreement <=0.001
nats/km, and replay the central score within 1e-7. This audits two position
coordinates only; it is not a Hessian, uncertainty calibration or global search.
No re-optimization, replacement point or change to qualification occurs.

One additional 90-second/4-GiB single-thread nice19 job, no retry, run alongside
at most one existing numerical job. Preserve a failure if the audit cannot
finish. Freeze this note and script before executing; no pose values are read.

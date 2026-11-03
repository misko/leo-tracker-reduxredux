# Time-balanced eight-scan sets

Freeze before geographic outcomes. Reuse exactly the24 distinct scans per DS
already present in the early/middle/late eight-scan panels. Sort by recorded
start UTC. Split by chronological rank modulo3 into three disjoint sets of
eight. Each set must include two or three scans from each original window.
Membership uses timestamps only, not reference errors, posterior weights,
signal quality, or candidate labels. Persist and hash the manifest before fits.

Compare the three original contiguous-window sets with the three time-balanced
sets per dataset. Both arms use the unchanged q020 candidate/trend mixture,
observations, per-track masks, RF conventions, and timing bounds. For every set,
run the same three fixed starts E=-2,0,2km,N=0 and all recording times zero.
Select highest training score among qualified fits; never initialize from
known geographic error or an old fitted position. No group-specific corrections.

Use inherited fit limits100 iterations/160 evaluations, no boundary, optimizer
success, gradient<=0.01, and finite-difference gradient discrepancy<=0.02.
Per-set cap90seconds; maximum three CPU workers. Retain failures and timeouts.
Score original interleaved held observations at each set's training optimum.
Report dataset-wide held totals over the same24 scans, geographic medians,
sub-km counts, individual results, and elapsed start-to-start spans.

This deliberately spends more elapsed time per eight-scan estimate, with the
same number of scans and exactly the same overall corpus. Do not present it
as an equal-latency comparison, independent-site validation, or an optimal
geometry selection algorithm. Source references remain exposed and unsurveyed.
No new RF, production changes, or remote publication.

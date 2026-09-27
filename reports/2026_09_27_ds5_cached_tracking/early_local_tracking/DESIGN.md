# Bounded local timing before accepting a native proposal

The two-regression diagnostic identifies margin failures at rounded epochs.
Score center, center-1, and center+1 independently for each original positive
proposal. Keep original acquired and expected physical CFO fixed. Retain only
points passing the original margin/status/support gates; choose highest margin,
center then earlier sample on ties. Never score negative timing. Guided local
search remains unfitted and does not train timing/CFO drift. Preserve the
nuisance-aware discovery veto and existing cache invalidation rules.

This is a separate candidate. Re-run all 42 original controls and 24 swapped/
original negative executions before development replay. Count every added point
call; all are included in complete-call timing. This search increases trials,
so passing the predecessor's controls is not assumed. CPU0, numerical threads=1,
120-second control bound. No holdout opened. Wider acquisition coverage remains
required even if the two development regressions recover.

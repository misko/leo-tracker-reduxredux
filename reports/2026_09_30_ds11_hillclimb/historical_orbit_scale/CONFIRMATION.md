# Frozen independent date/object confirmation

Use the day immediately after the last historical forecast center (2026-09-28
00:00 UTC). Keep the original cutoff: both request and local file-write evidence
must precede earliest DS11 minus24hours. Select newest eligible snapshot from
each original provider at center-24h, center and center+24h, then newest element
per NORAD under the original epoch/request/digest rule. The global availability
cutoff can truncate the last reference horizon; report actual timestamps and do
not describe it as a guaranteed24hour update. These remain archive reference
proxies, not independently attested orbit truth.

Exclude every NORAD appearing anywhere in the original12 propagated windows,
including unused cases. From remaining STARLINK non-debris objects common to
the three catalogues select up to256 by the original SHA256(NORAD) ordering.
Require strict old<current<later epoch advancement, reporting all exclusions.
Use the same three-point propagation grid and exact center state. Never inspect
DS11 residuals or coordinates. Score the already sealed constant and age models
without refitting. Require at least50 eligible objects, positive mean and median
log-score gain, and strictly more than55% wins. Keep every eligible case. A
failed gate ends this candidate uncertainty model; no horizon, cohort or age
threshold is tuned. Any pass still is not a DS11 position improvement, and the
isotropic position proxy is not a calibrated Doppler covariance.

# Training-only opportunity features for every fitted track

Use all 258 audited scans and the unchanged 25 donor groups/nine target eight-scan
groups. Include exactly the fitted track identities in their frozen posterior
exports; report other exported tracks separately. No residual or position score
is used to select membership or features.

Join by session, exact receiver and exact RF without rounding. Reproduce the
existing whole-visit training partition (seed2026092711, SHA256 first32 modulo10<6).
Verify each observation's stored mask and visit against the opportunity records.
Every track visit must have an analyzed matching RX/RF probe with a passing
candidate; this is consistency, not independent satellite identification.

For each track's RX/RF lane, count all analyzed training probes in its scan,
including empty ones. Feature p=(empty+0.5)/(probes+1), logit(p). A scan's held
probes never enter these features. Keep missing joins explicit and stop rather
than substitute a different RF or drop tracks. Smoothing is fixed before results.

Three prelaunch tests: exact receiver/RF separation; held-out outcome isolation;
missing support and partition inconsistency rejection. Independently reconstruct
hash partitions, counts and every feature after export. One child, timeout90s,
AS4GiB/BLAS1/nice19. This is a prerequisite audit, not fitting or evidence of
predictive improvement. No IQ/RF/propagation/provider/production changes.

# Equal-scouting-budget control

Freeze before execution: reuse the exact 12-scan chronological prefixes and later target sets from `2026_09_29_prefix_score_selection/manifest.json`. Select eight chronological ranks `[0,2,3,5,6,8,9,11]`, obtained by rounding eight equally spaced ranks across 0–11. This is rank spacing, not equal elapsed time. No frequency, fit outcome, target score or reference coordinate selects membership.

Compare against the existing score-selected eight, full prefix12 and first prefix8 at the same decision cutoff. Prefixes are sparse subsets of the original 24-scan pools. Keep q=0.2, six starts, original bounds, training-only start selection, optimizer/gradient audits and target timing integration unchanged. Report all failures. Each dataset subprocess has a 300-second cap, BLAS1; no retries and no new RF.

Primary comparison: summed later-target log score, rank-spaced eight minus score-selected eight, separately per dataset. Also report individual target differences and reference distances. This is exploratory transfer on previously exposed data, not a blind validation or an independent accuracy certificate. Do not choose a policy by pooling away dataset failures.

An exposure audit must match full-manifest membership to prior complete-dataset fit plans and verify selected result dimensions and qualified execution. Prior full-dataset fits already imply exposure even where a scan is absent from recent 24-scan subsets.

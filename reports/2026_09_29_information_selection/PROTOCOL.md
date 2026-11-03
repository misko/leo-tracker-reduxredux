# Training-only information selection from 24-scan pools

For each DS7/DS8/DS9 pool, use its existing qualified N24 training fit as the
scouting point. Every track contributes centered Doppler derivatives in east,
north and scan timing, weighted by its training candidate and signal mixture
probabilities times 5/70000. Profile the per-scan timing to obtain a 2x2
geographic information proxy. This is not a calibrated covariance or observed
mixture Hessian. All 24 scans are needed to scout; this is not acquisition of
only eight scans.

Greedily select eight scans maximizing log determinant of summed information,
with ridge 1e-9 times half the full pool trace. Resolve ties by pool order.
Recompute with half derivative steps and require identical selected sets and
relative matrix discrepancy below 1e-5. No held data or reference selection.

Fit the selected eight using original q020, three cold E starts (-2,0,+2 km)
and three matching training-only timing-grid starts. Select highest qualified
training score using existing optimizer and gradient gates. Evaluate the five
frozen outside-pool targets using original q020 shared-scan timing integration.
Compare to each existing balanced N8 fit, their equal per-scan mixture, and N24.
None of these already examined targets is a blind new validation dataset.

Three workers capped at 300 seconds. No RF, production changes or publication.

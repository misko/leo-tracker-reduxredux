# Wide-start audit of existing N24 solutions

For each DS7/DS8/DS9 N24 source pool, run the original q020 optimizer from
four fixed corners: east/north (−8,−8), (−8,+8), (+8,−8), (+8,+8) km relative
to the configured center. At each corner initialize each scan's timing from
its training-only 41-node score grid. No reference or held-score selection.
Keep original ±12-km / ±5-s bounds and optimizer/gradient qualification gates.

Compare all endpoints to the existing qualified six-start N24 solution by
training score and physical-coordinate displacement. Preserve exceptions and
unqualified endpoints without retry. Save each corner result as it finishes.
This tests initialization sensitivity within an existing site-conditioned
candidate bank and bounded domain; it does not remove the geographic prior
or certify catalogue support for a global search. No new geographic accuracy
claim follows simply from recovering the existing solution.

Three dataset workers capped at 300 seconds. No target evaluation, new RF,
production edits or publication in this audit. If a better qualified training
solution appears, record it for a separate predictive follow-up.

# Joint fitting beats separate fitting locally, but not the cached frequencies

All six common-probe frequency comparisons complete, with both joint starts
qualified in every case. Joint refinement beats separate refinement on five
of six held-sample comparisons, with median NMSE gain+0.000561. However, it
beats the cached acquisition frequencies on only two of six; mean and median
gains against cached are negative. **These single-frame refinements should
not replace the cached Doppler measurements in positioning.**

| Pair | Cached held NMSE | Separate-frequency held NMSE | Joint-frequency held NMSE |
|---|---:|---:|---:|
|0|0.925256|0.932749|0.931920|
|1|0.954800|0.951561|0.951494|
|2|0.896152|0.897960|0.897069|
|3|0.905734|0.910637|0.910344|
|4|1.002421|0.992144|0.997509|
|5|0.938151|0.942284|0.940423|

Lower is better. All arms reconstruct both candidates with jointly fitted
complex gains on identical fitting samples and evaluate identical held samples.
Only frequency selection differs. Both negative cases from the preceding
coexistence test remain. All epochs and sample masks are unchanged.

| Joint comparison | Wins /6 | Mean paired NMSE gain | Median paired gain |
|---|---:|---:|---:|
|Versus separate refinement|5|−0.000237|+0.000561|
|Versus cached acquisition|2|−0.001041|−0.001595|

The predeclared5/6-win, positive-median, complete-coverage gate against separate
refinement passes. That limited gate permits another measurement test; it is
not evidence of improvement over the actual incumbent. The mean comparison
also worsens because one negative case outweighs the small gains. No case,
frequency bound, or qualification threshold is changed after evaluation, and
no position fit follows.

Joint native-frequency residual estimates in candidateA/B order are:
96.88/183.89Hz,1074.91/38.92Hz,−58.75/−61.89Hz,58.96/2.31Hz,
727.61/27.20Hz, and0.46/−45.56Hz. An interior numerically qualified estimate
is not a calibrated frequency measurement. These fits use only one frame,
whereas the cached GLRT measurement summarizes a longer probe. Different
statistical support and model error can affect this comparison.

The next bounded experiment should keep these six probes and compare cached,
separate and joint frequency estimates while pooling eight frames with
independent frame/carrier gains. It should require improvement against cached
as well as separate predictions before considering broader measurement work.
This tests whether additional support reduces refinement variance; it does
not assume that variance caused the present loss or promise a position gain.

Two component tests verify analytic variable-projection derivatives, recovery
of two injected frequency offsets, and held isolation. Twelve joint endpoints
pass optimizer/interior/gradient/finite-difference checks. Highest training
likelihood selects each endpoint and its selection is saved before held scoring.
Independent QR gain solves replay all18 held scores within2.23e-16 and verify
source bindings, excerpt digests and training-score selections. The single
worker exits0 in1.01seconds, below its120second cap. No retries, new IQ, RF,
orbit updates, geographic scoring or production changes occur.

Evidence: [protocol](PROTOCOL.md), [outcome](outcome.json),
[independent verification](verification.json), and per-case starts/selections
in `rows/`. Plan SHA256:
`888675b7887cf140c08c2416b21aaf971956c2350be8781b380b7bd2b37a43da`.

# B fixed union:035 start preservation helps;029 remains a failure

All24 original-solver calls completed and sealed before reference evaluation.
Under a fixed union bank, adding the six original before starts recovers a much
better035 basin.029 does not benefit. Neither case is sub-kilometer, and this
experiment does not justify blanket promotion of the union policy.

| Case | Original before full, km | Original after full, km | Union after-six, km | Union all-twelve, km | All-twelve winner |
|---|---:|---:|---:|---:|---|
|035|6.289808|96.957197|185.298712|6.712071|Before start4|
|029|151.054387|63.286893|77.256367|77.256367|After start2|

All selections use stationary training objective alone. The physical before
initializers retain their original proposal centers/corrections/timings; no
original-bank endpoint was reused as a union outcome. Within the common bank,
the after-six fits are shared with the all-twelve selector rather than repeated.

| Case/selector | Union candidates | Accepted starts | Training objective | Training NLL | Full physical KKT |
|---|---:|---:|---:|---:|---:|
|035 after-six|55|5/6|39173.517282|38663.044386|.000556410|
|035 all-twelve|55|10/12|35702.056804|35313.207147|.000482388|
|029 after-six|44|6/6|34414.016094|34115.928833|.000561862|
|029 all-twelve|44|12/12|34414.016094|34115.928833|.000561862|

The035 all-twelve objective improves3471.460478 over its union after-six
incumbent, including3349.837239 lower training NLL. That is a within-bank
comparison. Original-bank objectives are not ranked against these values because
changing candidate count changes detector prior/density normalization.
Frequency-fit improvement and configured position accuracy are separate results.
No held-frequency observations were prepared.

Stationarity attrition matters.035 after start0 returned objective38622.574892,
lower than the accepted after-six winner, but KKT.002311329 excludes it despite
solver success true.035 before start3 returned36141.173760 with KKT4.291613095,
also solver success true, and is excluded. The accepted all-twelve winner beats
both rejected objective values. These failures remain unchanged; no polish,
continuation or retry was performed. Thus the after-six error185.298712 cannot
be attributed solely to the bank or proposal locations.

The four six-call units completed in30.413,31.746,19.133 and19.335 seconds;
single-worker wave total100.644 seconds including preparation. Each call retained
the original20-second/600-iteration fitted-c solver and its original25 km disk;
whole-unit180/195/200 bounds and30-second remaining-time admission were enforced.
Twelve-start selection explicitly has twice the start budget of six-start
selection:24 new calls across the pair. Upstream original pipelines and zero-fit
qualification costs are separate. No additional clock, likelihood, phase or
candidate-selection model was introduced.

This supports preserving old starts on035 under the tested union bank. It does
not isolate bank versus start effects completely, fix029, or establish a matched
full-versus-half improvement: union half-view fits are absent. Existing paired
baseline histogram rows remain unchanged. The next diagnostic will compare
accepted runner gaps and per-band likelihood/mass at training-selected union
states without new fits or reference selection.

Source control commits `720da8837`/`1d7cb8657`; five owned tests and Ruff passed.
Postseal evaluator `6c68fc4ef` has four tests rejecting missing seals, changed
selectors and inconsistent return flags. Private bulk namespace
`/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-b-union-control-v1`.
Terminal SHA256
`3bfa7914fb94cc5c376bdde4d7314ea8005f6a7361856a49462d3b87869c1e68`;
seal SHA256 `e64e61b460a606c2132197cbf95a8abe189e8b11dd1f5c2b01209c4671ea1165`;
postseal comparison SHA256
`72b39067fff26a6fe1027abc0ee39a0da3ea3dcbec1de8507e2d3e7d9a4f416d`.

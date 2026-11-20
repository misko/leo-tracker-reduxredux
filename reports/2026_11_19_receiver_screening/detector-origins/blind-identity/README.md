# Cross-track clocks for blind orbit identity

The cross-track clock receiver **published 0/6 matched rooftop fixes**. A control using each arc’s own clock published **2/6**, both within 5 km in both calibration arms. Both share raw observations, a causal orbit shortlist, the standalone position fit, and the same publication gates. The cross-track method took **1.66 s median worker CPU**, compared with **3.61 s** for the earlier independent-arcs receiver. That receiver also withheld all six matched offers in this panel. The cheaper shortlist is useful for runtime. The added clock vote worsened the identity-to-position result in this form. [Matched positions and RF scores](scores.csv) · [Standard atlas figures](figures.json)

| Six containing roof offers | Cross-track clock | Per-arc clock | Independent arcs |
| --- | ---: | ---: | ---: |
| Published, each arm | 0/6 | 2/6 | 0/6 |
| Published within 5 km, each arm | 0/6 | 2/6 | 0/6 |
| Median forced error, zero / fitted c | 19.47 / 19.45 km | 8.17 / 6.19 km | 7.41 / 8.26 km |
| Median conditional RF RMS, zero / fitted c | 1,829 / 1,604 Hz | 1,062 / 1,189 Hz | 752 / 753 Hz |
| Median held RF RMS, zero / fitted c | 427 / 444 Hz | 279 / 278 Hz | 345 / 364 Hz |
| Median end-to-end elapsed | 3.95 s | 3.86 s | 4.80 s |
| Median worker CPU | 1.66 s | 1.66 s | 3.61 s |

The two published per-arc results were DS26-0303 at 4.92/4.00 km and DS29-0247 at 3.92/4.12 km. On DS26-0303 the conditional training residual remained about 9.8 kHz even though the held decoder found low-residual paths. This exposes how a sparse held decoder can admit a useful subset while much of the original selected support fits poorly. Cross-track held medians have five measurements because DS29-0082 returned zero held peaks. The other columns have six. Original v5 published all six same-offer references. [Sealed endpoints](positions.jsonl.gz)

## Where the shared clock loses

The two selectors link peaks in measured time without orbital information. Each starts identity from the same seven phase seeds, the same arc head, and at most eight causal satellites with three phase hypotheses each. The proposed selector fixes a receiver/band clock inferred only from other arcs. Its vote needs at least two distinct provisional orbits, then a robust update uses their head points. The target arc’s head nominees are scored on that arc’s later points. The control predicts the same tail using its own head’s clock. Final model fitting and both calibration arms use the unchanged standalone physical estimator. The c column is absent in the c0 arm. An outer raw holdout was excluded from linking and inference. [Prospective protocol](PROTOCOL.md) · [Identity and phase selections](identity-traces.jsonl.gz)

Of the 74 roof arcs accepted by both selectors, **49 received different orbit IDs**. The clock method kept more arcs than the control in both diagnostics yet moved farther away. On DS26-0197, for example, it added five accepted arcs and reduced conditional RF from 4.82 to 1.60 kHz in c0, while forced error increased from 8.94 to 25.84 km. On DS29-0082 the method admitted four arcs and found no held peaks. In the six roof tests it was at the fitted c bound once, and in the two simulated containing tests it reached the bound in both. The estimated clock is conditional on other arcs’ unverified identity and phase. These observations show that its consistency vote can change assignments substantially and still fail to preserve geometry. [Common accepted arcs and disagreements](track-identity-overlap.json)

## Wrong offers and geographic controls

All three methods withheld on both authentic omitted roof offers. Cross-track forced errors were 46.06–64.01 km. The two simulated sites were drawn from a previously sealed geographic transfer panel with measured archive CFO disturbances. Each supplied its containing offer and a near-missing offer. Both selectors withheld all four. The cross-track containing forced median was 13.79 km in both arms, compared with 7.16/7.69 km for the local clock. The within-lane real peak-list shuffle yielded zero linked arcs and no estimate. The simulated site data preserve the earlier panel’s simplified observation contract and serve as additional geography controls. The independent public field receiver’s beacon data use a different measurement contract. [Omitted roof queries](omitted-queries.json) · [Simulated queries](simulated-queries.json) · [Shuffle result](shuffle-position.jsonl.gz) · [Field inventory](../../physical/README.md)

## Compute boundary

There were 14–49 linked anonymous arcs per matched capture, 244–857 retained orbit/phase hypotheses, and 882–1,151 regional causal orbit IDs. Median worker stages were 0.24 s for parsing and linking, 0.85 s for propagation and proposals, 0.013 s for cross-track selection, 0.15 s for the standalone fit, and 0.37 s for held validation. The shortlist comparisons operate on a few measured arc points. The earlier independent-arcs baseline used up to 4,608 full time-ordered lane/orbit/phase decodes. This counts different numerical operations at each boundary. The four matched reserves had freshly timed independent-arcs runs. Their medians were 3.41 s worker CPU and 4.55 s elapsed, compared with 1.70 s and 3.95 s for this receiver. Two inherited diagnostic timings came from an earlier batch.

The new source is 334 Python lines. It calls the frozen 310-line standalone estimator, the 409-line linker and the 473-line Python plus 82-line C path module. Only held validation calls the full path decoder. File counts include unused entry points and exclude common geometry and numerical libraries. Median matched RSS was 187 MiB. The batch sealed 29 fresh jobs in 54.3 seconds on cores 6/7 at nice 10. The developmental run used a coarse clock grid. The final protocol added continuous clock refinement on peer heads before the reserve lock and before geographic scoring. The measured failures favor stronger physical identity checks before other arcs determine the clock. [Frozen source, roster and input hashes](blind-plan.json) · [Prediction seal](prediction-lock.json)

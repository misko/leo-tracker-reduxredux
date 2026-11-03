# Fixed-state population point control, before a coherent recovery model

The preceding turn made progress by publishing a source-verified15-window progress chart and developing the new control's components. Original96/693, highest experimental462/693 and latest complete joint-band420/693 remain unchanged. The15-window generalization goal remains active. This protocol fixes the point control before new metadata predictions or held scores; no fit, reference-based selection or production change is authorized.

## Question and limits fixed before outcomes

Does a normalized background over800 metadata-eligible but TRAIN-unselected satellites improve predictive density at the same immutable TRAIN-trained state? This is a necessary availability-only control, not a recovery model. Retain both original legacy fitted-c and conditional-c0 endpoints from iteration9. Their coordinates, calibration, clocks, selected45 identities, q and timing remain unchanged. Thus position cannot improve in this experiment. The c0 discovery/upstream state remains conditional on fitted-c processing.

Allocate the same Q=1.6 budget: selected q becomes(1-eta)q, and every unsupported object receives eta*Q/800. Evaluate only eta=0 and .10, with no tuning. Preserve lambda=.5, measurement sigma125Hz, relative timing scale2s, actual RF, compact horizon1e-5 and original candidate ordering. Unsupported prediction is linear in its relative timing delta, with mean at the retained common shift and variance125²+4*(dCFO/dtau)². This integrates an independent per-point Gaussian timing working model; visibility is frozen in delta. It does not integrate globally fixed satellite errors or the full nonlinear orbit model. Report the separate exact-orbit linearization/visibility diagnostic rather than conceal approximation failures.

Use old odds q*w/(1-q*w), one normalized density per mark, and a normalized wrapped Gaussian for every component. Population mass does not increase with catalogue size. eta=0 must exactly replay the old selected-bank PDF/classification and copied physical predictions; the845-bank interpolation must not replace selected45 predictions.

### Analytic classification ceiling

For eta=.10 and800 objects, each unsupported q=.0002. Its maximum odds times wrapped-Gaussian peak at sigma>=125 is about6.384e-7, below lambda/ALIAS=2.2e-6. No unsupported object can individually beat clutter. Every selected odds decreases, so all new associations must be a subset of the eta=0 associations. This is a mathematical constraint under the unchanged best-state-versus-clutter rule, not a hypothesis to optimize away. Assert it during evaluation; a violation is a bug. Do not change eta or the threshold after observing this ceiling or later scores. Shared evidence across observations is required for the next recovery model.

## Frozen inputs and barriers

Reuse both iteration9 legacy outcomes and blank-CFO prediction seals, the existing response-blind845-ID bank, and the causal TRAIN provenance. Original row metadata comes only from those frozen blank prediction archives. Require matching original recording, UTC origin, prior/chart, TLE provider/digest/collection/payload, metadata digest, unique845/45/800 partition and all3988 ordered observation IDs. Preserve2073 TRAIN,1909 held and6 boundary rows. The requested held subset has80 rows across windows007/008/009; the other555 requested observations in the15-window dataset remain untested here.

The metadata producer may make exactly two full orbit/derivative calls and two elevation/horizon calls, one per RF arm, under60s TERM/65s KILL. It performs no propagation, source preparation, localization objective or fit. Root reviews its source and owned tests before freeze/run. Both new prediction archives must seal before any held marks or requested-window metrics enter evaluation.

The separate diagnostic uses at most two TRAIN metadata rows per RX/channel/RF lane chosen by fixed hash, at most32 total, all800 unsupported objects and nine fixed relative shifts(-6,-4,-2,-1,0,1,2,4,6)s. Both RF arms use the same rows. Its maximum is18 orbit and18 elevation calls under60s TERM/65s KILL, with no measured CFO, propagation, objectives or fits. It reports all exact-minus-linear frequency errors and visibility changes, without selecting cases or changing model parameters.

## Evaluation and controls

After generic density tests and both prediction seals pass, evaluate four fixed cases: two RF arms times eta0/.10. Report same-mark proper NLL by TRAIN/held/boundary/full and the fixed80-row requested held subset, seven excluded20s blocks, original-classifier new/lost/retained counts, paired retained residual RMS, selected-ID changes and unsupported posterior mass. Counts are model assignments, not true emitter labels. eta0 must replay the saved legacy control; positions and timing histograms remain unchanged by construction.

Prespecify32 held-CFO permutations with seed345421, independently within each RX/channel/actual-RF lane. Use identical index permutations for both RF arms and eta settings. Keep times, visibility, predictions, RF, calibrations and parameters fixed; no regrouping or refitting. Recompute each proper held density and report observed eta.10-minus-eta0 NLL alongside all32 null differences. This is a conditional diagnostic, not a null-refitted significance test. Its evaluation cap is120s TERM/125s KILL. Preserve all cases/failures without retries or favorable permutation selection.

No positive point-score result alone authorizes a fit, a coherent-model claim, all-five expansion, geographic improvement, production/main push or completion of the15-window goal. Negative or positive results both inform the separately qualified coherence model. Candidate/RF eligibility cannot use selected window membership, manual satellites, configured coordinates or held scores.

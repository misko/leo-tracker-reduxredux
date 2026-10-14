# Prospective C per-start disk releases: no selected improvement

Both approved releases completed and passed independent stationarity checks.
Neither beat its case's original training incumbent, so the training selector
retains all three original selections. The operation completed in 50.123 seconds
including preparation, exactly two new fitted-c optimizer calls, with no retries.

| Case | Trigger objective before→after | Original incumbent | Remaining objective gap | Released full KKT | Selected endpoint |
|---|---:|---:|---:|---:|---|
| Before029 | No qualifying release | 38420.441200 | — | — | Original start1 |
| Before037 | 31741.317921→31721.327990 | 27741.020228 | +3980.307762 | .000409717 | Original start3 |
| After029 | 37493.647493→35397.411750 | 32862.774268 | +2534.637482 | .000935261 | Original start4 |

All 18 original endpoint eligibility rows were retained. Before037 release used
7.888 seconds/239 evaluations; after029 used 20.051 seconds/1174 evaluations,
including the original fitter's final checks. Both had unchanged 20-second/600-
iteration optimizer caps. The latter reports solver success false but converged
true, with independently replayed full KKT .000935261 under its new disk; the
original fitter accepts this stationary endpoint. Its new disk is active, and the
one-release policy stops there. No further release or retry was performed.

Before037 released training NLL is 31280.551635 versus incumbent 27295.406938;
after029 released training NLL is 35144.389243 versus incumbent 32623.913772.
The likelihood score preserves the losing ranking in both cases. These scores
are training frequency-fit evidence; no held-frequency data were prepared.

Only after both calls, all eligibility rows and training selections were sealed
did a separate evaluator join the configured reference:

| Case | Original/selected configured error, km | Losing release error, km |
|---|---:|---:|
| Before029 | 268.918456 | Unavailable; no trigger |
| Before037 | 334.350833 | 319.699822 |
| After029 | 100.198781 | 18.300354 |

The closer after029 release cannot be promoted by reference error: its objective
is still 2534.637482 worse. These two continuations show that the prespecified
rule did not improve the selected solution in these cases. They do not establish
failure of every global search mode or prove a likelihood-model cause. In
particular, before029's sole stationary original was interior, so its error did
not qualify for this intervention. The sub-kilometer and full-versus-both-halves
targets remain unmet.

Scientific source/protocol commit `ec8f2f719`; 978 bindings were frozen before
preparation. Local namespace `model-c-adaptive-disk-next-control-v1`; terminal
SHA256 `9527fc5e58e0c6fe19e244ae0ba59010a1c1ec347888767357c1945ce788148b`,
seal SHA256 `a8e64ff72b3c376584229327a35b674f142f08faba5b5df9c087a422ca93316a`.
The separate postseal evaluator is committed as `91992566b`; its three tests
reject missing calls, changed return flags and changed selectors even with new
file hashes. Original scientific sources and baseline histogram rows are intact.

In parallel, all 34 before and all 34 after prerequisite chains now have complete
six-proposals scientific terminals. Final three before parents are canonical
`initialization-v1/DS21-{083,085,087}/six-proposals`; all parents were handed to
the model worker. This is prerequisite completion, not completion of the remaining
model matrices or achievement of the accuracy target.

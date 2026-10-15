# A053 matched hard control: cross-view state access matters

All nine unchanged-hard-model calls pass strict acceptance. With exactly the same three complete common starts as the smooth experiment, the hard model selects **1.148233 km full, 1.709737 km low and 0.299857 km high**. The new high result demonstrates that adding the other band's complete state can repair a half-view basin without smoothing. Full remains above 1 km and worse than the best half.

| Density / fixed width | Full km | Conditional low km | Conditional high km | Full worse than both? |
| --- | ---: | ---: | ---: | --- |
| Hard, matched three states | 1.148233 | 1.709737 | 0.299857 | no |
| Smooth 5e−6 | 1.148252 | 0.630473 | 1.444907 | no |
| Smooth 1e−5 | 1.148260 | 0.656590 | 0.701089 | yes |
| Smooth 2e−5 | 1.148273 | 0.860641 | 0.928054 | yes |

Every row uses three starts per view, the same bank, frame, priors, frozen learned receiver shifts and 50 km disk, with matched 20-second/600-actual-objective call caps. All smooth widths are reported; none is selected by configured error. Smoothing improves the low-view estimate here, worsens the high-view estimate, and leaves full unchanged. These finite local-search outcomes do not establish a generally superior density or a cohort-wide repair.

The hard selectors are:

| View | Complete initializer | J | Frequency NLL | Prior | Strict KKT |
| --- | --- | ---: | ---: | ---: | ---: |
| Full | Full | 19299.950146 | 19020.777883 | 279.172262 | 0.000339104 |
| Low | Full | 12867.902076 | 12601.690130 | 266.211946 | 0.000248016 |
| High | Low | 6117.295408 | 5970.490789 | 146.804619 | 0.000104076 |

The previous hard high incumbent was 1.444907 km, J 6142.299734, NLL 5966.148355 and prior 176.151379. Its new 0.299857 km successor has **worse frequency NLL by 4.342435**, but prior improves by 29.346760 and J improves by 25.004325. The widest smooth high model has much better NLL 5801.634018 yet worse configured distance 0.928054 km. Frequency fit, regularization and position must therefore remain separate outcomes. The new low selector has lower J than its retained 1.659857 km incumbent but slightly worse position 1.709737 km; it remains selected by training J.

All three original own-view incumbents and all nine model/state starts were independently qualified in 12 objective evaluations, zero fits and 7.741 s. Seeds, solver options and geometry match their frozen smooth counterparts exactly; tests additionally check masks, fixed baselines and precision matrices across every width. Every eligible original source state remains in the training pool. There were no optimizer retries, unavailable calls or acceptance relaxations.

The nine new fits used 2421 actual objective evaluations total; maximum numerical duration was 3.133 s and maximum evaluation count 595. Six single-thread workers completed the finite wave in 22.266 s. Nine independent returned-endpoint objective audits are separate. Each view's selector minimizes its own accepted training J. All outcomes and selectors sealed before reference evaluation, which used zero objectives and 6.661 s. Half views remain conditional full-derived views, not independent half discovery. Added total search cost is explicit; historical cumulative costs are not equalized.

Source `c6a2ffcef`; five component tests and Ruff passed, including a fitter-dispatch test that verifies the hard objective and rejects the soft model. Namespace `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-a053-hard-visibility-control-v1`; wave `model-a053-hard-control-wave-v1`. Global scientific seal `a0c9ddf1be63a00ead0135f48e6b64aff8798f2f680e3436206c0262232cf5b2`; evaluation SHA256 `cbe53d94d4d5a977270a9ca7ac5bda982fa2fcbcf2f2bbc40267f4238a621e28`. The paired smooth experiment remains unchanged and separately sealed. No held observations, reference-derived seeds or new RF collection were used.

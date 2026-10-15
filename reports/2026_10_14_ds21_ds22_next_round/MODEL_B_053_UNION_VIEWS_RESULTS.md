# B053 union matched views

The fixed-union59 complete-state control remains far from the reference: full **50.504614 km**, low **50.610269 km**, high **49.232165 km**. Full improves low by 0.105655 km but loses to high by 1.272449 km. This does not meet the full-versus-both-halves or subkilometer targets.

All three original-solver calls used the same selected before/start2 complete physical, timing and nuisance state, unchanged full frame/bank/priors and original 25 km disk. Only the observation mask changed. Each call retained the original 20 s/600 limits; this is extra conditional saved-state work, not an equal end-to-end discovery budget. The fitted RF coefficient remained enabled. Full-derived discovery, frame and initialization are shared by the halves.

| View | Objective | NLL | Prior | Independent KKT | Error km |
|---|---:|---:|---:|---:|---:|
| Full | 24974.287689 | 24611.481373 | 362.806316 | .000429845 | 50.504614 |
| CH1–4 | 16892.725964 | 16546.520965 | 346.205000 | .000098383 | 50.610269 |
| CH5–8 | 7969.826253 | 7715.031789 | 254.794464 | .000089609 | 49.232165 |

All fits passed strict independent stationarity; no selected endpoint exceeded its own-mask feasible initializer objective. Their whole-unit times were 1.408/4.134/2.515 s. The three-objective zero-fit qualification passed exact original full score, additive band NLL/gradient, complete state, priors, posterior/residual and domain checks. The original fitter's recorded timing-only inward initialization was bounded at 1.1 ns, with no geographic or nuisance clipping.

All three outcomes were sealed before the reference comparison. No original held or locked observations were read. Source commit `7fb0b839d`; runtime `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-b-053-union-views-v1`; qualification SHA256 `d2943fc1c3cce2ec8a4198f1f88b106edca7529d125f31a3e47143d822b42755`; scientific seal `92a472fb2446337ebd1b7d551aa8427374961c3d9271c36302a1362f87f1b0f0`; postseal evaluation `9c325554e15a76147f2a7715d004c6c8c4ccb6006e47a3c3e235f933a29d88ec`.

Preserving old starts on a common union previously improved the selected full endpoint from the after-only union result 248.346140 km to 50.504614 km. These matched views show the remaining error is shared across bands at this selected basin. They do not establish global search completeness or prove a likelihood defect.

# C059: strict numerical repair admits a better basin, but geography remains poor

The two-method control repaired the rejected clock-family coarse19 endpoint without changing its model, bank, priors, domain, active timing face or stationarity threshold. Tangent Newton passed the original independent KKT audit; an ordinary SLSQP repeat still failed. The newly eligible training winner changes configured-reference distance from **311.714 to 272.286 km**, still far from the accuracy goal. DS22 reference continuity remains unconfirmed.

| Method | Actual objectives, including audit | Numerical wall time | Final objective | Original KKT | Strictly eligible |
|---|---:|---:|---:|---:|---|
| Saved rejected source | Historical | Historical | 46116.27539975415 | 0.008057196 | No |
| Unchanged SLSQP repeat | 24 | 1.412 s | 46116.27539975419 | 0.008017778 | No |
| Active-tangent Newton | 407 | 23.150 s | 46116.27539975272 | 0.000000263146 | Yes |

Each method also used one separately counted source-qualification objective. Total fresh work was 431 numerical objectives plus two qualification objectives, exactly two numerical calls, and no retries. Both calls remained within the prespecified 60-second / 600-actual-objective limit, including independent audit. Preparation and authority validation were additional: the two-worker wave completed in 72.958 seconds. All outcomes sealed before the configured-reference join. SLSQP reported success after two iterations, illustrating why solver success alone remains insufficient.

## What the repair established

The supplied raw vector and nuisance state replayed exactly, including its active +20-second satellite timing bound. The optimizer constructor's inward margin was recorded but not applied. A relative coordinate chart preserved the physical source state bit for bit. No reference, held data, new candidates, receiver lifts, calibration flexibility or larger search disk entered either numerical method.

The 101-dimensional affine-feasible tangent Hessians used analytic-gradient central differences at steps 1e-5 and 5e-6. Their minimum eigenvalues were 0.104653482 and 0.104653431; maxima were 510344.899 and 510344.901. Relative matrix change was 1.19e-7 and relative asymmetry was below 1.41e-7. Both passed the declared positive-definite/stability gates without regularization. These are local active-face certificates, not evidence of a global optimum.

One full feasible Newton step reduced KKT to 2.63e-7. Predicted objective decrease was 1.546e-9, approximately 212 objective ULPs; observed decrease was 1.433e-9. The position moved only **8.30e-7 km (0.83 mm)** from the saved rejected endpoint. The 39.43-km change in the selected result therefore comes from making an already-discovered basin eligible, not from Newton moving that distance. The accepted endpoint's NLL is 45544.247147858; the tiny numerical correction changed NLL and prior in opposite directions while barely changing their sum.

## Training selection and limits

| Eligible clock-family candidate | Training objective | NLL | Configured-reference distance |
|---|---:|---:|---:|
| Original 48-call pilot incumbent | 47191.836555059 | 46698.856988364 | 311.714228 km |
| Repaired coarse19 endpoint | 46116.275399753 | 45544.247147858 | 272.286061 km |

The original incumbent remained eligible and the training selector chose the repaired endpoint by objective alone. The position change is a 12.65% reduction against the configured station, not a claim that the model is adequate. Original 48-call outcomes and the failed fresh SLSQP control remain intact. The projected no-clock family is a different model and is not mixed into this selector. Matched halves on this 75-satellite union have not been fitted, so historical halves cannot establish a same-model fusion improvement here. No held evaluation or cohort promotion was performed.

The result supports a finite-precision stopping mechanism at this endpoint. It does not establish that all other rejected endpoints are repairable, that the tangent remains positive-definite elsewhere, or that repairing convergence will resolve the remaining large geographic error. Further identical restarts are not warranted by this completed control.

## Reproduction and authority

- Prospective protocol: `DS22_C059_ACTIVE_REPAIR_PROTOCOL.md`; source and component tests: commit `fdd504f4b` (10 tests passed; Ruff clean). Evaluator: `05eb3010e` (post-seal ordering test passed; Ruff clean).
- Scientific namespace: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c059-active-endpoint-repair-v1`; wave: adjacent `ds22-c059-active-endpoint-repair-wave-v1`.
- Comparison: adjacent `ds22-c059-active-endpoint-repair-evaluation-v1/report.json`.
- Pair seal SHA256: `98b5f4f602581ee3956b62b1e9e6a1a37a9f36be1573067d73e12d489ce13348`.
- Terminal SHA256: `4090b0a7085dacdf14157a869c5600a7a6fed4b5ee05737fc83422004f7a4cca`.
- Newton result SHA256: `bb0ae4816a95c09d3ec33d6059c6eb96747dea9e7812392580b58d1addb80dc1`; SLSQP result: `d9c6c4baeb93aa069d5798c77f3d4c249787c94677e7781d855f07bf493703dc`.

The initial manifest command used an unavailable `python` executable and stopped before any scientific namespace or claim was created; switching the manifest generator to `python3` did not repeat any scientific work.

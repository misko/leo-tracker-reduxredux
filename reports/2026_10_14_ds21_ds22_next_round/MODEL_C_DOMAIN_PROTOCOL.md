# Current coverage C geographic domain diagnostic

Audit DS21-003 and DS21-023 from their completed `model-a-pipeline-coverage-{003,023}-cached-v2` parents, separately from the historical shared-six Model C experiments. Use each original all-band training selector and original winning 25 km disk. The direction is the displacement to that case's own high-band training selector, used only for fixed-state diagnostics; no reference or held observations enter preparation, directions or selection.

The `freeze` command validates all three original C unit receipts and original source/parent authority, copies the scientific source closure plus the new diagnostic sources, and pins the exact training cache, initialization, all C calls and global training terminal before any training cache load. The `run` command rechecks all bindings and original ports, loads the sealed training cache, and reconstructs the unchanged original neutral singleton C objective. It has a 180 s internal whole-slice cap including validation, cache preparation, model construction, diagnostics and final validation, with TERM at 195 s and KILL at 200 s. No optimizers, held preparation or reference joins occur. Unexpected failures retain a termination and forbid retry in the same namespace.

Replay the saved all-band objective/NLL at the exact saved endpoint. Report the original domain KKT and a separate KKT using a 25 km disk recentered on that same endpoint, actual radial and tangent derivatives, and the solver initializer's maximum difference from the saved endpoint. The original solver reserves 1e-9 inside timing faces during initialization; this does not invalidate an unchanged feasible saved endpoint.

Evaluate fixed-nuisance outward, inward and high-directed displacements of 1 m, 100 m and 1 km; additionally evaluate the actual high-directed displacement length. Evaluate signed 1 m, 100 m and 1 km arcs along the original disk's saved radius, preserving geographic feasibility when a straight tangent would leave an active disk at second order. All probes report original and recentered feasibility. Outside-original-disk probes are diagnostics, not accepted fits.

At every probe, use the original orbital prediction and the original singleton likelihood on restricted low/high observation rows, retaining full-frame calibration, satellite/branch/clutter mass and candidate slots. Require the two NLLs to sum to the replayed full NLL within 1e-7. Full prior penalty is reported once. No half-view nuisance transfer, bank alteration, clock alteration or new likelihood is introduced.

If the original disk blocks a material descent direction, the next prespecified control is two calls per case: original disk versus a disk recentered on the same all-band training winner, both with unchanged original model/nuisance/start and original 20 s / 600 iteration limits, fitted c only. C023 is an interior-domain control. Source endpoint authority and any tiny solver initializer margin must be explicit. Audit final KKT under each call's own domain, preserve failed/nonstationary outcomes without retry, and seal both cases' outcomes before any reference or held evaluation. Improved training likelihood alone is not localization improvement.

Reproducible command sequence per case, using the release scientific Python and single-thread numerical environment:

```text
python tools/ds21_model_c_domain_audit.py freeze --parent reports/2026_10_14_ds21_ds22_next_round/local/model-a-pipeline-coverage-003-cached-v2 --output reports/2026_10_14_ds21_ds22_next_round/local/model-c-domain-003-v1
timeout --signal=TERM --kill-after=5s 195s python tools/ds21_model_c_domain_audit.py run --output reports/2026_10_14_ds21_ds22_next_round/local/model-c-domain-003-v1
```

Repeat for 023 with its genuine parent and exclusive `model-c-domain-023-v1` namespace. Whole-case diagnostics occupy one of the six owned worker slots; remaining slots continue DS21 prerequisites.

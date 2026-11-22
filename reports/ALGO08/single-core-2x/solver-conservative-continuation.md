# Warm-starting fitted calibration in conservative refits

Starting fitted calibration from the converged fixed-zero fit reduced targeted DS30-0374 fit CPU by **0.41 s**. The complete saved-detection solve changed from **28.75 to 28.70 CPU s** in one pair. In the northern distant omission, the seeded fit stopped at an intermediate endpoint **2.86 km** from the cold result with a higher exact objective on the same observations. Both trials reproduced the final decisions, calibration endpoints and publication artifacts. [Receipts](measurements/solver-conservative-continuation.json.gz)

## Which fit changed

The stock conservative policy first runs paired exclusions and then, where eligible, tries salvage and runs the pair again. Both arms normally start at zero east and north with zero phase references on each mask. The previous exact reuse already skips a post-salvage pair when its inputs are unchanged. Initial branch discovery mainly uses the fixed-zero arm and has no same-stage donor for this experiment. The earlier collapsed solver reused a physical seed after discovery while removing several evidence stages. This trial preserves discovery, the complete conservative policy, family/history fitting, signed priors, cavity inference and standard publication. [Conservative policy](../../../src/leo/analysis/localization_v3/conservative_recovery.py) · [Existing exact reuse](solver-recovery-reuse.md) · [Collapsed experiment](solver-collapsed.md)

The immediate fitted-c arm uses the fixed-zero endpoint and clipped posterior phases when the scan, hypothesis, retained mask and budgets match. The donor must finish with the released small bounded position step and a final phase change of at most 0.01 s, the threshold used by the later predictive gate. The same criteria govern acceptance of the seeded fit. A failed seed or unsettled fit replays the cold fitted arm. Both arms retain five phase refreshes, up to 48 optimizer iterations per round, the original causal phase priors and the exact variational likelihood. Each recomputes its own noise precisions and nuisance posterior. The trial pins the release function and changes its initial phase input. [Continuation and endpoint audit](../../../tools/pipeline_eval/variants/algo08_conservative_continuation.py)

## Saved-input comparison

Both modes used digest-verified detections, the same supplied region and causal archive, and the existing exact causal, salvage and recovery reuse. DS30-0374 ran stock first. North far ran continued first. The independent objective audit rebuilt each conservative endpoint with its own complete model and phase reference. The objective, optimizer score and coordinate checks passed in both arms and all observed calls. The post-timing witness also scored different endpoints at a shared fixed phase reference. It consumed the other run's receipt only after inference. [Trial runner](solver_conservative_continuation_trial.py)

| Saved input | Fitted calls seeded | Fitted optimizer evaluations, stock → seeded | Fitted conservative fit CPU, stock → seeded | Complete solve and grid CPU, stock → seeded | Complete elapsed, stock → seeded |
|---|---:|---:|---:|---:|---:|
| DS30-0374 | 4 of 4 | 132 → 72 | 1.327 → 0.919 s | 28.753 → 28.699 s | 30.46 → 32.69 s |
| North far | 1 of 2 | 119 → 66 | 0.537 → 0.484 s | 11.004 → 10.982 s | 11.16 → 11.22 s |

The 0.408 s physical saving measures the targeted fitted calls. Elimination of all those calls would cap speedup at **1.05×** for that saved-input solve. The earlier retained-fit controls and audit work still run, and all five phase references are refreshed. The complete-solver clocks include independent endpoint audits in both modes. These are one matched timing pair per input on one low-priority pinned CPU. Rendering is timed separately, and acquisition is outside the trial.

DS30-0374 retained the same rejection decisions and final 2,905 owners. Its four intermediate fitted endpoints shifted by **1.20–3.04 m**. Evaluating each endpoint pair at each run's final phase reference favored the cold endpoint by at most **6.03 × 10⁻⁶** negative-twice-ELBO units. The final fixed-zero error and RF RMS were **1.855 km and 101.536 Hz**, and the fitted values were **1.935 km and 101.520 Hz**. The lower fitted RF RMS accompanied a larger horizontal error. All 179 grid locations, the selected optimizer paths and the eight rendered PNGs matched. [Physical reference](../location-audit/README.md)

On the northern omission's initial 266-point mask, the continued fit used **18** evaluations versus **71** cold. It reached the same west boundary at a north offset of −6.991 km, compared with −9.847 km cold. It met the small-step and phase conditions. At the continued phase reference, the cold coordinate scored **3179.080** against **3187.276** for the continued coordinate. This exact witness shows that the convergence checks admit a worse solution on the same model. The common gate rejected the same track in both runs. On the resulting 228-point mask the fixed-zero donor did not settle in five rounds, leaving the cold fit in place. Both pipelines offered cavity inference and ultimately kept the same 228 owners, 137 evaluated grid locations, path and all eight figures. Both still issued false fixes. Their errors were **52.455 km fixed-zero and 52.491 km fitted**, with RF RMS **37.951 and 37.533 Hz** respectively. The newer far-exterior veto is a separate publication experiment. [Published northern scores](../regional-release/blind-scores.csv) · [Far-exterior veto](regional-bound-guard.md)

The fit-level cost reduction and unchanged final publication on these two inputs provide limited support for a speed optimization. The large intermediate difference in the omitted region gives a concrete reason to keep the cold fit in the frozen candidate. These trials use one physical development site and one public simulated offer.

## Reproduce

The receipts identify the saved detection digests and supplied regions. Use the frozen DS30-0374 archive under `snapshot/inputs/DS30-0374/tle` and the published northern offer `e99fe65747d72e6b793584a9.json` with its original public archive. Fifteen component tests passed. [Component tests](../../../tests/pipeline_eval/test_algo08_conservative_continuation.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
trial() {
  flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    PYTHONPATH="$PWD:$release/src:$release" "$release/venv/bin/python" -B \
    reports/ALGO08/single-core-2x/solver_conservative_continuation_trial.py "$@"
}
trial stock "$saved_detections" "$tle_archive" "$release/assets" "$offer" "$detection_sha256" > "$stock_receipt"
trial continued "$saved_detections" "$tle_archive" "$release/assets" "$offer" "$detection_sha256" \
  --against-stock "$stock_receipt"
```

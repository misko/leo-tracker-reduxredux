# Guarded publication for the saved-I/Q compact receiver

The existing 20 m rule withheld both released disjoint full-fallback fixes and retained both 15 km containing controls. All 135 published fixes on the archived original-region roof panel remained published. A guarded decision uses the same fitted endpoints, conditional Doppler RMS and frequency objectives as its guard-off control. [Frozen protocol](PROTOCOL.md) · [Prior measured 20 m rule](../../receiver-core/measured-boundary-policy/README.md)

| Recorded panel | Offers | Guard off | Paired 20 m guard |
| --- | ---: | ---: | ---: |
| Original 25 km roof offer | 135 | 135 published | 135 published |
| Released containing stress, 15 km east | 2 | 2 published | 2 published |
| Released disjoint stress, 30 km east | 2 | 2 false publications | 0 false publications |

Both calibration arms had these same decision counts. The original 135 fits retained at least 2.277 km of fitted clearance. On the containing stress, the published errors were 0.266/0.204 km for DS26-0237 and 0.568/0.516 km for DS29-0082, in `c = 0`/fitted order. On the disjoint stress, the original 255 s release gate withheld both and the complete fallback issued the false fixes. The terminal guard preserved their 12.485–12.545 km numerical errors as forced diagnostics. [135 original compact fits and v5 references](../../factors/full-comparison/README.md) · [Containing stress archive](../../receiver-deadline/sequential-fix/README.md) · [Disjoint stress archive](../../receiver-deadline/sequential-fix/omitted/README.md)

## Prospective offers

The new placements use three recordings each from DS26 and DS29. Every recording has a containing offer and two missing offers, with identical entire native GLRT, causal catalogue and screen center across its three 25 km fits. The containing offers placed the surveyed receiver 1.704 km inside. The near omissions missed by about 2.296 km and the clear omissions by 12.296–23.821 km. [Input seal](prospective-source-lock.json) · [First endpoint seal](prospective-prediction-lock.json) · [Actual offer labels](prospective-queries.json)

| Offer | Attempted | Guard off | Paired 20 m guard | Median error, zero / fitted `c` |
| --- | ---: | ---: | ---: | --- |
| Near containing | 6 | 5 published | 5 published | 0.765 / 0.757 km published |
| Near omission | 6 | 6 false publications | 0 false publications | 2.304 / 2.304 km forced |
| Clear omission | 6 | 5 false publications | 0 false publications | 23.186 / 23.186 km forced |

All completed omitted fits reached a face. The five retained near-containing fits cleared their nearest faces by at least 1.040 km, and all five were within 2 km in both arms. Four of six attempts met both the 5% and 10% error allowances against that recording's fixed no-repair v5 reference on its original tile, in both arms. The analogous original-region roof counts were 129/135 and 131/135, respectively. DS26-0168's near-containing fit failed during orbit-phase interpolation. DS29-0357's clear omission timed out. Withholds, failures and timeouts contribute no accuracy successes. There was no false interior fit on these offers. The sample measures only the supplied placements and one roof. [Per-arm scores and v5 references](scores.csv) · [Counts and distributions](summary.json) · [Both-arm charts](charts/index.html)

The paired guard preserved all reported RF RMS and frequency objectives exactly, including the forced fits. Relative to zero calibration, fitting `c` moved the median paired published near-containing error by −0.002 km. The conditional RF RMS changes were +0.060 Hz on near-containing fits, +0.055 Hz on near omissions and −0.037 Hz on clear omissions, with omitted fits counted once as numerical diagnostics. The corresponding median changes to the compact frequency objective were +1.045, +6.425 and +9.878. [Paired calibration ablation](coefficient-ablation.csv)

The guard took 9.23 µs median and 15.28 µs P95 per prospective decision, measured in-process including result validation. The measured compact services took 49.04–180.09 s wall and 46.17–173.00 CPU-seconds. Peak charged memory across these attempts was 404.06 MiB and swap remained zero. [Guard and fit timing](guard-timing.csv) · [Raw service receipts and logs](prospective-service-logs.tar.gz)

## Command

Use `--interior-guard` on the normal authenticated saved-I/Q command. The original phase-release fit still runs once. The guard reads the exact fitted square and the two selected endpoints. If either fits within 20 m of a face or outside the square, both `latlon` fields become null and their points remain in `forced_latlon`. The guarded outcome is written to `position/position.json` before the command builds its summary. The legacy invocation keeps its existing publication behavior. The cumulative qualification also applies the guard after selecting an accepted early release or its actual full fallback. Non-successful fits retain their previous status and reason.

```bash
python -m tools.pipeline_eval.original_receiver \
  --case "$CASE" --cpus "${CPUS[@]}" --out "$OUT" --interior-guard
```

Two capped services exercised the same saved-I/Q position worker from authenticated original GLRT. The first result file withheld both arms for the disjoint DS26-0237 offer in 89.89 s and published both for the containing DS29-0082 offer in 41.19 s. Both outputs matched the archived numerical endpoints and RF quantities exactly, including the disjoint forced coordinates. Both services used zero swap. This test starts at the position handoff, after the GLRT. [Omitted handoff](handoff-omitted.json) · [Containing handoff](handoff-containing.json) · [Handoff seal and raw receipts](handoff-lock.json)

The roof panels use genuine wideband recordings from one physical location. The earlier fresh-site compact qualification used simulated factor streams. The independent eight-site measured result used prepared StarLoc beacon Doppler and a different receiver and interior rule. It shows that omitted regions can harbor false interior fits under a different measurement contract. Counts across these controls have separate denominators. [Simulated compact sites](../../receiver-core/boundary-policy/README.md) · [Eight independent measured beacon sites](../../pilot-influence/independent-site/README.md)

## Reproduction

Copy the protocol into a new output directory and supply a new local work path. The trial authenticates the source archive and its original native GLRT, then stages actual 25 km receiver installations. The trial runs the first qualified full fit for each sealed offer. The results command scores the sealed paired decisions and renders the three standard charts in each calibration arm.

```bash
trial=tools.pipeline_eval.qualification.final_region_trial
python -m "$trial" stage "$WORK" --report "$REPORT"
python -m "$trial" run "$WORK" --report "$REPORT"
python -m tools.pipeline_eval.qualification.final_region_results --report "$REPORT" --render
```

The first launch used symlinked receiver roots. Twelve sealed services hit module-path verification errors. DS26-0168's near-containing offer hit an orbit-phase interpolation failure and DS29-0357's clear omission timed out. Four unsealed services have raw logs. The corrected run uses real directories and the same sealed roster and geometry. The two initial numerical outcomes remain in the prospective denominator, with corrected-harness repeat statuses shown separately. [Initial source lock](preflight-source-lock.json) · [Initial runner](preflight-source.tar.gz) · [Initial attempt receipts](preflight-attempts.tar.gz) · [Historical scorer sources](historical-scorer-sources.tar.gz) · [Historical handoff sources](historical-handoff-sources.tar.gz)

# DS10 geographic transfer: the frozen baseline exceeds 1 km reference distance

**The frozen zero-height baseline does not reproduce the earlier pooled subkm reference agreement on DS10.** All 24 selected inputs validate, all four primary panels complete, and all 24 optimizer starts qualify. The pooled N24 reference distance is 1,092 m, compared with 809 m for the configured center alone. These distances remain conditional on the previous installation/reference coordinate applying to DS10.

| Primary panel | Tracks | Observations | Qualified starts | Horizontal reference distance |
|---|---:|---:|---:|---:|
| Interleaved N8_0 | 460 | 25,356 | 6/6 | 1,076 m |
| Interleaved N8_1 | 494 | 26,128 | 6/6 | 1,803 m |
| Interleaved N8_2 | 489 | 23,930 | 6/6 | 1,847 m |
| Pooled N24 | 1,443 | 75,414 | 6/6 | 1,092 m |
| Configured center, no RF fit | — | — | — | 809 m |

The three N8 panels partition N24; these four results are not independent trials. No primary fit is within 1 km of the supplied reference or closer than the configured center. Numerical convergence is therefore insufficient evidence of accuracy. Preserve this transfer failure without retuning the model, changing scan selection or relabelling a secondary scenario as the primary result.

**All predeclared height scenarios are now complete.** None of the twelve panel/height combinations reaches 1 km reference agreement or beats the configured center. No secondary result is substituted for the frozen baseline. [summary.json](summary.json) verifies complete coverage and preserves full precision.

| Panel | Reference distance, 0 m height | At 20 m | At 40 m | Held-score change, 20 m vs 0 m | Held-score change, 40 m vs 0 m |
|---|---:|---:|---:|---:|---:|
| N8_0 | 1,076 m | 1,072 m | 1,067 m | +1.40 | +2.18 |
| N8_1 | 1,803 m | 1,829 m | 1,857 m | −9.45 | −19.80 |
| N8_2 | 1,847 m | 1,872 m | 1,898 m | −4.91 | −10.40 |
| N24 | 1,092 m | 1,105 m | 1,117 m | −12.22 | −26.42 |

Positive held-score change favors the height scenario on that panel's same observations. Scores are comparable across heights within a panel, not directly across unequal panel populations. The small improvement on N8_0 does not generalize to the other panels. The height scenarios do not rescue the primary transfer result and are not measured installation heights.

![Complete DS10 reference-distance comparison](reference-distance.png)

This follows review of the existing receiver-association work: [shared identity coupling](../2026_09_29_rx_identity_coupling/README.md) already failed to improve held prediction consistently. Repeating that experiment would not add evidence. A new dataset transfer test of the retained baseline is a more useful next step than another fit-weight adjustment on repeatedly inspected DS7–DS9 panels.

## Frozen evaluation

Chronological recording ordinals are:

`1, 9, 17, 25, 33, 41, 49, 57, 65, 73, 81, 89, 98, 106, 114, 122, 130, 138, 146, 154, 162, 170, 178, 187`.

Selection uses integer ranks `i*(N-1)//23`, including the first and last recording. It does not use signal quality, sample rate, candidate identities or location results. The 24 records form one N24 panel and three disjoint interleaved N8 panels. These are sparse time-balanced sets, not consecutive eight-scan acquisitions. No failed export will be replaced by a more convenient recording.

The [protocol](PROTOCOL.md) freezes the existing q020 model/configuration and six-start procedure. Zero-height geometry is primary for exact baseline comparison; 20 m and 40 m are predeclared secondary sensitivity cases, not measured antenna elevations. Membership, configuration and numerical source hashes are in [plan.json](plan.json).

## Completed checks

- DS10's own offline verification passed: 187 recordings, 414,161 visits, 49,699.32 valid IQ seconds per receiver, eight excluded candidates. Its membership was not changed.
- All 24 selected analysis-receipt digests match the DS10 manifest.
- Two selection tests passed: chronological membership/endpoints and immunity to sample-rate values; duplicate-session rejection.
- All 24 inputs exported and validated through the pinned runtime and existing read-only observation/propagation ports. There were no failures, replacements or retries. The first input was reused after verification; the remaining 23 exports have separate process receipts/logs.
- Complete inputs: **1,443 eligible tracks and 75,414 observations**. Analysis digests match minted GLRT metrics, input artifacts are hashed, sample rates agree, and every orbital-provider snapshot satisfies the inherited causal cutoff.
- Selected sample-rate counts are 3 at 2.5 MS/s, 4 at 5 MS/s, 7 at 7.5 MS/s and 10 at 10 MS/s. Rates did not select membership.
- `audit_inputs.py` rechecks the frozen plan/implementation, all minted analysis digests, session identity, source manifests and artifact hashes. The complete audit passes.
- Each primary panel contains exactly the declared six starts; training-only selection and source bindings verify. N8 runs take 33–38 seconds; N24 takes 131.5 seconds, within the 180-second caps.

Input evidence is retained under `exports/<unit>/validated.json`, alongside observations and candidate-bank manifest/NPZ. `input-audit.json` records complete coverage; `export-batch.json` and `receipts/` preserve execution status. No raw IQ was read or collected. Starts and selected fits are under `fits/<panel>_h<height>/`; `fit-receipts/` records execution. All twelve panel processes exited zero within their 180-second caps.

Across the twelve fits, **70/72 starts qualify**. Every selected endpoint qualifies. The unqualified starts are retained without retries:

- N8_0 at 20 m, cold +2 km east: optimizer returned `ABNORMAL` with maximum gradient 0.000434; the success requirement still fails.
- N24 at 40 m, timing-grid +2 km east: optimizer reported convergence, but maximum gradient 0.010426 exceeded the unchanged 0.01 qualification limit.

No qualification threshold was relaxed. The result auditor verifies exactly six declared starts per panel, training-only highest-qualified-score selection, exact session membership and saved source/artifact hashes. Plot values come directly from that audited summary; the rendered figure was inspected for legibility.

## Interpretation limits before execution

DS10 has already been used for waveform and identity research. This is a newly frozen geographic transfer evaluation, not a claim of a wholly unseen research dataset. No new geographic outputs were read to choose these recordings.

The DS10 mint did not collect pose companions. The prior physical installation/roof reference is therefore not independently attested for DS10 here. Any reference-distance table must explicitly retain that assumption, unresolved reference uncertainty and antenna-height uncertainty. The banks and search configuration remain site-conditioned; the configured center is itself near the prior reference. Do not interpret a numerically successful fit as independent global localization.

## Consequence and next work

The declared evaluation is complete, and it does not establish a generally transferable subkm method. First resolve whether DS10 used the same installation/reference; that question is pending. Independently of that answer, retain the numerical transfer result and its site-conditioning caveat. If the location is unchanged, this is further evidence that successful optimization and pooled DS7–DS9 reference agreement do not ensure subkm performance on another dataset.

Any later change must be explicitly labelled development on exposed DS10 data, not a replacement baseline or blind confirmation. Diagnostic work should distinguish geometric/association/model mismatch using held evidence, rather than tune scan selection, height or nuisance weights to pull the DS10 point toward the reference. This report does not identify which physical error caused the discrepancy.

```sh
python3 reports/2026_09_29_ds10_post_ds9/mint.py verify
python3 -m unittest discover -s reports/2026_09_29_ds10_geographic -p 'test_*.py'
sudo -n env OPENBLAS_NUM_THREADS=1 timeout 180 /opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python reports/2026_09_29_ds10_geographic/export_one.py DS10-F009
```

The example export command now names a completed unit and intentionally refuses to overwrite it. `prepare.py` creates the plan exclusively; do not rerun over the frozen plan. `export_one.py` refuses existing observation/bank outputs and requires explicit staged recovery of a partial export. `fit_batch.py <height>` first requires the complete input audit; completed batch logs/results also refuse overwrite. The fit runner saves each start with source hashes before proceeding, permitting explicit review of partial execution if needed.

`primary-evidence.json` binds the unchanged baseline outputs. The initial `checkpoint.sha256` records the historical preparation checkpoint, before this README and status summaries were updated; it is not the final directory seal. `evidence.sha256` binds the completed current report, plot, scripts, inputs, results and process receipts. Reproduction starts from a fresh output context, or audits the saved artifacts with `audit_inputs.py` and `summarize.py`; do not overwrite completed numerical results.

No RF acquisition, production changes or remote publication occurred. Primary evaluation and all declared height sensitivity are complete. Reliable subkm accuracy is not established by this transfer test.

# Alternating the fifth acquisition region across twenty roof recordings

The reconstruction chooses one of the two physical receiver lanes for the fifth detector region on every valid visit. The lane starts at zero for each recorded tuning center, then alternates across later valid visits at that center. A hardware-invalid visit leaves parity unchanged. The other receiver uses its complete four-region packet. The algorithm uses the exact recorded integer RF center, so distinct channel labels sharing that center use the same parity. Each selected packet carries its original candidate records and admission flags. The position solver then consumes the reconstructed packet sequence and performs fresh `c = 0` and fitted-`c` fits.

The archived four- and fifth-region runs used the same ordered raw-IQ identity, signed segment manifests, physical lane identifiers, hardware exclusions, calibration configuration and delivery clocks. All twenty complete input pairs were retrievable and passed authentication before position scoring. [The pre-inference plan](plan.json) binds these inputs, the later truth-free requests, the source versions and the frozen twenty-case roster. [The packet audit](packet-audit.json) binds each parent native body, the exact selected packet sequence, each segment manifest, the RF map, and the source clock. Counts of changed winners compare the full selected winner record, including detector metadata.

Of 135,442 scheduled stereo visits, 132,740 were valid and 2,702 were hardware-invalid. The fifth region went to lane zero on 66,411 valid visits and lane one on 66,329. Across physical lanes the complete stock, alternating and complete fifth packets contained 85,812, 89,640 and 93,363 gated probes respectively. The reconstruction added 3,906 gated probes and lost 78 relative to stock. [Per-recording support census](raw-support.csv)

The installed phase-release receiver ran as separate Linux services on CPUs 2–5, with one numerical thread, `nice 10`, `MemoryMax=512 MiB`, zero swap and 210 s per recording. [Service measurements](resources.csv) cover stored native input through both numerical position arms and include peak cgroup memory. The earlier complete controls and the original four v5 roles supply reference positions, independently recorded native digests and conditional RF measurements. This study uses stored detector packets, so its detector runtime is unavailable. It measures a counterfactual acquisition selection and new numerical fits on these roof recordings. The separate direct native study measures computation from saved IQ.

## Results

All 20 reconstructions returned coordinates in both calibration arms. Each table cell lists `c = 0` / fitted `c`.

| Receiver | Median error, km | P95 error, km | Within 1 km | Within 2 km | Median conditional RF RMS, Hz |
| --- | ---: | ---: | ---: | ---: | ---: |
| Complete four regions | 0.774 / 0.776 | 1.592 / 1.388 | 15 / 16 | 19 / 19 | 85.483 / 85.497 |
| Alternating fifth region | **0.686 / 0.681** | 1.388 / 1.423 | 15 / 14 | 20 / 19 | 87.010 / 86.963 |
| Complete fifth region | 0.746 / 0.825 | 1.567 / 1.533 | 15 / 15 | 20 / 20 | 88.348 / 88.369 |
| Original v5 baseline | 0.739 / 0.724 | 1.719 / 1.653 | 14 / 13 | 19 / 19 | 105.505 / 94.993 |
| Original v5 selective gap | 0.739 / 0.724 | 1.719 / 1.653 | 14 / 13 | 19 / 19 | 105.505 / 94.993 |
| Original v5 omitted track one | 0.703 / 0.695 | 1.719 / 1.653 | 14 / 13 | 19 / 19 | 107.595 / 94.988 |
| Original v5 omitted tracks | 0.703 / 0.695 | 1.719 / 1.653 | 14 / 13 | 19 / 19 | 107.595 / 94.988 |

All seven variants were within 5 km on all 20 recordings in each arm. Relative to complete stock, alternating was closer on 11 of 20 `c = 0` recordings and 10 of 20 fitted-`c` recordings. The median paired change was −7 m and −6 m. DS29-0330 had the largest increase in error at +1.017 km and +0.990 km. Relative to complete fifth, alternating was closer on 11 of 20 recordings in each arm, with median paired changes of −8 m and −6 m. In each arm, 10 of 20 alternating endpoints were within 5% of the original-v5 baseline error, and the same 10 of 20 were within 10%. [Paired effects](paired-effects.csv)

Median track counts were 126.5 for complete stock, 138 for alternating and 140 for complete fifth. Median paired conditional RF RMS rose by 0.89 Hz and 0.83 Hz relative to stock and fell by 0.76 Hz in both arms relative to complete fifth. The largest coordinate shifts and the RF changes therefore need separate interpretation. Each new position service took 44.1–118.0 s after acquisition, with median wall time 72.35 s and median service CPU time 55.65 s. Peak cgroup memory reached 479.2 MiB, with no swap. [Per-recording position and frequency scores](scores.csv) · [Resource measurements](resources.csv)

## Verification

The candidate `positions.jsonl.gz` contains one terminal result for each scheduled recording and is authenticated by `prediction-lock.json`. `capture-era-v5.csv` contains all four original roles, including the authenticated extensions for DS29-0047 and DS29-0330. `scores.csv` and `paired-effects.csv` retain per-recording paired position and conditional RF measures. The figures include the original-v5 roles and both complete detector controls on matched recordings in each calibration arm. [Position figures](charts/README.md)

The rehearsal uses `python -m tools.pipeline_eval.qualification.staggered_reconstruction_trial /path/to/new/local/work` in a separate checkout or a report directory without an existing plan. After all numerical jobs finish, use `python -m tools.pipeline_eval.qualification.staggered_reconstruction_results /path/to/work` to publish scores from the sealed candidate results. The input paths in the packet audit refer to locally archived native documents or the recorded read-only corpus. The receiver file ledger in `plan.json` identifies the installed phase-release payload.

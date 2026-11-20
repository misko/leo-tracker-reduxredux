# One stock-derived cavity challenger on merged data

All three challengers lost the original merged predictive screen. The genuine receiver therefore reproduced each ordinary merged position and conditional frequency fit in both calibration arms. The separate diagnostic refits show why a stock prior alone is insufficient. The two negative-rescue challengers also failed original paired fit gates. The restore-only challenger passed the paired gates and had lower geographic error, while its conditional RF RMS and objective were worse.

This prototype takes a single rival satellite from an actual stock cavity ranking and tests it with the merged receiver's own tracks, held-family predictive score and numerical solver. It keeps the ordinary merged position unless the rival meets the original predictive and paired acceptance rules. The rejected branch can still produce a separate diagnostic endpoint. The experiment tests DS26-0168 and DS29-0604 from negative rescue and DS26-0237 from a distinct stored wide-to-restore merge. [Prespecified rule and timing scope](PROTOCOL.md) · [Native, orbits, and solver bindings](plan.json)

Stock cavity pairs are ranked by the receiver's measured held-family predictive gain. A pair can transfer only when at least four shared observations agree on one current merged owner and that owner is in the stock pair. The other member challenges it. This lets a stock alternate that the merged receiver already chose nominate the original stock owner for a reverse check. No NORAD is hardcoded. One complete stock replay produces the prior, so this qualification charges the full donor cost separately. [Candidate-selection evidence](candidate-evidence.json) · [CPU, wall and memory](resources.csv)

| Recording | Merged owner → challenger | Stock-held points that matched | Merged held predictive gain | Diagnostic paired fit gate |
| --- | --- | ---: | ---: | --- |
| DS26-0168 | 61704 → 47386 | 99 | −112.981 | Failed |
| DS29-0604 | 63717 → 64610 | 44 | −9.944 | Failed |
| DS26-0237 | 67081 → 59899 | 142 | −2.608 | Passed |

On DS26-0168, the actual stock fit accepted 47386 → 61704. The merged receiver had already assigned all 99 mapped stock-held observations to 61704. Its full held family had 298 points and strongly rejected the reverse change. [Actual stock cavity and grouping analysis](../locked-assignments/README.md) · [Merged rejection evidence](candidate-evidence.json)

| Recording | Stock geographic error | Published merged and replay error | Rejected diagnostic error |
| --- | ---: | ---: | ---: |
| DS26-0168 | 0.805 / 0.796 km | 1.472 / 1.473 km | 2.676 / 2.680 km |
| DS29-0604 | 0.735 / 0.734 km | 0.780 / 0.797 km | 0.791 / 0.811 km |
| DS26-0237 | 0.382 / 0.323 km | 0.303 / 0.173 km | 0.142 / 0.171 km |

Values list zero c and fitted c in that order. The DS26-0237 rejected branch reduced zero-c error by 161 m and fitted-c error by 2 m. Its conditional RMS rose from 92.542 / 92.469 Hz to 92.560 / 92.489 Hz, with the objective also increasing in both arms. The predictive gate made its normal RF-based decision before the geographic score was available. For DS26-0168 and DS29-0604, both conditional RMS and geographic error rose in the diagnostic fits. [Both-arm scores and four original v5 references](scores.csv) · [Diagnostic position figures](figures.json)

All six services completed with the original phase-release receiver under physical 512 MiB cgroups and zero swap. Prior creation used 66.6–106.6 CPU seconds per recording. The extra screen used approximately 0.2 ms CPU in each run, and the separate rejected diagnostic refits used 2.78–5.13 CPU seconds. Both new and ordinary merged positions use the same admitted factors. The timing begins at saved detector factors. [Measured CPU, wall and cgroup use](resources.csv) · [Closed prediction receipt](prediction-lock.json)

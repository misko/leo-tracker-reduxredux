# Four-anchor winner selection

The four-anchor rule made **zero winner changes** across 104,252 valid native receiver probes from six hard recordings and two controls. All eight compact replays used byte-identical fixed four-region factors. The candidate filter added 51–260 ms of host CPU time per complete factor array, with parsing and compact fitting measured outside that filter timer.

The rule uses two original winners on each side of the current probe, on the same receiver, channel and edge, within a 2.6 s span. Actual retunes are removed before each side independently predicts absolute Doppler and wrapped fractional timing. It can offer an already admitted candidate if it uniquely agrees with both forecasts and the incumbent agrees with neither. The filter leaves all scores, ranks and gates exact on the candidates it offers. This is batch processing with future support.

Of 34,676 probes with multiple gated candidates, 185 had usable forecasts from both sides. Each forecast opportunity ended with a supported incumbent (174), multiple alternatives (6), or no supported alternative (5). Of the remaining ambiguous probes, 34,284 lacked the required anchors or span, 35 had mutually incompatible anchor steps, and 172 were too close to a lane boundary to have two probes on each side. The six multiple-alternative abstentions are retained under the frozen rule.

On the hard six, fixed four selected 23,321 of the 25,971 original physical winners. Among the 2,650 it missed, 458 were present among already gated alternatives and 2,192 were unavailable under the unchanged gate. The rule recovered or lost zero of the original physical winners. That 458 is the recall ceiling for strict reselection of the offered gated candidates on this panel.

The eight fresh compact runs reproduced the stock coordinates, RF RMS and frequency objective exactly in both arms. Geographic error was within 5 km for all eight in both arms. Median error was 0.737 km at `c0` and 0.814 km at fitted `c`. The respective maxima were 2.489 and 2.346 km. The host compact services used 40–116 CPU seconds with 50–152 elapsed seconds while other host work ran, and reported 351–455 MiB cgroup peaks with zero swap. These are stored-factor service costs on the pinned host cores.

## Files

- `PROTOCOL.md`, `source-lock.json`, `predecision-lock.json` and `edits.json` bind the experiment before geographic scoring or inspection of the archived winners.
- `prediction-lock.json` and `positions.jsonl.gz` contain eight fresh complete compact attempts with separately archived service logs and resource receipts. The recording waveforms were processed in the earlier fixed-four experiment. This trial begins with those authenticated stored factors.
- `physical-support.csv` and `support-audit.json` compare hard-case winners against the capture era after compact predictions were sealed. Epoch agreement is within two samples and CFO agreement within an absolute 1 kHz. The ceiling includes only original physical winners present among the fixed-four gated alternatives.
- `geographic.csv` and `frequency-fit.csv` report geographic and frequency fit outcomes separately for each calibration arm. The standard position charts compare the fresh compact runs with fixed four regions and the four capture-era v5 choices.

## Reproduce

From the workspace root, the results command verifies the existing receipts against the authenticated factor archives and renders figures. It uses the published input digest equality to audit the unchanged candidate factors without local worker scratch. Use `--out` to render a fresh copy. The freeze and fit stages below describe the original measurement. Repeat those stages in a separate workspace copy and use a fresh `--work` path for both. Fit starts one host worker per assigned core with a 512 MiB cap, zero swap and a 210 s deadline.

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.consistent_peaks_trial freeze
.venv/bin/python -m tools.pipeline_eval.qualification.consistent_peaks_trial fit
.venv/bin/python -m tools.pipeline_eval.qualification.consistent_peaks_results
```

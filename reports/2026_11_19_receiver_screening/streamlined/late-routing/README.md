# Late recovery triggered by held Doppler curvature

Keep the curvature test as a negative control. It retained the two known material repairs on fresh aligned receivers, but still sent **127 of 135** archived calls to full late recovery, including **125 of 133** capture IDs outside the diagnosis. The difficulty is deciding which coherent residual curves will change the position. Detecting coherent curvature is cheap.

## Request-time input and cost

The gate reads only the existing top three wholly unowned residual fragments after the aligned cavity, with hardware and drift corrections already available in each calibration arm. It trains on the middle half of the time interval and requires the quadratic predictor to reduce the combined outer-quarter RMS by at least 40% over the linear predictor in both arms, with agreeing curvature sign. There is no site, satellite ID, position, error, final decision, or identity fit in the gate. The fixed thresholds, preselected confirmation draw and matched inputs are in the protocol and run lock. The late screen and reassociation remain unchanged when invoked. Declines skip late orbital propagation and family ranking. The unmodified aligned complete fit is the live control.

The 135 genuine original v5 archive packets were verified against the execution, frozen solver, request and ZIP SHA-256 receipts. All 135 had valid diagnostics. Median test CPU was **0.563 ms** and P95 **0.853 ms**, excluding preparation already performed by the receiver. The eight archive declines account for **553.57 of 11,315.95 seconds** of the five archived late stages, or **4.89%**. This is an upper bound on the archived stage time exposed to the bypass, before fallback/control bookkeeping. It does not measure complete receiver speed. The previous RF-only reassociation preflight bypassed 16 of 135 while always running residual addition. The new whole-late trigger addresses more work per decline with roughly half as many declines.

## Independent archive outcomes and fresh checks

On the 133 non-diagnostic archived cases, 9 of 10 changed original endpoints would retain full recovery. The other 116 dispatched cases had no endpoint change. Of eight declines, seven had no change. DS26-0016 missed a real addition and lost 74.8 m with zero c and 76.4 m with fitted c. The two improvements of at least 100 m were both used for diagnosis. There were zero independent improvements of that size, so the independent archive cannot establish recall for similarly large repairs. No original 5 km success crossed that boundary under this archive replay.

| Original archive stage selected | Zero-c P50 / P95 km | Fitted-c P50 / P95 km | Within 5 km, both arms |
|---|---:|---:|---:|
| Cavity | 0.982 / 2.941 | 0.988 / 2.819 | 133/135 |
| Curvature route | 0.982 / 2.941 | 0.988 / 2.819 | 133/135 |
| Full late oracle | 0.982 / 2.941 | 0.988 / 2.819 | 133/135 |

Median archived conditional RF RMS for the curvature route was 109.19 Hz with zero c and 96.68 Hz with fitted c. Full late was 109.78 / 98.15 Hz and cavity was 71.17 / 71.05 Hz. These values use the conditional support of each archived stage, which differs after ownership changes. They do not score the same observations and should not serve as a localization criterion.

| Fresh routed worker | Late work | Zero-c / fitted-c error km | Zero-c / fitted-c conditional RF RMS Hz |
|---|---|---:|---:|
| DS26-0066, diagnosis | Added residual family and repaired 62025 → 68047 | 1.209 / 1.191 | 69.87 / 69.94 |
| DS26-0287, diagnosis | Added residual family | 0.502 / 0.439 | Not recorded |
| DS26-0098, hash confirmation | Dispatched, no correction | 0.229 / 0.110 | 78.84 / 78.85 |
| DS26-0146, hash confirmation | Dispatched, no correction | 0.625 / 0.546 | 57.51 / 57.50 |
| DS26-0231, supplemental bypass | Bypassed both late branches | 0.782 / 0.752 | 115.91 / 115.84 |

Each fresh row exactly matches both endpoints and all available conditional RMS values of its authenticated aligned control. The diagnostic controls are sealed prior runs. The counterbalanced fresh confirmations used the same core for each pair. For DS26-0098 control → routed was 130.47 → 122.08 seconds wall and 95.15 → 97.57 seconds child CPU. For DS26-0146 it was 104.56 → 118.76 seconds wall and 91.02 → 87.98 seconds CPU. Both performed the same numerical route. These fluctuations do not support a speedup.

The supplemental case was hash-selected from the eight archive declines before its scoring and has its own run lock. Its two independent workers ran in parallel on different cores. The targeted late stages took 34.79 seconds wall in the control and 0.007 seconds in the bypass. Whole-worker wall was 125.74 / 86.31 seconds and child CPU was 88.06 / 61.38 seconds. The stage measurements confirm that the bypass avoids that work on an actual decline. The parallel pair does not isolate an end-to-end speedup.

The archived figure shows an offline choice between two authenticated recorded positions. The fresh figure shows actual stored-native replays, without IQ or detector processing. The archive covers 127 DS26 and eight DS29 roof captures. It has no matched predecision census for the remaining 32 DS26 captures in the all159 panel, so the 127/135 duty does not establish all159 duty. The experiment uses the aligned compact finish after a real cavity, before either late branch. It does not claim prospective performance of a combined stock-first exception and late policy.

- [Protocol and prospective lock](PROTOCOL.md) · [Run lock](run-lock.json)
- [All archived decisions and position/RF effects](archive-summary.json) · [Both-arm scores](archive-scores.csv) · [Truth-free predecision packets](archive-predecision.json.gz)
- [Fresh worker comparison](live-summary.json) · [Both-arm scores](live-scores.csv) · [Supplemental bypass lock](bypass-lock.json) · [Standard roof figures](figures.json)

## Reproducing the sealed decisions

[Measured source archive](measured-source.zip) preserves the original worker, gate, extractor, and qualification drivers byte for byte. The original run, archive, and bypass seals still provide their SHA-256 digests. Run the following command to compare every recorded decision and both-arm RF diagnostic with the original and cleaned gates. It can also take a relocated copy of this report directory via `--report`.

```sh
OPENBLAS_NUM_THREADS=1 python -m tools.pipeline_eval.qualification.late_routing_sources
```

To reread the original zipped checkpoints, run `python -m tools.pipeline_eval.qualification.late_routing_archive --output /path/to/new-directory`. This uses the archived extractor and gate with the original scientific bindings. Only the new extraction timings are measured again. The original receipts and results remain in this directory.

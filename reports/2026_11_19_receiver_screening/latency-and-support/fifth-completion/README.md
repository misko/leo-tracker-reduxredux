# Optional fifth center on ten additional matched IQ recordings

The fifth-center receiver returned both calibration arms on **10/10** recordings. Its median error was **0.786 / 0.828 km** at `c = 0` / fitted `c`, with P95 at **1.263 / 1.256 km**. Stock medians were 0.774 / 0.781 km and P95 was 1.323 / 1.329 km. On this host, the fifth-center detector completed **3 of 67,136** unpaced dual-receiver calls inside 20 ms. [Zero calibration](charts/c0/modifications.pdf) · [Fitted calibration](charts/fitted_c/modifications.pdf) · [Score summary](summary.json)

The twelve-recording stock wide roster and the earlier eight-recording stock/fifth panel share DS26-0237 and DS29-0082. This experiment runs the same released fifth-center detector on the ten other stock recordings. It uses both receivers on each saved waveform and the actual installed compact phase release. These are ten additional detector-arm measurements at the same surveyed roof. [Protocol](PROTOCOL.md) · [Case, input and executable lock](source-lock.json)

## Pairing and audit

The schedule was fixed before the new services started. The scheduler deals sorted IDs round-robin to CPU pairs 12/13, 14/15 and 16/17. Each pair has one active unpaced replay service at a time. The service reads both receiver lanes from archived IQ, observes original capture exclusions and passes the complete newly computed native GLRT factors to compact positioning. The original search tile, causal TLE history, tracking configuration and scientific solver release are shared across methods. Each replay has a 450 s deadline, a 512 MiB cgroup cap and zero swap. [Source lock](source-lock.json) · [Terminal authorities](raw-authority.json) · [Resource receipts](resources.json)

The four-center comparison is the previously sealed fixed primary attempt for each recording. The pair checks cover IQ authority, deliveries and sample counters, per-probe receiver, position in the sequence, RF metadata, exclusions and original request. Probe candidate payloads are allowed to vary with the detector. Gate retention fingerprints the passing payloads with the export rank removed. The fifth-center lane trace independently checks that an extra valid epoch neighborhood leaves the original center choices intact. Candidates still compete at the shared ranking and gate stages. [Stock provenance](stock-authority.json) · [Probe audit](probe-audit.json)

Of 134,272 matched receiver probes, 112,183 evaluated a distinct fifth center. The fifth added 3,787 probes with a passing candidate and lost 82 that were positive in stock, changing the positive total from 45,019 to 48,724. It retained 202,610 exact passing payloads, lost 10,298 stock passing payloads and added 19,798. The fitted solver used a median 375 additional observations and 12.5 additional tracks per paired recording. [Fifth-center admissions](raw-authority.json) · [Probe and track comparisons](probe-audit.json)

## Positions and RF fit

Both calibration arms use the same native factors, tile, and search configuration within each detector. The position scoring compares returned coordinates with the surveyed roof. The 5% and 10% counts include the full roster and use each recording's matching original no-repair v5 arm. The four original v5 options use their archived capture-era factors. Frequency RMS and frequency objective describe the fit conditional on each receiver's associated observations. [Candidate prediction seal](prediction-lock.json) · [All per-arm scores](scores.csv) · [Paired changes](paired-deltas.csv) · [Calibration deltas](calibration.csv)

Each paired cell lists `c = 0` / fitted `c`.

| Detector | Coverage | Within 5% of v5 | Within 10% of v5 | Median error (km) | P95 error (km) | Median RF RMS (Hz) |
| --- | --- | --- | --- | --- | --- | --- |
| Optional fifth center | 10/10 / 10/10 | 5 / 4 | 5 / 5 | 0.786 / 0.828 | 1.263 / 1.256 | 85.696 / 85.703 |
| Archived stock wide | 10/10 / 10/10 | 4 / 5 | 4 / 5 | 0.774 / 0.781 | 1.323 / 1.329 | 84.503 / 84.536 |

The fifth improved error on six recordings in each arm. Median within-recording fifth minus stock error was −0.023 / −0.012 km. Conditional RF RMS increased by a paired median of 1.193 / 1.166 Hz and the conditional frequency objective increased by 3,381 / 3,379. The two detectors fit distinct sets of observations. Within the fifth path, fitting `c` changed the frequency objective by a paired median of −2.317, conditional RF RMS by +0.013 Hz and geographic error by +0.006 km. [Per-pair geography and RF metrics](paired-deltas.csv) · [Calibration deltas](calibration.csv)

## Timing

The archived four-center runs used the CPU pairs and service deadlines recorded in the comparison ledger. The unpaced host measurements give pipeline and detector timings under those specific conditions. Wall counts at 20 ms refer to measured dual-receiver detector calls. [Timing ledger](timing.csv) · [Host timing figure](timing.png)

| Detector | Pipeline wall median / P95 (s) | CPU median / P95 (s) | Raw / position wall medians (s) | Calls at or below 20 ms |
| --- | --- | --- | --- | --- |
| Optional fifth center | 271.2 / 303.2 | 342.1 / 406.1 | 162.7 / 99.3 | 3 / 67,136 |
| Archived stock wide | 196.5 / 243.9 | 250.7 / 296.5 | 112.4 / 84.8 | 29,567 / 67,136 |

The ten fifth services completed over 970 s of elapsed campaign time. Individual pipeline walls ranged from 206.0 to 303.4 s, under the 450 s limit. Peak charged memory reached the 512 MiB cap, with zero swap and zero OOM kills in every candidate service. These unpaced host timings cannot establish arrival or device deadline behavior. [Actual resource receipts](resources.json)

The score command uses the sealed predictions and paired native exports.

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.fifth_completion_results score
```

The prediction lock binds the exact launcher bytes, candidate native gzip exports and individual terminal receipts. The source checked into the workspace received only line wraps after the numerical seal. Its Python AST matched the archived executable source, and the decompressed archive matched the original program digest. [Prediction lock](prediction-lock.json) · [As-measured launcher](as-measured-launcher.py.gz)

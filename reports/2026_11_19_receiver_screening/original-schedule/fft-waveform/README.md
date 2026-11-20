# Complete DS29-0519 comparison of stored 256- and prepared 512-point FFTs

The stored 256-point replay completed all **6,771 scheduled visits** in **394.96 seconds**, compared with **577.33 seconds** for the earlier 512-point replay on the same chunk and CPU assignments. It reproduced **62,048 ordered published candidates** exactly. Every valid visit exceeded 20 ms detector wall in both full runs. [Audit](audit.json) · [Matched comparison](comparison.json) · [Stage chart](timing.pdf)

This replay changes the prepared overlap-save bank on DS29-0519 from the released 512-point plan to the frozen 256-point plan with stored FFTW wisdom. It retains the original screened lower-edge release, both physical lanes, 12/22 anchor policy, row-wise peak selection, four-frame fine CFO, later physical refiners and signed 25 km offer. The workers keep the earlier complete 512 run's exact chunks and CPU assignments. [Source lock](source-lock.json) · [Protocol](PROTOCOL.md) · [Earlier complete run](../../retry-and-transfer/batched-waveform/README.md)

The new launch checks include an exclusion, a negative, a near-gate fixture, two independently measured ordering witnesses and three additional sequence-hash visits. The 512 and 256 paths agree on complete public responses, projected factors and acquisition attempts on all eight. The preceding stage assay separately tested empty, near-tie and ordering controls and measured a 15.60 ms paired median complete detector CPU saving across 40 counterbalanced real calls. [Launch receipt](receipts/smoke.json) · [Independent held comparison](../../coarse-and-navigation/fft-length/README.md)

The initial launch service stopped before detection because the earlier report's binary copy was readable only by its owner. The replay loads an independently hashed readable copy of those same bytes from this evidence directory. [Initial launch receipt](receipts/initial-preflight/receipt.json) · [Stored-plan library](prepared-256.so) · [As-run source snapshot](source-snapshot.json)

## Native fields

The workers authenticated all 106 compressed chunks, 6,727 valid visits and 44 capture exclusions. All 13,454 physical probes matched the signed archive and measured 512 stream, including 22 empty rows, 14,464 gate-passing candidates and 4,637 probes with at least one pass. Candidate ranks, epochs, CFO, exact and control scores, margin and gate flags matched in canonical encoding. The UTC anchor, delivery clocks, final sample counter and exclusion records also agreed. Both full runs performed 15,210 folded-grid calls with identical per-visit counts and 121,680 batched fine calls without fallback. [Fresh native stream](native.json.gz) · [Exactness audit](comparison.json) · [Fine ledger](fine.csv) · [Folded grid ledger](coarse.csv)

## Position and RF calibration

Independent compact fits on the fresh and archived factors reproduced the earlier complete 512-point endpoints in both calibration arms. Coordinates, conditional RF RMS and frequency scores were identical at full reported precision. Each compact fit used 4,637 observations, 143 tracks and 7,290 projections. The same 43 causal TLE snapshots and 25 km offer bound all comparisons. The prediction lock preceded geographic scoring against the held survey. [Prediction lock](prediction-lock.json) · [Geographic scores](scores.csv) · [All four v5 role records](v5-roles.csv) · [Chart, c = 0](charts/c0/modifications.pdf) · [Chart, fitted c](charts/fitted_c/modifications.pdf)

| Position input | Error at `c = 0` (km) | Error with fitted `c` (km) | Conditional RF RMS, zero / fitted (Hz) |
|---|---:|---:|---:|
| Fresh stored 256-point FFT | 0.23499 | 0.30588 | 76.4584 / 76.5237 |
| Independent archived-factor compact fit | 0.23499 | 0.30588 | 76.4584 / 76.5237 |
| Earlier complete 512-point FFT | 0.23499 | 0.30588 | 76.4584 / 76.5237 |
| Earlier complete fast four-region | 0.33430 | 0.32371 | 90.2303 / 90.3410 |
| Earlier complete fast five-region | 0.66460 | 0.76268 | 89.0001 / 89.0351 |
| Original v5, all four roles | 0.24831 | 0.31923 | 100.7451 / 81.3416 |

Fitted `c` increased the geographic error by 70.89 m in each complete FFT run. Conditional RF RMS rose by 0.0653 Hz and the frequency score rose from 33,820.243 to 33,821.523.

## Host timing

Both raw runs used cores 0, 1 and 6–11 on the same Intel Core Ultra 9 285K host. Each worker had 512 MiB charged memory and zero swap. The stored plan halved the largest named FFT workspace from 2,072,576 to 1,036,288 bytes. The fresh worker RSS peak was 215.54 MiB and the largest charged peak was 512 MiB. The archive covers 299.977 seconds of recorded delivery. [Per-visit matched clocks](paired-timing.csv) · [Worker receipts](receipts/)

| Full replay timing | Prepared 512 | Stored 256 |
|---|---:|---:|
| Raw replay wall (s) | 577.33 | 394.96 |
| Bound worker cgroup CPU (s) | 3,159.53 | 2,550.20 |
| Resident detector CPU across valid visits (s) | 3,134.02 | 2,525.91 |
| Coarse CPU across valid visits (s) | 1,570.77 | 1,121.81 |
| Per-visit resident CPU, P50 / P95 / P99 / max (ms) | 432.56 / 1,186.34 / 1,312.81 / 2,070.23 | 378.57 / 750.43 / 829.53 / 1,315.60 |
| Per-visit resident wall, P50 / P95 / P99 / max (ms) | 476.99 / 1,315.00 / 2,726.00 / 14,610.86 | 387.66 / 782.15 / 1,133.21 / 6,142.65 |
| At or under 20 ms detector wall | 0 / 6,727 | 0 / 6,727 |

The complete runs happened at different times on the shared host. Matching by visit gives an observed median saving of 48.90 ms detector CPU and 24.91 ms coarse CPU. The separate counterbalanced held comparisons estimate the isolated prepared-bank effect. [Sequential full-run comparison](comparison.json) · [Interleaved study](../../coarse-and-navigation/fft-length/README.md)

| Independent compact fit, both arms | Wall (s) | Cgroup CPU (s) | Charged peak (MiB) |
|---|---:|---:|---:|
| Fresh 256-point factors, CPU 0 | 46.13 | 45.11 | 293.19 |
| Archived original factors, CPU 1 | 46.63 | 45.24 | 297.75 |
| Earlier complete 512-point factors | 50.29 | 48.39 | 302.71 |

Both fresh position services used zero swap. Raw launch through fresh coordinates took 446.26 seconds, compared with 633.39 seconds in the earlier complete 512-point run. The earlier complete fast four- and five-region runs recorded 188 and one valid calls at or under 20 ms detector wall, respectively. [Fresh position receipt](receipts/actual/terminal.json) · [Archive position receipt](receipts/archive/terminal.json) · [Earlier complete fast resource records](../../latency-and-support/complete-timing/resources.csv)

## Reproduce

Keep the signed paths from the source lock available. Use a clean evidence checkout for a fresh publication. The source snapshot preserves the as-run launcher and collector if shared accounting code changes.

```bash
work=/var/tmp/leo-fft256-repeat
report=reports/2026_11_19_receiver_screening/original-schedule/fft-waveform
mkdir "$work"
cp "$report/source-lock.json" "$work/source-lock.json"
.venv/bin/python -m tools.pipeline_eval.qualification.fft_waveform preflight "$work"
.venv/bin/python -m tools.pipeline_eval.qualification.fft_waveform run "$work"
.venv/bin/python -m tools.pipeline_eval.qualification.fft_waveform_results position --work "$work"
.venv/bin/python -m tools.pipeline_eval.qualification.fft_waveform_results publish --work "$work"
```

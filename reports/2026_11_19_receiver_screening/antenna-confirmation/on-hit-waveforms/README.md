# Partner-on-hit from saved IQ through position

Two of the 14 antenna confirmation recordings were selected by the lowest signed first-segment manifest digest in each of two strata with a frozen ordinary waveform reader. DS26-0168 uses the lower pilot edge and DS29-0174 the upper edge. The selection was locked before scoring position. Each replay used the same signed physical RF schedule, original causal orbit catalogue, 25 km region and compact solver. [Protocol](PROTOCOL.md) · [Selection](selection.json) · [Source lock](source-lock.json)

On each valid visit the stock four-region detector ran on the rotating physical primary. A primary candidate's strict fractional gate triggered a second call on the physical partner. The compact solver consumed the actual emitted observations. Both entire native documents, including empty physical slots and the excluded windows, matched byte for byte against an independently reconstructed projection of the original measured dual-stock factors. The fitted positions and conditional RF residuals also matched the separate compact reruns from the projected factors in both arms. [Parity and RF call counts](parity.json) · [Position lock](prediction-lock.json) · [Independent projection lock](../partner-holdout/prediction-lock.json)

| Recording | Valid / invalid visits | Primary only / two calls | RX calls, hit / dual | Gated probes, hit / dual | Partner-only gated probes omitted |
|---|---:|---:|---:|---:|---:|
| DS26-0168 | 6,774 / 0 | 4,288 / 2,486 | 9,260 / 13,548 | 4,270 / 4,959 | 689 |
| DS29-0174 | 6,704 / 70 | 4,606 / 2,098 | 8,802 / 13,408 | 3,254 / 4,169 | 915 |

Both fixes published in both arms. Partner-on-hit passed both the 5% and 10% geographic error limits relative to each recording's matched v5 baseline on **one of two recordings in each arm**. Always-one passed on zero of two, and dual stock and partner-on-miss each passed on two of two. Always-one and partner-on-miss use independently computed prior compact positions on projected factors. Stock dual uses its earlier complete saved-IQ runs. [Per-recording errors and all four v5 controls](scores.csv) · [c = 0 error chart](charts/c0/modifications.pdf) · [Fitted-c error chart](charts/fitted_c/modifications.pdf)

| Recording | Partner-on-hit error, c = 0 / fitted (km) | Dual-stock error (km) | Original v5 baseline error (km) | Partner-on-hit conditional RF RMS (Hz) |
|---|---:|---:|---:|---:|
| DS26-0168 | 4.154 / 4.154 | 0.805 / 0.796 | 1.515 / 1.551 | 75.10 / 75.10 |
| DS29-0174 | 0.783 / 0.893 | 0.793 / 0.806 | 0.885 / 0.917 | 98.35 / 98.43 |

## Measured host work

The policy used 18,062 physical receiver calls across 13,478 valid visits, 33.0% fewer than dual stock. Detector timing covers CI16 staging, one or two serial native calls and physical row assembly. A total of 8,550 visits (63.4%) finished within 20 ms wall. Of the 4,584 visits with two calls, one finished within that budget. The original dual-stock wall timings came from separate runs and host conditions. [Detector timing chart](timing.pdf) · [Per-visit times](timing.csv) · [Prior measured dual-stock timings](stock-timing.json)

| Recording | Detector P50 / P95 CPU (ms) | Detector P50 / P95 wall (ms) | Raw / compact wall (s) | Service wall / cgroup CPU (s) | Charged peak / swap (MiB) |
|---|---:|---:|---:|---:|---:|
| DS26-0168 | 14.48 / 33.67 | 15.20 / 36.85 | 100.87 / 97.01 | 200.69 / 267.07 | 512 / 0 |
| DS29-0174 | 13.70 / 32.34 | 14.04 / 34.82 | 117.06 / 76.75 | 197.39 / 220.97 | 512 / 0 |

This is an offline host replay of two roughly five-minute recordings, each with a known roof offer. Both services saturated the 512 MiB charged cgroup limit. The raw runs and tail clocks describe the saved-IQ service on this host. [Resource and service receipts](resources.json) · [Summary](summary.json)

Regenerate the charts and tables from the sealed evidence with `python -m tools.pipeline_eval.qualification.on_hit_waveforms_results publish`.

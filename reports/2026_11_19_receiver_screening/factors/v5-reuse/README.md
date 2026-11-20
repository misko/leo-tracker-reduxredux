# Reuse the full causal orbital bank in compact v5 reassociation

The candidate matched both full compact controls and the independent original v5 results exactly in both calibration arms. It cut complete worker CPU by 6.2% and 6.1% on the two recordings. Preparing and screening final reassociation took 24% and 36% less CPU. The number of coarse projections stayed at 124 per recording while the repeated whole-bank validations fell from 124 to zero. [Sealed predictions](receipt.json) · [Original v5 equality](original-checks.json) · [Work and timing](timings.csv)

Residual screening already builds a validated, immutable ECEF orbital bank. Final reassociation propagates the same ledger on the same time grid and starts with a fresh dictionary. The projection routine then checks the complete dictionary's shapes and finiteness on every coarse phase query. The candidate passes the existing immutable bank forward when the sorted TLE lines, UTC origin and exact float64 knots match. A mismatch uses the original bank factory and validates that bank once before projection. The final audit still checks the complete causal catalogue independently in TEME. [Implementation](../../../../tools/pipeline_eval/variants/v5_recovery_bank_reuse.py) · [Protocol](PROTOCOL.md)

The stage profile used the DS26-0002 recovery ledger, 11,143 usable rows on 381 knots, sixteen uniformly sampled times from the longest prepared native track, and two fixed positions near the supplied tile center. The same 31 phase queries took 4.538 CPU seconds with a plain dictionary and 3.002 seconds with an immutable bank. Every frequency and elevation byte matched. The one-time bank freeze took 0.165 seconds, and the original full ECEF propagation took 2.564 seconds. The independent SGP4 audit took 1.882 seconds. [Stage profile](profile.json)

## Repeat work and measured runtime

| Recording | CPU | Final preparation and screening CPU s, stock → reuse | Whole CPU s, stock → reuse | Whole wall s, stock → reuse | Numerical process peak RSS KiB, stock → reuse |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0036 | 20 | 28.86 → 22.03 | 162.08 → 151.96 | 174.59 → 174.39 | 1,443,488 → 1,419,644 |
| DS29-0082 | 22 | 27.79 → 17.73 | 126.03 → 118.35 | 144.80 → 127.32 | 1,321,908 → 1,309,084 |

Each worker used one numerical thread. Whole-worker timing includes kernel compilation, startup and all native observation preparation and position stages through the final decision. Each candidate ran once and consumed one bank from its own residual stage. Both controls propagated the ECEF grid twice and ran the raw audit once. Both candidates propagated ECEF once and produced the same raw audit evidence. They retained about 194–195 MiB of already validated orbital data between stages. Whole-worker peak RSS fell in both measured pairs. [Detailed performance and counters](timings.csv) · [Source and input lock](source-lock.json)

The two primary pairs completed 356 seconds after locking. The stress pair required 780 seconds remaining and had 724, so the experiment finished with the two primary recordings. [Optional stress receipt](optional-stress.json)

## Geography and frequency

| Recording | Zero-calibration error (km) | Fitted-calibration error (km) | Zero-calibration RMS (Hz) | Fitted-calibration RMS (Hz) |
| --- | ---: | ---: | ---: | ---: |
| DS26-0036 | 1.278 | 1.208 | 74.7609 | 74.6823 |
| DS29-0082 | 0.567 | 0.517 | 97.0036 | 96.6836 |

Both methods returned identical positions, conditional RF RMS, objective values, associated observation counts and recovery decisions. The position comparison includes the original v5 baseline, selective gap, omit-one-track and omit-tracks references. Both datasets use the same roof installation. [Geographic and frequency scores](scores.csv) · [Chart evidence](figures.json)

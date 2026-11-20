# Run the second antenna only after a primary pilot miss

The conditional detector skipped 3,027 of 23,280 physical receiver analyses across the two complete saved recordings, a 13.0% reduction from always processing both antennas. It recovered 1,385 gate-positive partner probes relative to processing one antenna. On the hard DS29 recording, the extra observations raised fitted position error from 0.728 km to 2.802 km. The two-condition calibration ablation used the same measured observations within each receiver policy. [Position charts](charts/README.md) · [Per-visit timing chart](timing.pdf)

## Genuine conditional detector calls

The original alternating schedule chooses the primary independently at each recorded RF center. An actual one-receiver native context tests that physical lane first. The canonical complete fractional projection alone decides whether to run the partner. A positive primary retains its full candidate row and leaves the partner's physical slot empty. A miss returns both complete candidate lists. Both physical IQ streams remain present in the archive reader. [Protocol](PROTOCOL.md) · [Source and dispatch lock](source-lock.json)

| Recording | Valid visits | One call | Two calls | Positive partners | Physical analyses / dual stock | Gate-positive probes, one → conditional → dual |
|---|---:|---:|---:|---:|---:|---:|
| DS26-0014 | 6,772 | 1,990 | 4,782 | 819 | 11,554 / 13,544 | 1,990 → 2,809 → 3,925 |
| DS29-0082 | 4,868 | 1,037 | 3,831 | 566 | 8,699 / 9,736 | 1,037 → 1,603 → 2,063 |

The observed conditional sequence and entire native documents match a separate projection from the authenticated measured dual-stock factors, down to the serialized bytes on both recordings. Every primary row matches the independently measured always-one service. All 3,027 primary-positive visits retain both original always-one probe arrays byte for byte. The preserved 1,904 hardware-invalid DS29 visits consume zero detector calls. A before-launch check on three authentic waveforms and two band-matched zeros covers both primary orderings and both gate paths. [Preflight](preflight.json) · [Whole-capture parity](parity.json) · [Prediction seal](prediction-lock.json)

## Position versus conditional frequency fit

Each pair is zero / fitted calibration. Both signal arms use actual measured detector packets, the same original 25 km offer, causal TLEs and installed compact solver. All three policies publish two positions per calibration arm and meet both the 5% and 10% allowances against original no-repair v5 on the same one of two recordings. [All four original v5 policies and calibration arms](scores.csv)

| Recording | Original no-repair v5 | Dual stock | Always one antenna | Second on primary miss | Conditional detector RF RMS |
|---|---:|---:|---:|---:|---:|
| DS26-0014 | 3.415 / 3.405 km | 0.472 / 0.755 km | 1.236 / 1.050 km | 0.870 / 1.308 km | 101.300 / 101.286 Hz |
| DS29-0082 | 0.567 / 0.517 km | 2.489 / 2.346 km | 0.728 / 0.728 km | 2.622 / 2.802 km | 85.451 / 85.407 Hz |

On DS29, adding partner observations decreased fitted conditional frequency RMS from 104.964 to 85.407 Hz while increasing fitted position error by 2.074 km. This RMS is conditional on the detector's own observations. Within the new policy, fitting calibration changed RMS by −0.013 and −0.044 Hz and increased geographic error by 0.438 and 0.179 km. [Distributions and timing](summary.json)

## Actual host timing

| Recording | Host CPU p50, one / two calls | Complete wall p50 / p95 | Wall ≤20 ms | Full worker wall | Detector CPU |
|---|---:|---:|---:|---:|---:|
| DS26-0014 | 14.70 / 25.76 ms | 24.86 / 33.42 ms | 1,919 / 6,772 | 169.76 s | 153.16 s |
| DS29-0082 | 14.72 / 26.06 ms | 25.74 / 35.01 ms | 979 / 4,868 | 130.98 s | 115.53 s |

Each native clock starts before staging the physical CI16 lane and includes the policy decision, any actual second native call and returning both physical slots. The one- and two-call timing groups contain different recorded visits. The earlier dual and always-one clocks retain their original host runs and load. Both new measured services returned within 450 seconds and used a charged peak of 512 MiB with zero swap and zero OOM kills. DS26 ran on CPUs12/13 and DS29 on CPUs14/15. These are host results from saved IQ. [Per-visit timing](timing.csv) · [Recorded prior and new resource receipts](resources.json)

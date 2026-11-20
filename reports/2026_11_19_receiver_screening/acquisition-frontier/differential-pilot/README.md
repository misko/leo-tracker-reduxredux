# Adjacent-symbol differential pilot timing

The blind raw-IQ scout recovered **5 of 16 primary misses** and **2 of 8 disjoint confirmation misses** through the original wide GLRT. All seven targets became the detector's largest-fractional-margin candidate. Their absolute CFO differed from the archived targets by at most 43.1 Hz. Stock and the shifted sham recovered none. The eight pre-existing target positives stayed gated with identical public candidate payloads under the real hint. Position was unmeasured at this detector boundary. [Stage figure](stage.pdf) · [Per-visit outcomes](stage.csv)

| Cohort | Visits | Stock top four ±2 / ±20 | Raw top four ±2 / ±20 | Raw top 16 ±2 / ±20 | Gated target stock / raw / sham |
| --- | ---: | ---: | ---: | ---: | ---: |
| Primary misses | 16 | 0 / 0 | 9 / 9 | 9 / 9 | 0 / 5 / 0 |
| Primary retained | 8 | 8 / 8 | 8 / 8 | 8 / 8 | 8 / 8 / 8 |
| Disjoint confirmation misses | 8 | 0 / 0 | 3 / 3 | 3 / 3 | 0 / 2 / 0 |

Only rank one was supplied to the native search. On the primary misses, three near-epoch proposals ranked below first, and one near rank-one proposal did not complete fractional verification. The confirmation panel had a third near-epoch proposal below first. None of the newly recovered real targets was in the weak archived margin stratum. The raw hint added seven unrelated gated candidates across two visits with unverified identities and displaced no unrelated stock positive on the audited receivers. [Full primary and confirmation counts](qualification.json)

## Why one symbol

One 4.4 µs OFDM symbol spans exactly 44 samples. The adjacent-symbol product preserves the complex relative coding of the eight Qin pilot carriers and removes the unknown initial carrier phase. Constant CFO contributes one common lag rotation to the correlation, removed by taking its magnitude. Reference products use the whole active block with exact 0 and ±⅓-sample frame residues, valid pairs from both sample endpoints, and a 17-symbol-roll control. The comparison uses observation pair masks at the raw visit edges. The original native scout uses the shorter 1/3/5-sample lags plus power. [Frozen measurement protocol](PROTOCOL.md) · [Qin et al., §VII](https://arxiv.org/html/2602.02627v1#S7)

Both signs' strong and weak synthetic pilots ranked first on both receivers. All four single-live-frame lanes also ranked first and passed the native gate at the plant CFO with the hint, up from zero stock. Alternating global frame sign preserved first rank. Zero produced no proposals. Gaussian noise and lower-edge CW produced no native positives. Upper-edge CW still produced six gated candidates across the two receivers with the hint, compared with eight from stock. [Per-lane synthetic controls](controls.csv) · [Complete native payloads](controls.json.gz)

## Boundary and cost

All 32 raw visits passed CI16 and metadata authentication. The stock replay matched complete wide factors on both receivers, and the ABI without hints matched its public payload. Only the designated target receiver got the raw or sham hint, selected without its archived timing. The other receiver reproduced stock factors. The hint could replace only the fourth ordinary center. Confirmation used later, disjoint visits within the same four recordings. The initial confirmation worker froze its complete eight-visit roster, then rejected the in-memory receiver ID tuple at the input checker before calculating any results. Replaying the exact frozen JSON roster supplied the canonical ID list and changed neither waveform nor implementation. One rejected input read and one identity-only diagnostic read preceded the eight admitted confirmation reads. [Primary input seal](input-lock.json.gz) · [Disjoint roster](confirmation-lock.json) · [Confirmation continuation](confirmation-execution.json)

| Primary host boundary | P50 CPU | P90 CPU | P50 wall | P90 wall |
| --- | ---: | ---: | ---: | ---: |
| Stock native, dual RX | 17.64 ms | 23.76 ms | 18.73 ms | 270.61 ms |
| Raw differential scout, dual RX | 14.32 ms | 18.33 ms | 27.40 ms | 194.51 ms |
| Scout plus hinted native, paired per visit | 32.14 ms | 38.80 ms | 61.29 ms | 363.96 ms |

CPU 4, single numerical thread at nice 10, with concurrent host load reflected in wall timings. The scout has 96 warm measurements. Paired totals use the first scout measurement of each visit and its corresponding native call. Warm isolated scout allocation peaked at 14.27 MiB with inputs and cached templates already present. The 20 ms dual-RX budget was exceeded on median CPU before archive reads, tracking or positioning. All work used existing saved IQ and local ext4 scratch. [Timing and allocation receipt](qualification.json)

To reproduce postprocessing without reading IQ, restore `plan.json` by decompressing the input lock into local scratch and copy the compressed measurements and the two confirmation JSON seals alongside it. The frozen scorer and original native ABI must be available at the paths and hashes specified by those locks. Run `python -m tools.pipeline_eval.qualification.differential_pilot_results --work "$work"`. The primary detector replay entry point is `differential_pilot_eval replay --case CASE --work "$work"`. The continuation entry point `differential_pilot_confirm --work "$work"` verifies and uses the already frozen confirmation roster before dispatching the same detector. [Evidence and source hashes](prediction-lock.json)

# Coherent ranking of folded CFO aliases

The coherent pilot-block scorer chose the correct absolute alias first on **8 of 8 held timing nominations within two samples**, compared with **5 of 8** for the four-sample lag. Both methods included the correct alias in their first two choices on all eight. The evidence-gated native mask saved **0.64%** of total coarse tap evaluations and did not improve median end-to-end CPU. Forcing the mask saved 6.34% of taps and dropped a genuine gated native factor. Position was unmeasured. [Stage chart](stage.pdf) · [Per-rank results](ranks.csv)

| Blind timing rank | Timing within two samples | Coherent top one | Short lag top one | Both top two |
| --- | ---: | ---: | ---: | ---: |
| 1 | 3 | 3/3 | 1/3 | 3/3 |
| 2 | 4 | 4/4 | 4/4 | 4/4 |
| 3 | 1 | 1/1 | 0/1 | 1/1 |
| 4 | 0 | — | — | — |

The worst tuned absolute error on these eight coherent hits was 13.01 kHz. The result depends on the timing nomination and applies to eight scored nominations across 16 later saved-IQ visits. It does not establish general top-two recall. [Raw timing and alias roster](input-lock.json.gz) · [Machine-readable outcomes](qualification.json)

## Voltage evidence

The 44-sample phase gives a carrier frequency modulo 227.27 kHz. The scorer projects each in-band alias and seven short residual offsets against the complex Qin voltage over four consecutive symbols. Eight such blocks sample both halves of the pilot. Taking squared magnitude per frame and block removes the unknown common complex phase at that aperture. Exact 0 and ±⅓-sample reference phases cover the three frame residues. The two-half evidence threshold compares energy-normalized correlations for the exact and 17-symbol-roll pilot waveforms. This differs from the previous single short-lag estimate and from the phase-only mask, and also differs from confirming a fully formed native candidate without changing its CFO. [Frozen method and gates](PROTOCOL.md)

Signed strong, weak, one-live-frame and ±790 kHz plants ranked their absolute alias first on both receivers. Both native masks preserved all four single-frame plant targets. Zero produced no alias, and white noise failed the block evidence gate. Both CW controls produced confident alias scores on both receivers. Lower-edge CW produced no native positives, and upper-edge CW retained its six hinted positives in both masked arms. The coherence gate is therefore evidence about ranked support and cannot serve as the receiver's pilot detector. [Synthetic controls](controls.csv)

## Measured native pruning

| Actual native arm | Missed targets recovered | Retained controls kept | Mask applied | Other gated factors lost |
| --- | ---: | ---: | ---: | ---: |
| Stock wide | 0/12 | 4/4 | — | — |
| Differential timing and all CFO bins | 1/12 | 4/4 | — | 0 |
| Evidence-gated top two aliases | 1/12 | 4/4 | 1/16 | 0 |
| Forced top two aliases | 1/12 | 4/4 | 10/16 | 1 |

The disabled overlay reproduced every stock hinted payload. The evidence-gated overlay also kept identical public payloads on these 16 visits, including the one where its mask applied. The forced mask removed the factor at epoch 919, fractional offset −0.4381 samples and −87,888.1 Hz on DS29-0519 visit 2180, RX 0. The all-bin fractional margin was 0.11816 against the original 0.025 gate. The two forced shortlist CFOs were about −320.45 and −739.00 kHz. This counterexample is a genuine unpruned gated factor of unverified identity. [Native factor and work comparisons](stage.csv) · [Counterexample payload](DS29-0519.json.gz)

| Host CPU after reading dual CI16 | Median | P90 |
| --- | ---: | ---: |
| Coherent rank-one score, one designated receiver | 0.708 ms | 1.033 ms |
| Timing scout plus unpruned detector | 49.65 ms | 58.26 ms |
| Timing scout, coherent score and evidence-gated native detector | 50.90 ms | 58.06 ms |
| Timing scout, coherent score and forced native detector | 50.45 ms | 59.18 ms |

The warmed one-thread comparison used CPU 22 at nice 10 and the same dual-RX windows. It charges only the leading coherent rank for the actual native option. Coarse physical taps totalled 62,050,296 with masking disabled, 61,655,352 with the evidence gate and 58,116,564 with forced screening. The original 20 ms visit budget was exceeded on this host. The waveforms, input projection and other receiver remained authenticated throughout. [Paired timing](qualification.json) · [Native build and ABI](build-lock.json) · [Evidence seal](prediction-lock.json)

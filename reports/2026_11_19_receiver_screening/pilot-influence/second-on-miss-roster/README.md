# Second stock antenna only after a primary miss

The receiver alternates its primary physical antenna within each RF. It runs the stock four-center search on that antenna. A true fractional margin gate on any primary candidate suppresses the second detector call. A miss keeps both complete stock candidate arrays. The suppressed partner keeps its original physical slot with an empty candidate array. Both IQ streams remain present in the saved recordings. [Frozen protocol](PROTOCOL.md) · [Source and request seal](plan.json)

All **63,982** valid visits that were positive on either stock antenna stayed positive in the projected stream. The partner restored **16,283** visits that always-single missed. Across **146,268 valid visits** and **2,720 capture exclusions**, **98,569** visits required the partner. The policy schedules **244,837** antenna calls, **16.3% fewer** than the **292,536** calls required by full stock. It retains **1,143,931/1,409,765** stock candidate rows, including **850,187/967,341** non-gated rows. Each retained antenna's complete stock array and physical metadata were checked against the frozen document. [Per-recording support](support.csv) · [Physical and dispatch audit](packet-audit.json)

The 22 recordings use stored-factor projection followed by actual compact phase-release fits. All numerical requests preserve the original causal catalogue and offered tile, and run both calibration arms with identical support. Each fit is pinned to one of CPUs16–19 under 512 MiB, zero swap and a 210-second deadline. This roster measures compact fit time after acquisition. The direct saved-IQ study measures detector clocks on the two overlaps. [Independent direct IQ study](../second-on-miss-whole/README.md)

The full saved-IQ runs on DS26-0014 and DS29-0082 emitted byte-identical native documents to these two projected inputs. Both calibrated position endpoints and conditional RF RMS values also matched exactly. The 22 frozen native and dispatch hashes independently reproduced from the sealed stock inputs. [Direct IQ parity](direct-iq-parity.json) · [Source and input reproduction](input-reproduction.json)

## Geographic results

All 22 compact fits published in both calibration arms. Second-on-miss met the original no-repair v5 +5% and +10% geographic allowances on **11/22** in each arm. Always-single reached **8/22** at both allowances and in both arms. Stereo stock reached **12/22** and **13/22** at zero calibration, and **13/22** at both allowances with fitted calibration. The per-case rows include signed differences and symmetric tolerance flags. [Per-case effects](scores.csv)

| Policy on all 22 | Error median / P95, zero | Error median / P95, fitted |
|---|---:|---:|
| Second-on-miss | 0.867 / 1.755 km | 0.893 / 1.752 km |
| Always-single | 0.855 / 1.786 km | 0.815 / 1.797 km |
| Stereo stock | 0.774 / 1.543 km | 0.776 / 1.437 km |
| Original no-repair v5 | 0.739 / 1.760 km | 0.724 / 1.769 km |

| Second-on-miss subset | Error median / P95, zero | Error median / P95, fitted | Within +10%, zero and fitted |
|---|---:|---:|---:|
| DS26 | 0.946 / 1.507 km | 0.977 / 1.660 km | 4/11 each |
| DS29 | 0.704 / 2.171 km | 0.692 / 2.267 km | 7/11 each |
| Earlier difficult six | 1.086 / 2.406 km | 1.271 / 2.540 km | 0/6 each |
| New lower-edge pair | 0.952 / 1.285 km | 0.943 / 1.267 km | 1/2 each |
| Direct IQ overlap pair | 1.746 / 2.535 km | 2.055 / 2.727 km | 1/2 each |

The scheduled recordings cover one surveyed roof. The direct pair overlaps the 22 and includes one of the earlier difficult six. The geographic figures include the original four v5 options, which use capture-era inputs. [Zero-calibration figures](charts/c0/modifications.pdf) · [Fitted-calibration figures](charts/fitted_c/modifications.pdf) · [Summary including the four original options](summary.csv)

## Conditional frequency fit and service clocks

Second-on-miss conditional RF RMS median/P95 was **90.899/110.038 Hz** at zero calibration and **90.820/109.916 Hz** with fitted calibration. Stereo stock achieved **85.483/104.123 Hz** and **85.497/104.113 Hz**. Always-single achieved **90.680/109.989 Hz** and **90.549/110.112 Hz**. All **63,982** projected gated antenna rows appear in the observed compact support counts. Stereo stock had 95,305 gated antenna rows. The retained per-visit positivity counts and per-antenna support count different observations. [RF and fit objectives](scores.csv)

Across 22 actual compact services, wall median/P95 was **63.87/86.22 s**, and CPU median/P95 was **58.13/76.13 s**. Peak charged memory was **393.2 MiB**. The compact service clocks cover both arms. The saved-factor roster has blank detector clocks. [Worker clocks and memory](resources.csv) · [Prediction seal](prediction-lock.json) · [Score seal](score-lock.json)

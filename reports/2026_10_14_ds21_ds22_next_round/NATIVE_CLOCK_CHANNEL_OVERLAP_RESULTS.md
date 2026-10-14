# Native-clock posterior deficit by channel, receiver and time

The DS22-001 full-versus-own-half likelihood deficit is uneven across channels, receivers and time. CH2/RX0, CH3/RX1 and CH4/RX1 contribute strongly. This localizes the statistical disagreement; it does not prove a hardware calibration cause, identify correct satellite assignments, or show that another clock model will improve location.

The same three original matched native-clock training winners, full bank, frame and priors were used as in `NATIVE_CLOCK_POSTERIOR_OVERLAP_RESULTS.md`. No fit, reference or held data was used. Every channel was included. Time intervals were fixed in advance as 30-second half-open blocks anchored at observation-frame zero, before inspecting state-dependent loss. Positive differences mean the full model predicts worse than that channel's own-half winner.

| Channel | Windows | Full minus half NLL | RX0 NLL difference | RX1 NLL difference | Full minus half signal mass | Full-clutter/half-signal windows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 467 | +94.269 | +68.071 | +26.199 | −11.541 | 18 |
| 2 | 510 | +416.146 | +338.748 | +77.399 | −60.177 | 63 |
| 3 | 486 | +215.230 | +26.601 | +188.629 | −38.508 | 52 |
| 4 | 348 | +186.089 | +46.359 | +139.730 | −23.644 | 38 |
| 5 | 414 | +67.450 | +21.604 | +45.847 | −5.527 | 9 |
| 6 | 426 | +81.392 | +72.664 | +8.728 | −3.185 | 4 |
| 7 | 308 | +10.552 | +12.306 | −1.754 | −2.414 | 3 |
| 8 | 270 | +46.286 | −1.272 | +47.559 | −3.304 | 7 |

CH2/RX0 loses 49.676 effective signal windows, CH3/RX1 loses 34.188 and CH4/RX1 loses 17.831. The entire fixed time partition is shown below, including negative differences; none of these bins was used to select or exclude observations.

| Seconds | CH1 | CH2 | CH3 | CH4 | CH5 | CH6 | CH7 | CH8 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0–30 | +3.46 | +3.54 | +2.33 | +4.75 | 0.00 | +5.54 | +1.78 | 0.00 |
| 30–60 | +0.67 | +1.73 | +8.33 | −12.72 | 0.00 | +1.35 | +1.28 | 0.00 |
| 60–90 | +2.11 | +0.50 | +0.76 | −0.36 | +1.48 | +0.21 | −2.80 | −1.08 |
| 90–120 | −1.35 | +4.51 | −3.04 | −2.85 | −3.20 | +1.61 | −0.74 | +2.49 |
| 120–150 | +9.70 | +3.38 | −10.46 | −2.06 | +0.81 | +18.24 | +5.22 | −0.50 |
| 150–180 | +45.70 | +67.10 | +73.22 | +16.74 | +7.28 | +16.66 | 0.00 | +6.20 |
| 180–210 | +22.98 | +31.31 | +133.36 | +24.33 | +33.99 | +23.55 | +3.54 | −21.39 |
| 210–240 | +1.41 | +39.23 | −32.59 | −44.89 | +12.12 | +8.45 | +10.27 | +6.56 |
| 240–270 | +8.21 | +182.30 | +18.73 | +29.90 | −2.90 | −11.25 | −1.73 | +52.68 |
| 270–300 | +1.38 | +82.55 | +24.58 | +173.26 | +17.88 | +17.04 | −6.26 | +1.33 |

These totals mix different window counts and assignment patterns. CH2's last minute contributes +264.85 NLL, CH3's 150–210 seconds +206.58, and CH4's last 30 seconds +173.26. The heterogeneous pattern motivates inspecting residuals and assignment support within prespecified channel/receiver groups. A single shared correction can still produce channel-dependent effects through differing satellite geometry and available observations; this audit alone does not exclude that explanation. Prior expanded-calibration fits remain unpromoted.

Source `33422ff6d` and its numerical dependencies were frozen before execution. Observation-only partition tests cover frame-zero anchoring, negative times, half-open boundaries, all-window coverage and invalid metadata. Stable posterior arithmetic retains the earlier tested subnormal handling. Actual channel, receiver and time likelihood partitions close against the original band totals; all saved own-view objectives and reconstructed posteriors replay. Runtime was 32.266 seconds, six objective evaluations, zero optimizer fits under a 120-second internal cap.

Complete per-stratum overlap, confidence and transition accounting is in `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-native-overlap-strata-v1/report.json`, SHA-256 `9db94b36cc30abf445786fa132e7a2daba155ea44f5494c8610d5af52f50f283`. Half views share full discovery and initialization; this is not an independent discovery comparison.

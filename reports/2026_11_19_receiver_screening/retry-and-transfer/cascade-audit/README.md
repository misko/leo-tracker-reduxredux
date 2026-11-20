# A sparse original-detector audit of the fast receiver

The frozen audit threshold escalated **0 of 20 held recordings**. The one development pair needing escalation had 33.75% disagreement among audited probes with a passing winner. The strongest held disagreement was 28.57%. This study tests the rule on existing recordings at one roof. [Route lock](route-lock.json) · [Protocol](PROTOCOL.md)

## Held position results

| Policy | Original escalations | Published | Within +5% of v5, zero / fitted | Within +10% of v5, zero / fitted | Median error km, zero / fitted |
| --- | ---: | ---: | ---: | ---: | ---: |
| Always fast | 0 | 20/20 | 11 / 12 | 12 / 12 | 0.745 / 0.745 |
| Frozen audit | 0 | 20/20 | 11 / 12 | 12 / 12 | 0.745 / 0.745 |
| Rate-matched random | 0 | 20/20 | 11 / 12 | 12 / 12 | 0.745 / 0.745 |
| Always original | 20 | 19/20 | 19 / 19 | 19 / 19 | 0.728 / 0.703 |
| Truth oracle ceiling | 9 | 20/20 | 19 / 20 | 20 / 20 | 0.531 / 0.628 |

The oracle maximizes the paired +10% count across both calibration arms, then publication and geographic error. The zero-budget oracle agrees with always fast. In the separate rank sweep, four switches selected by audit disagreement brought both arms from 12 to 15 of 20 within +10% of v5. The same-count manifest permutation reached 12 in both, and its expected count over uniform selections was 13.4 in either arm. The truth rank reached 16 with four switches. This sweep describes the existing held cases. A deployable cutoff still needs an independent evaluation. [Both calibration distributions](charts/index.html) · [Rank sweep](stage.pdf) · [Rank data](rank-sweep.csv)

All 14 new original fits returned both calibration arms. The primary original comparator uses the ordinary 210-second endpoint, including the archived DS26-0168 timeout. The longer same-input retry remains available as a separate receipt. The four original v5 options are retained per recording and calibration setting. [Endpoint seal](endpoint-lock.json) · [Archived retry](archived-retries.jsonl.gz) · [Original v5 scores](original-v5-references.csv)

Always-fast median RF RMS was 87.86 Hz with zero calibration and 87.92 Hz with fitted calibration. Median geographic error rounded to 0.745 km in both arms, with P95 decreasing from 1.504 to 1.343 km. The original comparator's median RF RMS was 77.99 and 78.03 Hz across its 19 fixes. [Per-arm position and frequency scores](scores.csv) · [Summary](summary.csv)

## What the selector sees

Every recording runs the complete fast four-region acquisition. The physical manifest selects one valid visit per complete block of 32 valid stereo visits. Both receivers at a selected visit also get an original-detector call. The rule counts a shared winner only if the two passing winners agree within 0.2 µs in circular epoch and 1 kHz in literal CFO. The audit counts positive support unique to either detector and separates CFO aliases from literal agreement. Its archive contains only the selected signal comparisons, including both antennas and the independently bound RF centers. [Audit roster and work seal](source-lock.json)

On the held recordings at least one detector passed on 3,002 of 8,398 audited receiver probes. There were 2,464 literal agreements, nine CFO-alias agreements, and 98 other paired disagreements. Another 256 probes passed only on fast and 175 passed only on original.

The development label compares the fast and original compact endpoints in both calibration settings. A pair needs escalation if either publication state differs or the two coordinates differ by more than 0.5 km in either arm. The deployed decision uses the audit disagreement fraction alone. The zero- and fitted-calibration position arms share the same route, observations, candidate sets and fit budgets. Held geography enters the scorer after the route and paired endpoints are sealed.

The earlier prefix policy chose between four and five fast timing regions from pilot recurrence within a short prefix. The earlier retry policy chose whether to repeat a failed receiver lane within an individual visit. This study uses complete recording-level fast coverage and an independent sample of original detector calls before selecting a recording-level compact endpoint. [Earlier timing-region choice](../../receiver-choice/prefix-evidence/README.md) · [Earlier receiver retry](../retry-evidence/PROTOCOL.md)

## Detector work and compact fits

The held audit uses 4,199 original calls on 134,635 valid stereo visits, or 3.12%. The detector CPU model rises from 2,617 s for always fast to 4,830 s for the audit rule, an 84.6% increase. The model uses authenticated complete fast detector timings on 18 held recordings and projects the two fresh cases from the matching recording series. It measures original per-visit costs on DS26-0237 and DS29-0082 and projects unsampled recordings from the matching series anchor. The CPU totals omit capture pacing, IQ buffering, and I/O. [Per-recording measured input and modeled cost](costs.csv)

The modeled cascade buffers the recording's I/Q so the audit can use its completed physical manifest. It retains the original-detector audit outputs until release. Each escalation would add the remaining original detector calls and a second complete compact fit to the already spent fast and audit work. The always-fast receiver and the cascade both make one initial compact fast fit per recording.

The hypothetical four-switch rule would spend an estimated 17,144 detector CPU seconds across the 20 holds, 6.55 times always fast. Its four second compact fits used 313 CPU seconds in their individual measured services. Always original is projected at 70,929 detector CPU seconds for the same cohort.

## Reproduce the benchmark

Regenerate the fit score tables from the authenticated worker receipts and rerender the position gallery from the sealed evidence.

```sh
study=reports/2026_11_19_receiver_screening/retry-and-transfer/cascade-audit
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval.qualification.cascade_audit_results \
  --work /srv/bulk/leo-dev/cascade-audit-20261119
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval benchmark --study "$study" \
  --out /var/tmp/cascade-audit-benchmark
```

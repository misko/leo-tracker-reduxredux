# Four-donor consistency did not improve empty-lane nominations

Across three held physical recordings, the four-donor screen retained **5,523 of 7,007** originally nominated empty short lanes. At the same query count, the screen retained **198** primary carrier-and-arrival matches and **4,904** queries that also returned empty under ALGO08v3. The deterministic hash control retained **242** matches and **4,795** installed-empty queries. Uniform selection at the same per-recording counts would also retain **242.0** primary matches in expectation. [Frozen protocol](empty-graph-outer-donors-protocol.md) · [Candidate-only prediction seal](measurements/empty-graph-outer-donors-plan.json.gz) · [Scored receipt](measurements/empty-graph-outer-donors-score.json)

Each forecast uses two consecutive original donors from its own side of the target, all on one candidate Graph piece, physical receiver lane and signed alias lift. Both outer donors are within four hardware seconds of the target; the original inner donors are within two. Each side extrapolates signed CFO and absolute pilot phase on the 40,000/3 sample lattice. The forecasts must agree within ±2,250 Hz and six samples. The original two-donor query itself stays fixed. We sealed the surviving observation IDs and both forecasts before opening the installed packets for scoring. [Original interpolation and phase controls](empty-lane-arrival.md)

| Held selection | Queries | Installed-empty queries | Installed-positive queries | Primary joint hits | Primary precision / recall | Historical loose hits | Loose precision / recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| Original | 7,007 | 6,076 | 931 | 313 | 4.47% / 14.92% | 475 | 6.78% / 22.64% |
| Four-donor screen | 5,523 | 4,904 | 619 | 198 | 3.59% / 9.44% | 276 | 5.00% / 13.16% |
| Equal-count hash | 5,523 | 4,795 | 728 | 242 | 4.38% / 11.53% | 361 | 6.54% / 17.21% |

The primary window is ±250 Hz and ±2 samples on the same installed winner. The historical loose window is ±2,250 Hz and ±6 samples. Precision divides by issued queries. Recall divides by all **2,098** installed winners on candidate-empty short lanes across the held cases, including lanes without a nomination. Among issued queries with an installed winner, primary agreement was 33.6% for the original, 32.0% for the screen and 33.2% for the hash. Thus the gate failed to enrich for installed positives and failed to improve agreement conditional on an installed detection.

## Recording and ownership checks

Each triplet is original / screened / equal-count hash. Installed owner partitions use the ordered signed ALGO08v3 maps. The respective `c = 0` and fitted-`c` owner counts and hits were identical on the two authenticated maps.

| Recording | All candidate-empty short lanes | All installed winners on those lanes | Queries | Primary joint hits | Installed-owned primary hits | Installed-owned loose hits |
|---|---:|---:|---:|---:|---:|---:|
| DS30-0049, development | 1,105 | 104 | 300 / 251 / 251 | 11 / 8 / 9 | 8 / 5 / 7 of 44 | 11 / 7 / 9 of 44 |
| DS30-0019, held | 6,110 | 595 | 2,196 / 1,682 / 1,682 | 107 / 75 / 82 | Unknown | Unknown |
| DS30-0086, held | 5,196 | 564 | 1,342 / 939 / 939 | 90 / 46 / 62 | 65 / 34 / 47 of 323 | 108 / 55 / 74 of 323 |
| DS30-0274, held | 6,125 | 939 | 3,469 / 2,902 / 2,902 | 116 / 77 / 98 | Unknown | Unknown |

For unowned installed winners, primary hits were 3 / 3 / 2 of 60 on 0049 and 25 / 12 / 15 of 241 on 0086, in both arms. The 0086 screen removed 297 installed-empty queries while losing 31 primary owned hits; the same-count hash removed 334 installed-empty queries while losing 18. Across held records, 786 of 1,484 rejections lacked a nearby complete quartet. Of the remainder, 606 disagreed on phase alone, 38 on carrier alone and seven on both; 47 failed a phase-rate or alias check. The median delay to the second future donor was 1.063–1.065 seconds across the four recordings, with a largest delay of 3.903 seconds. This is a lower bound on when evidence becomes available because the original retrospective Graph also uses future observations.

Agreement between donor trajectories supplies evidence about carrier and arrival **if** a pilot is present. An installed-empty lane has no independently observed emission label. The four cases do not establish that absence or presence can be inferred from agreement, and no receiver, waveform, orbit or positioning job was run. The tested screen does not justify narrowing the original nominations.

## Reproduce

Run `python -m reports.ALGO08.v3.empty_graph_outer_donors SNAPSHOT predict` with the retained first-30 metadata, original candidate Graph build and the two earlier carrier-plan archives pinned in the source. The held carrier plan is retained locally with the [original rescue study](empty-graph-rescue.md). Seal the compressed prediction before running `python -m reports.ALGO08.v3.empty_graph_outer_donors SNAPSHOT score PLAN.gz PLAN_SHA256`. The scorer checks published native identities, the archived phase-query digest and the verified owner witnesses when available. `PLAN_SHA256` for the paired results above is `623b64dfa46910d8f594ea720fe5576808f2a8bc75d5125dfaf853235508e297`.

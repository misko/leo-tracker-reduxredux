# Where the first 71 DS30 pairs miss half-time

The second quartile by installed elapsed time contributes the largest share of the remaining wall gap. It accounts for **245.988 s of the 706.253 s net deficit**, or **34.8%**, and all 18 pairs miss half-time on both wall and CPU. The longest quartile contributes 178.891 s, and the shortest 106.569 s. Fitted-calibration losses at 1 km account for 26.6% of the signed gap. The recordings that stayed within 1 km under both builds account for 42.0%. Both comparisons keep every timed original and its observed outcome. [Verified pairs and reducer](field_first71_deficit.py) · [Sealed case ledger](measurements/field-first71-deficit.json.gz)

## Measured timing

Wall speedup is **1.667× summed** and **1.725× at the paired median**, with 7,074.739 s installed and 4,243.622 s successor through the sealed boundaries. The gap is 716.920 s across misses less a 10.667 s surplus. CPU speedup is **1.581× summed** and **1.621× at the paired median**, with 6,187.502 CPU s installed and 3,913.356 CPU s successor. The analogous CPU gap is 820.114 s less a 0.509 s surplus, or 819.605 CPU s. Both summed and paired-median gates miss 2× on both clocks. Ten pairs individually meet wall half-time, four meet CPU half-time, and four meet both. [Both gates and case identities](measurements/field-first71-deficit.json.gz)

| Installed wall rank | Pairs | Installed wall range (s) | Positive wall deficit (s) | Wall surplus (s) | Net wall gap (s) | Net CPU gap (s) | At half wall / CPU / both |
|---|---:|---:|---:|---:|---:|---:|---:|
| Q1 | 17 | 1.726–89.262 | 107.513 | 0.944 | 106.569 | 124.331 | 4 / 4 / 4 |
| Q2 | 18 | 90.017–107.018 | 245.988 | 0.000 | 245.988 | 264.658 | 0 / 0 / 0 |
| Q3 | 18 | 107.382–121.123 | 177.367 | 2.562 | 174.805 | 202.558 | 1 / 0 / 0 |
| Q4 | 18 | 121.153–148.460 | 186.052 | 7.161 | 178.891 | 228.059 | 5 / 0 / 0 |

Each signed deficit is successor time minus half its own installed time. Quartiles sort on installed wall alone and use integer rank cuts. Paired-median speedup is the inverse of the median successor-to-installed ratio. The six pairs missing a two-sided geographic score include four both-withheld pairs and two installed solver failures with a successor fix. The four both-withheld pairs are exactly the four that meet both individual timing gates. All six retain their original clocks and scope. [Measured cases and outcomes](measurements/field-first71-deficit.json.gz)

## Independent 1 km split

Each arm is classified using its two published positions and the existing sealed references. A loss crosses from within 1 km to farther than 1 km. A gain crosses in the opposite direction. A pair missing either position stays unscored. No installed fix within 1 km was followed by a missing successor fix on this prefix. Every recording contributes once per calibration. A loss in either calibration occurred on 20 recordings, with 194.675 s net wall deficit, or 27.6%. These are retrospective groups. [Scored pair ledger](measurements/field-first71-deficit.json.gz)

| Signed threshold comparison | `c=0` pairs | Fixed gross / net wall gap (s) | Fitted pairs | Fitted gross / net wall gap (s) |
|---|---:|---:|---:|---:|
| Lost coverage | 16 | 152.863 / 150.301 | 19 | 190.076 / 187.515 |
| Gained coverage | 6 | 44.742 / 44.742 | 6 | 46.254 / 46.254 |
| Both within 1 km | 22 | 293.806 / 288.686 | 23 | 301.363 / 296.243 |
| Both beyond 1 km | 21 | 191.523 / 189.482 | 17 | 145.241 / 143.199 |
| Unscored | 6 | 33.986 / 33.042 | 6 | 33.986 / 33.042 |

Installed versus successor produced 65 versus 67 fixes in each arm. At `c=0`, the within-1-km count moved from 38 to 30. With fitted `c`, it moved from 42 to 31. The within-2-km count moved from 64 to 58 in each arm. The stage sensitivity below holds those published results fixed. [Calibration scores](measurements/field-first71-deficit.json.gz)

## Timing lever and next discriminating comparison

The earlier 20-pair study identified original input-buffer reuse as the largest then-runnable exact change. The first-64 study priced several projections, including a combined donor, without locating the deficit by installed-time rank. On the first 71, net savings have to reach a broad cohort. Granting free acquisition on every audited case in the longest quartile would put just **20/71** at wall half-time. The median requires **36/71**. [Earlier field reachability](field-speed-reachability.md) · [First-64 staged donor pricing](first64-producer-transfer.md)

Only the fixed chronological first 64 have matched stage receipts here, including all 18 recordings in Q2 and 16 in Q4. The all-71 sensitivity changes only these 64 candidate clocks and credits zero to the final seven. Starting from the actual 706.253 s net gap, a uniform cut in the audited 2,397.007 s of acquisition needs **29.46%** for the summed wall gate and **21.99%** for the median wall gate. Across the same denominator, reducing acquisition outside native callbacks alone needs **54.17% / 42.40%**, native callback wall alone **64.60% / 49.73%**, and solve wall alone **68.28% / 61.48%**. These are separate models with nested scopes. Even ideally removing all 655.907 s of audited producer CPU and turning each of those seconds into one second less wall would leave **50.346 s** at the sum. That bound prices producer CPU only. Any exposed demand-wait change needs its own measured elapsed saving inside acquisition. [Exact scope ledger](measurements/field-first71-deficit.json.gz)

If an exact acquisition change can plausibly affect enough of the charged boundary, the next useful comparison is a fresh matched trial on a naturally resident original near the second quartile, using signed source admission and complete verification. In Q2 the median pair misses by **12.618 wall s** and **13.291 CPU s**. Reaching half wall on a median Q2 acquisition fraction would require **30.12%** of that acquisition clock. Charge the candidate’s complete output and independently meter authenticated acquisition, native callbacks, and producer and demand wait. A byte-identical detector packet and both unchanged calibration products would establish timing transfer relative to the frozen successor. Installed accuracy remains an additional comparison. A faster producer-thread clock alone supplies no paid wall result. [Stage and timing evidence](measurements/field-first71-deficit.json.gz)

The reducer reads the sealed local first-71 export `d981a774…`, seal `1e628323…`, original plan, sealed first-64 accuracy and stages, and references for the final seven. It reads **1,970,794 logical bytes** per complete extraction. All worker and scientific clocks came from those receipts. The comparison used only saved metadata and acquired no timing lease. [Reproducer](field_first71_deficit.py)

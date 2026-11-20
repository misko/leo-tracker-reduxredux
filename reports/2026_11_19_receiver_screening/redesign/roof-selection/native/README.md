# Unchanged native smooth clock on all 159 DS26 roof recordings

The smooth-clock receiver published **23/32** fixes on the recordings excluded from the original common panel. Original no-repair v5 published **16/32**. Combining the newly measured rows with the sealed common127 results gives **135/159** native fixes and **143/159** original no-repair v5 fixes. Both calibration arms have those publication counts. The comparison used the same supplied roof region throughout. [Two-arm gallery](charts/index.html) · [Full per-recording data](scores.csv) · [Excluded recordings](excluded-scores.csv)

## What the common panel changes

| Cohort | Smooth-clock fixes | Original no-repair fixes | Original selective-gap fixes | Original one-omitted fixes | Original two-omitted fixes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Common127 | 112/127 | 127/127 | 127/127 | 127/127 | 127/127 |
| Excluded32 | 23/32 | 16/32 | 14/32 | 11/32 | 5/32 |
| All159 | 135/159 | 143/159 | 141/159 | 138/159 | 132/159 |

The selected common roster gives original no-repair v5 an 11.8 percentage-point coverage lead over smooth clock. On the full roster that lead is 5.0 points. The excluded recordings give smooth clock a 21.9-point coverage lead. On those 32 rows there are 13 paired publications, ten native-only, three original-only, and six where neither publishes. Original no-repair v5 recorded 14 failures, one timeout and one absent input. The one truly unavailable native capture is DS26-0172. Its frozen authority provides no native archive or causal catalogue. It stays in both denominators and no worker launches for it. The other 31 workers completed, with eight withheld on scientific gates. [Replay and statuses](fresh-lock.json) · [Frozen request plan](plan.json)

| Cohort and calibration | Smooth clock median / P95 (km) | Original no-repair median / P95 (km) | Native within 10% of original / paired fixes |
| --- | ---: | ---: | ---: |
| Common127, `c=0` | 1.560 / 4.481 | 0.988 / 3.084 | 36/112 |
| Common127, fitted `c` | 1.397 / 4.802 | 0.999 / 3.126 | 43/112 |
| Excluded32, `c=0` | 1.579 / 4.123 | 0.867 / 2.711 | 4/13 |
| Excluded32, fitted `c` | 1.535 / 3.622 | 0.844 / 2.694 | 5/13 |
| All159, `c=0` | 1.579 / 4.474 | 0.980 / 3.155 | 40/125 |
| All159, fitted `c` | 1.413 / 4.780 | 0.988 / 3.266 | 48/125 |

The median and P95 are conditional on each method's published fixes. The 10% test uses both published coordinates for the same recording and calibration arm. On all attempts, the fitted count is 48/159. A fix where original v5 failed contributes to coverage and its measured error distribution. The full panel shows those additional opportunities and the lower paired accuracy of smooth clock. [All roles, status counts and distributions](summary.json)

For the 31 fresh workers, fitted `c` reduced paired conditional RF RMS by a median of 25.10 Hz. Geographic error improved on 16 of 23 paired publications, with a median paired change of −0.072 km. Across all159 there were 158 paired RF estimates and 135 paired geographic fixes. Their median paired changes were −24.29 Hz and −0.026 km. These metrics use different conditioning, and both appear in the score files.

## Worker boundary and verification

The 32-case roster was derived from the authenticated panel set difference before loading any original scores. The inference request contains native factors, the frozen track configuration, capture clock and causal TLE bindings, and the original region. The worker starts at complete archived GLRT and rebuilds Graph before the unchanged native smooth-clock fit. It receives no truth or original position. Fresh attempts ran at low priority on CPUs 12 and 16 in 146.90 s of batch elapsed time. Their median worker time was 5.99 s CPU and 8.34 s elapsed. Peak RSS was 151.0 MiB and peak virtual memory was 386.0 MiB under a 512 MiB virtual limit. The 127 historical results were reused without rerunning the receiver.

The join verified each common native row against the exact frozen request, native file and catalogue digests, tile, observation digest and worker boundary. It checked 636 original v5 execution receipts against the frozen published score source and original request identities. Original failures, timeouts and the absent-input receipt were checked alongside completed positions. [Analysis sources](analysis-sources.json) · [Per-role receipt audit](original-v5-audit.json) · [All159 predictions](positions.jsonl.gz) · [Excluded32 predictions](excluded-positions.jsonl.gz)

## Reproduction

The replay uses the existing archived factors, Bubblewrap and the repository Python environment. The scoring command reads the existing archived original execution receipts. Both commands write evidence to the same destination.

```sh
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
scratch=$(mktemp -d /tmp/ds26-selection.XXXXXX)
nice -n 10 taskset -c 12,16 .venv/bin/python -B -m tools.pipeline_eval.qualification.roof_selection_native \
  --work "$scratch/work" --out "$scratch/evidence"
.venv/bin/python -B -m tools.pipeline_eval.qualification.roof_selection_native_results \
  --out "$scratch/evidence"
.venv/bin/python -B -m tools.pipeline_eval figures --panel screening \
  --variant ds26_selection_native_clock --evidence "$scratch/evidence" --out "$scratch/charts"
```

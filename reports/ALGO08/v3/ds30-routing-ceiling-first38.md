# Choosing between ALGO08v3 and the candidate on the first 38 DS30 recordings

Even with the surveyed answers available in advance, a free choice between the two existing builds achieved at most **1.330× summed speedup** while matching ALGO08v3's full position-error distribution in both calibration arms. Matching fix count and coverage at only 1 and 2 km allowed **1.491×**. Running the candidate on all 38 gave **1.656×** with fewer fixes within 1 and 2 km.

| Frozen enrollment prefix | Fastest choice matching both full error curves | Fastest choice matching fix counts and coverage at 1 and 2 km | Fraction of current candidate time allowed for 2× summed, full curves | Fraction allowed for 2× summed, 1 and 2 km |
|---|---:|---:|---:|---:|
| First 8 | 1.273× | 1.483× | 32.42% | 65.91% |
| First 11 | 1.313× | 1.502× | 33.05% | 62.17% |
| First 30 | 1.258× | 1.435× | 11.56% | 56.93% |
| First 38 | 1.330× | 1.491× | 36.76% | 64.99% |

On 38 recordings, installed ALGO08v3 took 3,671.856 s. The fastest route that preserved both full curves selected the candidate on 25 recordings and took 2,760.339 s. The 1 and 2 km route selected it on 29 and took 2,462.857 s. The half-time target was 1,835.928 s. An ideal router with unchanged outputs would need roughly **2.72× additional candidate acceleration** for full coverage, or **1.54×** for the two distance thresholds, to reach the summed target. The comparisons at different prefix sizes show why these estimates can change as more recordings arrive. [Selected cases, optimality bounds, and time-fraction brackets](measurements/ds30-routing-ceiling-first38.json)

Each recording gets one build choice, shared by the fixed-zero and fitted calibrations. Gains on one recording can compensate for losses on another. The constrained choice uses the fastest available whole run at each feasible assignment, with no charge for choosing it. Coverage includes every recording. The full comparison checks every observed distance threshold in each arm and both fix totals. Missing positions cannot contribute to finite-distance coverage.

The integer program independently checks the chosen route against every requested threshold and checks that its elapsed total agrees with the optimization's lower bound within 10 microseconds. The first 11 reproduce the earlier exhaustive search over 2,048 routes. Uniform time-fraction estimates hold candidate outputs and installed runtimes fixed, with a bracket narrower than 0.01 percentage points. At the feasible end of every reported bracket, the chosen route also reached the paired-median target. On the 38-recording panel the median candidate-to-baseline wall ratios at that endpoint were 0.232 for the full-curve route and 0.387 for the two-threshold route. At the other end of each bracket, even the optimal summed time exceeds half the baseline. A real selection method must pay for its decision and operate without the surveyed answer. An improved receiver or solver that changes the candidate predictions can change this bound. [Earlier exhaustive comparison](ds30-oracle-routing.md) · [Scorer](ds30_routing_ceiling.py)

```sh
python -m reports.ALGO08.v3.ds30_routing_ceiling "$campaign_root/rows-with-relocations.jsonl" --limit 38
```

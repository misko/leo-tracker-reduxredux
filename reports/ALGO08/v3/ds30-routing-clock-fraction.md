# Candidate clock reduction required for 2× on the frozen first 64

The largest uniform candidate wall-time multiplier is **0.506921183**. Each candidate recording would need to run in **50.6921% of its measured wall time**, a **49.3079% reduction** or **1.973× candidate acceleration**. This assumes the same outputs, unchanged ALGO08v3 clocks, and a zero-cost chooser that knows the measured outcome and clock of each build in advance.

The boundary chooses **44 candidate** and **20 installed** runs. The selected installed runs take 1,784.052 s. The selected candidate runs drop from 2,705.768 s to 1,371.611 s, giving **3,155.663 s** in total, or exactly half of the 6,311.327 s installed total. The paired median time ratio is **0.319723**, or **3.128×** speedup, so the same multiplier is sharp for both gates. The route has 60 of 64 fixes in each calibration arm, compared with 58 for installed, and zero deficits at all 118 finite thresholds per arm. It changes the chosen build on six recordings relative to the optimum at current clocks.

Each feasible route has elapsed time equal to its installed fallback time plus the uniform multiplier times its selected candidate time. At a proposed multiplier, the integer program maximizes saved time under both original coverage constraints. Rational ratio updates lead to the boundary fraction **13,716,112,511,437,386,303 / 27,057,682,689,921,930,278**. The final feasible route and its exact dual certificate both give savings equal to half the installed total. Every route that could reach half-time uses at least one candidate clock, so increasing this multiplier raises the elapsed time of each such route above the target. The archived endpoint certificates reverify 1,784.052 s for zero-time candidate calls and 4,483.791 s at current clocks.

This is a retrospective requirement on per-recording through-exit wall clocks with both builds' recorded outputs held fixed. It uses only the frozen first-64 receipt. The source and compressed proof include the chosen recording IDs, exact median ratio, rational updates and endpoint certificates. A focused exhaustive fixture checks the ratio optimum against every small-panel route, with an additional fixture where the summed optimum misses the median gate. [First-64 field bound](ds30-routing-first64.md) · [Protocol](ds30-routing-clock-fraction-protocol.md) · [Scorer](ds30_routing_clock_fraction.py) · [Exact receipt](measurements/ds30-routing-clock-fraction.json.gz)

```sh
nice -n 15 taskset -c 3 python -m reports.ALGO08.v3.ds30_routing_clock_fraction \
  reports/ALGO08/v3/measurements/ds30-routing-first64.json.gz
```

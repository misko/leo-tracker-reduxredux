# A perfect choice between the two measured builds on the first 64 DS30 pairs

A zero-cost chooser with perfect foreknowledge achieves **1.408× summed wall-time speedup** while preserving ALGO08v3’s full empirical error CDF in both calibration arms. The exact fastest eligible route takes **4,483.791 s**, which is **1,328.127 s above** the 2× target of 3,155.663 s. Choosing the faster measurement on every recording regardless of accuracy achieves **1.679×** and falls 603.522 s short of half-time. Preserving both curves adds 724.606 s to that unconstrained minimum.

| Choice | Installed / candidate | Total wall (s) | Summed speedup | Paired median speedup for that choice | Fixes per arm | Largest finite CDF deficit, c=0 / fitted |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ALGO08v3 throughout | 64 / 0 | 6,311.327 | 1.000× | 1.000× | 58 / 64 | 0 / 0 |
| Candidate throughout | 0 / 64 | 3,764.932 | 1.676× | 1.732× | 60 / 64 | 12 / 11 |
| Fastest measured choice on each recording | 1 / 63 | 3,759.185 | 1.679× | 1.732× | 60 / 64 | 12 / 11 |
| Fastest choice preserving both full curves | **20 / 44** | **4,483.791** | **1.408×** | **1.614×** | **60 / 64** | **0 / 0** |

One build is selected per recording, shared by both calibrations. Each CDF keeps the same denominator of 64. A no-fix contributes zero at every finite threshold, and the fix total is checked separately. Both strict curves had zero deficits at all 118 observed finite thresholds per arm. For the unconstrained route the worst deficits were 12 fewer recordings at 1.191 km with c=0 and 11 fewer at 0.963 km with fitted c. Comparisons allow a gain on one recording to offset another recording’s loss. The strict paired median above belongs to the summed-optimal assignment. The unconstrained per-record minimum is a lower bound on every individual time ratio, and even its paired median misses 2×.

The LP proposed a route and eight active row multipliers. Reconstructing those multipliers from exact count coefficients and the exported decimal clocks yields an integer certificate. The 219 distinct count constraints use the union of both builds’ finite thresholds plus fix counts, with duplicates and gain-only inequalities omitted. If a route has choices \(x_i\), gains \(w_i\), and counts \(Ax\ge b\), any nonnegative multipliers \(\lambda\) bound its gain above by \(\sum_i\max(0,w_i+(A^\mathsf{T}\lambda)_i)-\lambda^\mathsf{T}b\). Exact verification gives the same primal and dual elapsed total, **44,837,907,277,606,427,388 units of \(10^{-16}\) s**. These units represent the exported decimals and make no claim about physical clock resolution. The first 11 reproduce the archived 2,048-route exhaustive result exactly, selecting the same mask at 771.353 s for 1.313× summed speedup. An initial pure branch-and-bound attempt hit its CPU3 cap before yielding a certificate. [Earlier exhaustive report](ds30-oracle-routing.md)

Granting the candidate zero run time with unchanged positions and keeping installed measured cost gives an exact minimum of 1,784.052 s. The 1.408× bound applies to the two measured builds and their observed outputs.

The fixed combined export and seal include the verified DS30-0452 relocation. Enrollment follows the original smoke-first order through DS30-0282, immediately before DS30-0218. The scorer checks both complete-file digests and decodes evaluation and reference objects only for the preselected case IDs. An exploratory schema inspection parsed the reference envelope to list its top-level keys without examining case values. No post-prefix position or survey values were used for this comparison. The receipt contains the ordered cases, original attempt and raw identities, exact clock units, scored distances and the row-order dual certificates. Export line digests exclude their line endings. All work used existing metadata on CPU3, without an acquisition, position fit or Gauss lease. [Frozen protocol](ds30-routing-first64-protocol.md) · [Scorer](ds30_routing_first64.py) · [Case-level receipt](measurements/ds30-routing-first64.json.gz)

```sh
nice -n 15 taskset -c 3 python -m reports.ALGO08.v3.ds30_routing_first64 \
  --plan "$campaign_root/plan.json" --export "$snapshot/rows.jsonl" \
  --seal "$snapshot/seal.json"
```

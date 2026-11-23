# How much independent support do the three apertures offer?

On **112 dense nonanchor lanes**, 65 had an installed rank-zero factor. The released prefix matched 49, the distributed primary matched 48, and at least one matched 54. On the **80 dense nonanchor lanes common to all three apertures**, the three-way union matched 35 of 43 installed rank-zero factors. The best observed single fixed aperture, centered on that prefix, matched 33. [Distributed factors](measurements/distributed-aperture.json.gz) · [Centered factors](/var/tmp/leo-v3-centered-primary/reports/ALGO08/v3/measurements/centered-primary.json.gz)

| Common lanes | Installed reference held fixed | Reference present | Prefix | Centered | Distributed | Prefix + centered union | Prefix + distributed union | Three-way union |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Dense, 112, two apertures | Rank zero | 65 | 49 | — | 48 | — | 54 | — |
| Dense, 112, two apertures | Highest margin | 65 | 49 | — | 48 | — | 54 | — |
| Dense, 80, all three | Rank zero | 43 | 31 | 33 | 30 | 34 | 34 | 35 |
| Dense, 80, all three | Highest margin | 43 | 30 | 30 | 29 | 32 | 33 | 34 |
| Weak, 36, all three | Rank zero | 36 | 30 | 28 | 31 | 33 | 33 | 35 |
| Weak, 36, all three | Highest margin | 36 | 27 | 29 | 32 | 31 | 32 | 34 |

The join checks same receiver, visit, RF, edge, native metadata and I/Q digest. It also checks the common installed factors and the released prefix outputs. A match uses ≤2 wrapped timing samples and ≤250 Hz signed CFO. Highest-margin installed references use the lower rank when margins tie. Three weak and three dense references select rank one in the common three-way panels. Equal counts under different reference rules can cover different observations. [Census](aperture_factor_union.py) · [Machine-readable results](measurements/aperture-factor-union.json)

Each fixed aperture uses one call per lane. A union uses the installed factor to score whether any of the already computed alternatives matches. Selecting the highest observed margin across all three candidates instead requires three calls and matched **32/33** dense and **32/33** weak references for rank-zero/highest-margin, respectively. On the full 112-lane dense panel, choosing the higher margin across two calls matched **50/52**, versus the union’s **54/54**. The census estimates a possible benefit from aperture complementarity. It does not establish an input-only choice that realizes that benefit in one call. No detector, I/Q reader or localization solver ran for this census.

```sh
python3 -B reports/ALGO08/v3/aperture_factor_union.py \
  reports/ALGO08/v3/measurements/distributed-aperture.json.gz \
  /tmp/leo-centered-primary-run05/complete.json
```

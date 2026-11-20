# Outside evidence from an orbit-split halo

The 75 km halo put its full forced solution outside the 25 km tile on **4/4** fresh synthetic omissions and **1/4** containing offers. The two disjoint orbit groups and the full fit never cleared the same face by all six nominal radii, so the veto changed **none of 11** decisions. Both calibration arms retained **2/4** valid synthetic publications and **0/4** false synthetic publications. Both previously known false roof fixes survived. [Protocol](PROTOCOL.md) · [Per-case scores](scores.csv)

## Two fresh synthetic sites and epochs

Each site has one simulated complete native GLRT recording and four randomized offers. The recordings are at different geographic sites and at 0.75 and 3.25 h after the authentic causal catalogue's collection time. Positive signed margins are inside the supplied tile. The columns report the forced 75 km position's signed margin to the original tile for `c = 0` and fitted `c`. Both arms share the observations and assignment inventory. [Frozen request lineage](roster.json) · [Fresh figures](fresh-synthetic/figures.json)

| Site | Offer | True margin | Full halo margin, km | Full halo gate | Final smooth publication |
|---|---|---:|---:|---|---|
| 1 | Centered | +12.5 km | +11.90 / +12.09 | Weak geometry | Withheld |
| 1 | Near inside | +1.5 km | −5.86 / −8.73 | Weak held support | Withheld |
| 1 | Near omission | −1.5 km | −25.00 / −25.00 | Weak held support | Withheld |
| 1 | Far omission | −15 km | −10.37 / −10.32 | Weak geometry | Withheld |
| 2 | Centered | +12.5 km | +12.09 / +12.27 | Published | 0.497 / 0.237 km error |
| 2 | Near inside | +1.5 km | +1.78 / +1.73 | Published | 0.497 / 0.237 km error |
| 2 | Near omission | −1.5 km | −1.22 / −1.27 | Published | Withheld |
| 2 | Far omission | −15 km | −14.72 / −14.77 | Published | Withheld |

At site 2 the full halo tracked truth to about 0.497 and 0.237 km in the two calibration arms for all four supplied squares. Both satellite folds also went beyond the east face on the far omission. The least-certain nominal margin was −1.05 km after allowing for fitted radius, so it issued no confident veto. The near omission had nominal margins farther below zero. At site 1, comparing just the signs of full forced points would flag all omissions and incorrectly flag the valid near-inside offer. The halo's frozen support gate withheld all four site-1 estimates. [Position and frequency distributions](summary.json) · [Full fits and independent split diagnostics](native_halo_orbit_consensus.jsonl.gz)

## Exact archived diagnostics

| Known false offer | Native smooth and this halo | Previous exact-input tests |
|---|---|---|
| DS26-0102, truth 1.889 km outside | Both published, 4.548 / 4.678 km error | Held exterior published. Orbit influence withheld. |
| DS26-0070 reserve near omission | Both published, 14.549 / 14.964 km error | Local radius and recentered 50 km verification published. Orbit influence and held exterior withheld. |
| Standalone-majority southern near omission | Both withheld on native smooth geometry | Exact prior majority and subscan tests published, 5.558 / 5.600 km error. |

On DS26-0102 the full estimate and both orbit groups stayed inside the wrong offered square, with positions clustered about 10 km west of its center. On DS26-0070, one group stayed near the center while the other moved about 24 km west. The fitted group disagreement yielded an ambiguous exterior vote. The ordinary smooth publications on both roof diagnostics exactly reproduced the earlier sealed endpoints and Graph. [Roof diagnostic figures](archived-roof/figures.json) · [Earlier near-edge and recenter studies](../../refinement/boundary-roof/README.md) · [Orbit influence](../../redesign/orbit-influence/README.md) · [Held exterior](../../recovery/exterior-evidence/README.md)

The southern stored diagnostic uses the exact complete native factors, track configuration, tile and latest causal TLE from the earlier majority test. Its v5 receiver also used earlier causal snapshots and its own Graph and fitting stages. The near false output survived that receiver's 899/1,072 compatible-point majority and the archived subscan method. Native smooth already withheld independently with 1.565 km forced error in each arm. The larger halo's forced fit was about 2.95 km outside the tile and 1.484/1.518 km from truth, with weak position geometry. This case supplies no decision change attributable to the halo. [Majority diagnostic figure](archived-majority/figures.json) · [Majority qualification](../../next/standalone-majority/README.md) · [Subscan interval study](../../next/edge-interval/README.md)

## Receiver and timing boundary

The worker authenticated complete stored native GLRT factors, reconstructed a single anonymous Graph, and ran the same native smooth oscillator in both the original and 75 km supplied-center squares. The wider region is unconstrained with respect to the original tile. In admitted halo fits, each assigned satellite and all its tracks belonged to only one deterministic half. The halves fitted their own position and nuisance terms under matching calibration and fixed halo identities and aliases. Their samples were disjoint by satellite. Their orbit assignments and causal catalogue were shared with the full halo fit, so the result is a conditional consistency test on this capture. This differs from moving a 50 km square to a tentative fix, perturbing one orbit at a time, or evaluating a separate held exterior hypothesis. At present the veto's nominal agreement criterion yields ambiguity on every tested query. [Scientific and deployment source lock](source-lock.json)

All 11 jobs finished without failures or timeouts in **63.72 s** on CPUs 8 and 9, with one numerical thread per worker. Supervisor worker wall median / P95 / maximum was **10.72 / 14.07 / 14.78 s**. Median wall for the ordinary fit was 4.63 s and for the extra halo fit 3.55 s. The four split refits together added 0.212 s median across the six admitted halo fits. Peak RSS was 218,852 KiB and virtual address space reached 457,996 KiB under the existing 512 MiB limit. Both frequency-fit arms and timing stages are recorded separately. [Prediction seal](prediction-lock.json) · [Both calibration plots](charts/manifest.json)

A new run draws a fresh seed. The original hexadecimal seed is in the sealed evaluator for exact simulator regeneration through `region_halo_trial.synthetic`. Use a verified native-lean deploy bundle and a new output directory. [Sealed simulator seed and labels](evaluator.json)

```sh
halo_trial=$(mktemp -d /tmp/leo-region-halo.XXXXXX)
timeout --kill-after=2s 720s taskset -c 8,9 .venv/bin/python \
  -m tools.pipeline_eval.qualification.region_halo_trial \
  --work "$halo_trial/run" --bundle /path/to/deployed-source \
  --output "$halo_trial/report"
.venv/bin/python -m tools.pipeline_eval.qualification.region_halo_results \
  --work "$halo_trial/run" --output "$halo_trial/report"
```

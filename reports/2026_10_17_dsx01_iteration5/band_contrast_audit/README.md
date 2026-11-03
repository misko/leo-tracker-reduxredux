# Conditional frozen-band contrast assay

Revising only the frozen band constants modestly improves fitted-c held support:795→805/1909 (+40/−30), while requested held support stays66/80. The held frequency NLL improves by85.236. Thus the constants are a measured conditional fit bottleneck, but this assay does not restore another requested held observation.

The exact TRAIN-selected blocked-production endpoint supplies every physical coordinate, timing, residual clock, q and candidate. Only two receiver high-band corrections vary. The c=0 control changes only the RF coefficient before the same assay; it remains conditional on fitted-c production discovery and all its other learned coordinates. No geography, timing, clock, q, identity selection or reference coordinates are tuned or consulted.

The protocol was persisted before loading the real training context: per receiver, update±10000Hz at500Hz spacing, then±500Hz at25Hz spacing around the best coarse point, clipped to the original search box and public absolute alias-branch bounds. Receivers are separable because q is fixed and their high-band rows are disjoint. The score is exact shared lane likelihood plus the **absolute** contrast prior relative to zero: `originalJ + sum(laneNLL_new-laneNLL_original) + .5*(sum(new_offsets²)-sum(original_offsets²))/50000²`. The existing global prior is replaced once; no donor prior or prior on the update is added. Both selected updates were persisted before held scoring.

| c arm | RX1 update Hz | RX2 update Hz | Absolute RX1/RX2 Hz | TRAIN J before→after | Calls |
|---|---:|---:|---:|---:|---:|
| fitted-c | -25 | 2925 | -15056.269 / 37691.817 | 24678.312→24525.580 | 159 |
| zero-c | -425 | 2225 | -15456.269 / 36991.817 | 27534.529→26822.716 | 159 |

| c arm | Method | Train associated | Held associated | Held NLL | Held new/lost | Requested held |
|---|---|---:|---:|---:|---:|---:|
| fitted-c | baseline | 1088/2073 | 795/1909 | 23241.168 | +0/−0 | 66/80 |
| fitted-c | profile | 1108/2073 | 805/1909 | 23155.932 | +40/−30 | 66/80 |
| zero-c | baseline | 530/2073 | 405/1909 | 25196.099 | +0/−0 | 54/80 |
| zero-c | profile | 694/2073 | 500/1909 | 24801.587 | +168/−73 | 54/80 |

Fitted-c requested windows remain20/26,20/28,26/26; conditional c=0 windows remain17/26,13/28,24/26. The c=0 profiles improve broader held coverage405→500 and held NLL25196.099→24801.587 without increasing requested held coverage54/80. These are fixed-state frequency/calibration effects; location is unchanged and no localization improvement follows.

Each arm uses159 counted calls: one original shared objective,156 noncached lane densities, one full zero-update density check and one full endpoint density check. There are166 profile requests and10 cache hits per arm. Both arms have the same200-call/120-second allowance and finish their profile calculations in about0.10seconds. Initial context replay adds one separately declared strict shared-objective audit; initial full-cohort scoring adds four density calls and two prediction orbit queries. The independent no-fit replay separately reports one context audit, four direct shared objectives, four metadata prediction queries and four scoring densities. No continuous KKT or full-joint admission is claimed for a grid endpoint.

All fixed denominators remain:2073train+1909held+6boundary=3988source winners;58train+80held+0boundary+555untested other-source=693challenge observations. The other16096context observations remain untested. No original observation is replaced or credited via an alternate peak.

Four component tests pass: zero update nests the original objective exactly; separable scores match a directly reconstructed shared model with the absolute prior once; held CFO cannot change training selection; and cached/density accounting respects the cap and retains the incumbent. Actual endpoint replay reproduces both direct shared objectives/NLLs, frozen predictions and original125Hz classifier arrays. Old sealed reports are unchanged.

![Training-only contrast profiles](profiles.png)

This local frozen-state assay does not test joint band/timing/clock readjustment or drift. Its modest fitted-c gain leaves that question open; it is not a full-pipeline c=0 or independent-position validation result.

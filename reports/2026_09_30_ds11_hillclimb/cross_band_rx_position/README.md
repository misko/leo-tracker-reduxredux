# Cross-band drift geographic screen: primary gain misses frozen gate

The primary RX1-fixed allocation lowers eight-scan median position error from
3,108.162m to2,836.483m (8.74%) with5/8 paired wins. It fails the predeclared
10% median reduction and6/8-win gate. All three allocations have qualified
outputs for every scan; none passes. This version does not advance to the
remaining scans or replace the original IID default.

| Allocation | Qualified outputs | Median m | Mean m | P90 m | Paired wins |
|---|---:|---:|---:|---:|---:|
|Original IID|8/8|3108.162|3481.538|6046.037|—|
|RX1 unchanged, correct RX0 (primary)|8/8|2836.483|3394.452|6051.650|5/8|
|Symmetric|8/8|3142.913|3495.112|6054.209|1/8|
|RX0 unchanged, correct RX1|8/8|3491.110|3528.868|6056.291|4/8|

| Original scan index | IID m | RX1-fixed m | Symmetric m | RX0-fixed m |
|---|---:|---:|---:|---:|
|0|765.072|1053.144|774.870|508.466|
|4|3510.342|3143.814|3549.178|4023.661|
|8|5270.648|5285.099|5272.417|5259.921|
|12|1183.767|750.276|1203.809|1777.889|
|16|2153.140|2102.607|2154.167|1454.829|
|20|2705.981|2529.152|2736.649|2958.559|
|24|5917.578|5910.480|5933.171|5955.012|
|28|6345.775|6381.049|6336.633|6292.610|

The RX1-fixed arm was designated primary from held prediction before geographic
scoring. Its median/mean gains coexist with a slightly worse P90 and the loss
of scan0's sub-km fix, while scan12 becomes sub-km. The other allocations are
retained sensitivity controls, not candidates to choose scan-by-scan using
reference error. This reinforces that differential clock predictability does
not establish a physically correct allocation or dependable position gains.

All96 worker processes finish with exit0, no timeouts or retries;95 optimizer
starts qualify. One scan4 symmetric start has an abnormal line-search exit and
remains unqualified. Every scan/arm has other qualified starts. Each process
has a90second cap; the maximum observed worker wall time is20.35seconds. At
most three single-thread workers run concurrently. All24 endpoints are selected
by highest qualified training score and sealed before geographic scoring.

Qualified starts reveal multiple basins: scan16 symmetric spans784.49m in EN;
scan20 spans559.77m,551.40m and319.60m for primary, symmetric and RX0-fixed
respectively. These are not global-optimum guarantees. The fixed training-score
selection remains unchanged; no basin is selected by geographic accuracy.

Two component tests pass for correction immutability, original mask/time and
unpaired-track preservation, and rejection of invalid targets/shapes. Verification
rehashes sources and checks46,386 allocated correction values against the
frozen fixed-position arrays, all96 receipts and numerical qualifications,
training-only selection and geographic aggregation. The optimizer is not
independently rerun. No new IQ, RF collection, orbit replacement or cross-scan
position pooling occurs. The reference remains an unsurveyed exposed-site
coordinate, so these are development errors, not surveyed accuracy claims.

Plan SHA256: `b15a478b9ad2a62e723f3f11ded91c9fcd9c146a923740965f5876eb7607db00`.
Full endpoints, failures and selection precede the scored `outcome.json`.

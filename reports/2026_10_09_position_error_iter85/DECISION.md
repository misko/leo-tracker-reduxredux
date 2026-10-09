# Completed hard60 ablation: what contributes to position accuracy

**148/148 recordings completed: DS16 63, DS17 51, DS18 34.** Both worker
processes exited0. All3,256 fresh downstream attempts are retained, including
unqualified fits and their prescribed fallbacks. There were no input failures
or excluded recordings. Production remains unchanged.

## Mean position error

| Configuration | DS16 fitted-c km | DS17 fitted-c km | DS18 fitted-c km | Pooled fitted-c km | Pooled c=0 km |
|---|---:|---:|---:|---:|---:|
| B0: deployed hard60 | 5.964450 | 4.477043 | 4.422188 | 5.097594 | 5.346353 |
| B1: distinct regions only | 1.782396 | 1.551480 | 4.422188 | 2.309262 | 2.569152 |
| B2: joint clock/position only | 5.635765 | 4.063324 | 3.785292 | 4.668802 | 4.963720 |
| B3: regions + joint fitting | 1.422679 | 1.125847 | 3.785292 | 1.863155 | 2.163561 |
| B4: B3 + timing-based pruning | 1.100451 | 0.941063 | 2.930371 | 1.465914 | 1.847849 |
| B4W: B4 + wider clock prior | 1.078602 | 0.903526 | 2.774181 | 1.407796 | 1.824765 |
| B5: B4W + RF time | 1.065141 | 0.898735 | 2.771922 | 1.399896 | 1.824159 |
| B6: B5 + satellite slope0.25 | 1.017307 | 0.864203 | 2.739331 | 1.360148 | 1.738896 |
| B7: B5 + satellite slope0.5 | 0.979007 | 0.819111 | 2.691656 | 1.317354 | 1.666471 |

All means include every member and operational fallback. No isolated diagnostic
rescue replaces a difficult recording. The below1km pooled-mean goal remains
unachieved. [Full distributions and coverage](RESULTS.md) and
[controlled contrasts](CONTROLLED_EFFECTS.md) retain all refit-control rows.

![Mean position error across the ladder](means.png)

## Which changes earn their improvement?

**Region retention has the clearest standalone case.** It improves two scans,
regresses none and leaves146 unchanged in both arms. Those two rescues reduce
pooled fitted-c mean by2.788332km. Joint fitting alone does not repair either
catastrophic region error; after region retention, it reduces mean by another
0.446107km but regresses42 scans versus B1. Search and model fitting should not
be conflated.

**Timing-based pruning adds a substantial measured benefit.** Versus its
same-start unpruned refit C3, mean improves0.397241km:51 improve,30 regress,
67 tie. It removes candidates with absolute inferred relative timing over5s,
using fitted hypotheses rather than reference positions. This empirical gate
still needs independent validation, particularly for legitimate timing errors.

**Later flexibility has smaller incremental returns.** Clock-prior relaxation
improves0.052783km against its narrow-prior refit C4 (81 improve/66 regress/1 tie).
The simple ladder difference is0.058117km because an extra refit itself contributes
about0.005335km. RF-time terms improve only0.007900km against RF-off C5
(87/60/1). Satellite slope0.5 improves0.082542km against same-start RF refit C6
(100 improve/48 regress). These are consumed-corpus effects, not population estimates.

B4 captures approximately96.1% of B7's mean improvement over B0. B7 improves
another0.148560km over B4 and has the best pooled mean among the tested rows.
That supports comparing a lean B4 deployment candidate with B7, not claiming
all later components are individually necessary. The planned full-combination
removal study is **not yet performed**; the forward ladder is order-dependent.

## Tail errors and regressions remain important

B7 fitted-c median0.863677km, p952.269173km, worst53.400741km. It improves118
scans and regresses30 versus B0;27 regress by more than100m, with the largest
regression1.250014km. Sixty-one errors exceed1km; one exceeds5km and10km;
none exceeds100km. Both B7 arms have148/148 independently qualified raw fits,
without fallback. Other rows retain their failures explicitly in RESULTS.md.

| Diagnostic member | B0 km | Regions only B1 km | Joint only B2 km | Both B3 km | Full B7 km |
|---|---:|---:|---:|---:|---:|
| DS16-046 | 265.276544 | 1.807182 | 266.428219 | 1.003851 | 0.942161 |
| DS17-008 | 152.839550 | 3.635825 | 153.348007 | 3.536675 | 2.205054 |
| DS18-022 | 58.693871 | 58.693871 | 56.466255 | 56.466255 | 53.400741 |

The DS18 failure needs further search/model work. Its separate ordinary common-bank
single-case recovery is not part of this ablation. Historical reference-guided
starts remain diagnostic and were not used. These cases are chosen for retrospective
explanation only, never to choose an operational model or parameter.

![Full error distributions](distributions.png)

## Controls, runtime and validation

- All148 B0 errors reproduce the saved deployed full-cohort baseline. B0/B1 reuse
  immutable search receipts; this is not a cold end-to-end rerun of the grid.
- All148 zero-c C5/B5 controls have exactly identical objectives and matching
  convergence. Static-c and RF-time locks are checked in the reporter. C5 with
  fitted-c isolates static-c freedom; B5 versus C5 fitted-c isolates RF-time freedom.
- Candidate inventories, pruning decisions and shared starts are fitted-derived,
  so these are conditional matched c ablations. They are not independent c-specific
  search pipelines. The configured spatial prior remains unchanged and explicit.
- Frequency RMS improves89.154→67.204Hz from B0 to B7 fitted-c, reported separately
  from localization. Better frequency fit alone is not a deployment criterion.
- Mean wall time for loading and all22 fresh downstream fits is29.04s per recording;
  mean load time11.80s. This excludes archived regional/grid computation and is not
  a production-latency claim. Detailed per-stage timing is in summary.json.
- Ten synthetic model/report tests pass; Ruff passes. All1,466 frozen input/source
  hashes match. The DS18 manifest still hashes to
  `894a6f4b7055e5f6bd602f94ce3acf7f722f204c68c2b521a06dfd6be35a7516`.
- DS16 original48/added15 and DS18 consumed24/other10 remain separately reported.
  All evaluated data are consumed development; other10 does not mean unseen.
  No reserve outcomes or new RF collection were used.

## Deployment discussion

Prioritize qualifying region retention: its two catastrophic rescues and zero
observed regressions are strong development evidence. For broader improvement,
compare B4 (regions, joint fitting and pruning) with best-mean B7. Before promoting
either, finish the removal study, freeze a candidate for independent reserve
evaluation, and cold-replay the integrated standard pipeline. Then shadow naturally
arriving scans and verify convergence/fallbacks, actual runtime, and WebUI PNGs
including the longest16-track limit. No new default is deployed by this report.

![Individual scan errors](per-scan.png)

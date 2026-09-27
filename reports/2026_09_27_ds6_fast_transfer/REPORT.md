# DS6 transfer of the two DS5-selected fast aggregators

The published DS6 V2 position products passed the blind-input audit for all 43
sessions. Every product uses the same Sacramento 250 km prior configuration, sets
`known_position_used_for_inference` false, and has 400 evaluated Sacramento cells.
The selected tuple was replayed against its signal objective surface. Although the
published documents also contain reference-evaluation fields, extraction copied
only signal-selected coordinates, RF RMS, and support counts. The inference artifact
was sealed before the roof pose authority was read.

| Transferred method | 43 singles median / p90 | Five group8 median / p90 | Full43 |
|---|---:|---:|---:|
| Inverse RF RMS² mean | 6.528 / 6.710 km | 3.018 / 3.821 km | 1.978 km |
| Lowest RF RMS 75% mean | 6.528 / 6.710 km | 3.437 / 4.319 km | 2.680 km |

The methods are identical on single-session units by definition. Inverse RF RMS²
performed better on group8 and full43 in this transfer. These results use methods
selected on DS5 without DS6 retuning.

All 43 source searches stopped at their 400-point budget and report
`search_complete=false`. The source location resolution is 12.5 km, and aggregated
accuracy does not turn those source searches into converged estimates. Roof fixture
receiver mapping is provisional; RF phase centers, directed baseline, elevation,
altitude, and survey uncertainty are unmeasured.

Sealed artifacts are under `/srv/bulk/leo/experiments/ds6-fast-transfer/`.

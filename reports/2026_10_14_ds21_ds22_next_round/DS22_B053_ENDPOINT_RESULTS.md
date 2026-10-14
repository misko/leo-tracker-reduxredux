# DS22-053: endpoint continuation resolves one acceptance failure

The prescribed two-call original-B control completed in 36.220 seconds. Both new fits passed unchanged strict stationarity. The previously rejected lower-score start became eligible, reducing the configured-reference distance from 52.953753 to 26.515094 km. This is a separate diagnostic experiment with two additional fits; the original cohort matrix is preserved.

| Endpoint start | Objective | Independent KKT | Configured distance km |
| --- | ---: | ---: | ---: |
| Original accepted incumbent | 44417.351025676 | accepted in original matrix | 52.953753 |
| Incumbent repeat | 44417.351025676 | 0.000072485 | 52.953753 |
| Originally rejected start 5 | 43852.108912505 | 0.000741476 | 26.515094 |

Start 5 originally had KKT 0.002084660 at its 25 km disk boundary and was correctly excluded. Its new objective is effectively unchanged, but its independently checked KKT now passes the original 0.001 threshold. This demonstrates an acceptance/optimization limitation in the original result, rather than a newly improved likelihood model. The original incumbent remained eligible in both arms. The challenger beats it by 565.242113 objective units; its NLL is 43290.264430 and prior penalty 561.844483.

The new full-view result is below the existing B low/high distances of 78.290403/33.184760 km, but remains far from the localization goal. Those halves share discovery and initialization; they are not independent half-only controls. The reference is the existing configured station, whose DS22 continuity remains unconfirmed, so these distances are not verified accuracy.

The trigger was training-only: exactly one rejected full-view endpoint had lower objective than the accepted incumbent. Both original physical states and their original winning disks were preserved, with no projection exceeding 1e-12. Each call used the unchanged fitted-c original B fitter, a 20-second optimizer cap and 600-iteration cap. No failed scientific call was rerun in its old namespace. Both new calls and their selections were sealed before reading the reference; no held observations were used.

Source: `e1e9e1bf5` (control), `e3d4a02e1` (post-seal comparison). Control and evaluator tests passed, with Ruff clean. Numerical evidence is in `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-b053-endpoint-control-v1` and `ds22-b053-endpoint-comparison-v1`. Terminal SHA256: `db511e999708efaf15167ac986cc81dc7084b38d37a7579c53b5dc5b8c63cb42`; seal SHA256: `3d3f835b41d8aa250f89735e72dcdd585e3424a9f593012fb76826df888e4e69`.

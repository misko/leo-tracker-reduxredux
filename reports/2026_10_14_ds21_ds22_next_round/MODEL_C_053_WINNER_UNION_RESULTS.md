# C053 earlier winner survives, but loses on the same union model

Both original training-selected CH1–8 endpoints were transported to the same 59-satellite union bank and refined with identical 20-second/600-iteration budgets, retaining their own original 25 km search disks. Both returned stationary accepted fits. The earlier endpoint remains near its original solution, but the native likelihood still selects the distant endpoint.

| Endpoint origin | Objective | NLL | Prior penalty | Stationarity | Development error km |
|---|---:|---:|---:|---:|---:|
| Before winner | 24318.889225 | 24031.517341 | 287.371884 | 0.000260657 | 9.597334 |
| After winner, selected | 24198.937767 | 23795.014143 | 403.923624 | 0.000035267 | 253.901882 |

The closer endpoint loses by 119.951458 objective units: its NLL is 236.503198 worse, partly offset by a 116.551740 smaller prior penalty. Thus retaining the earlier basin and candidate satellites is insufficient to repair selection in this pilot. This does not prove that the full candidate bank, global optimization, or all twelve original initializers have been exhaustively tested. It does establish a score preference for the distant accepted endpoint when these two solutions are compared under an identical model.

Qualification preserved native corrections exactly (0 Hz difference), common-satellite predictions within 6.78e-10 Hz, and common visibility exactly. Absolute timing and original search disks were preserved, with no initializer projection. Source-bank scores were never ranked against union-bank scores. Initial endpoints were chosen by their original training objective, not their position error; reference coordinates were joined only after both new fits and selection were sealed.

The experiment completed in 55.042 seconds, with four qualification objective evaluations, four explicit qualification orbit calls, and two optimizer calls. This is an additional endpoint-start pilot, not an equal-budget replay of the original six or twelve starting points. No new result is promoted to the cohort baseline. The repeatedly inspected DS21 development set is not untouched validation.

Code: research commits `7361c98ab` and `5a95bca33`; two component tests and Ruff passed. The tests cover exact native endpoint transport, two bounded calls, rejection retention, no retry, and rejection of incomplete reference evaluation.

Artifacts: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-c-winner-union-053-v1/`. Terminal SHA256 `97c137d9564bfe67b2d8c5725f0fccc234c16889cf0136f98399b131f8123d72`; seal SHA256 `29c837f5d9d55f26bff01bd507e17e5c23f1b2e95fec790f4e2cbf09a6714c93`.

Next diagnostic: decompose the two sealed union endpoints by band, channel, receiver, and satellite/clutter support before proposing a changed score. The poorer selected accuracy is not explained by a failure to retain this earlier solution alone.

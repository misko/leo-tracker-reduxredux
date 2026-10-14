# DS21-025: completed fitted-only initialization

DS21-025 now has a complete six-stage initialization and qualified inputs for the three original final models. This adds a previously unprocessed development recording; initialization alone is not a position-accuracy result. Initialization used neither reference coordinates nor held observations. The full-DS21 target remains below 0.5 km per eligible recording.

The unchanged generic initialization policy uses the original 100-point hierarchy, with 100 / 50 / 25 / 12.5 km spacing, the 250 km regional prior and all-view discovery priority. It does not use the separate 80-center coverage intervention. The recording is `fast-62569efb54f8a8f88d3c08bb350e32e1`, with 2,428 / 1,240 / 1,188 training windows for all / low / high. Counter-defined held blocks remain 2, 3 and 13. The original causal TLE snapshot and all 402 live/archive initialization sources were verified.

| Stage | Completed work | Elapsed seconds |
| --- | --- | ---: |
| Discovery | 870-satellite regional bank; 100 points, 300 fits, 290 stationary | 352.101 |
| Shape | Three starts in each view; all nine stationary | 18.731 |
| Shape bootstrap | Nine completed bootstrap calls | 24.152 |
| Hybrid | Nine stationary fits | 32.297 |
| Cold bootstrap | Nine completed bootstrap calls | 24.568 |
| Six proposals | Eighteen physical seed exports across three views | 25.251 |

The ten nonstationary discovery fits remain recorded and excluded from stationary selection. Each stage completed in its first bounded slice; no failed fit was retried. Training selects the following six proposal centers, in kilometers relative to the configured regional origin:

| Proposal | East | North |
| --- | ---: | ---: |
| cold-0 | -93.750000 | -93.750000 |
| cold-1 | -93.750000 | -81.250000 |
| cold-2 | -75.000000 | -75.000000 |
| shape-low | -81.735780 | -66.291821 |
| shape-high | -79.109528 | -70.517389 |
| shape-all | -94.278272 | -73.178780 |

The final candidate pool contains 36 satellites. The 18 exported physical corrections reproduce their own source functions within 7.275958e-12 Hz maximum error. This transport closure is distinct from approximation loss when representing those functions in another model.

Final-model initialization is also complete under the [existing v2 protocol](THREE_MODEL_EXPANSION_V2_PROTOCOL.md). All 24 required A/B projections use the original strict bounded projection; none needs the exact-source fallback. All 18 C initializations use the original native-observation projection. The six C/all projection RMS values are 231.065, 64.886, 95.286, 163.393, 73.167 and 224.474 Hz in proposal order; these are initialization approximation losses, not final frequency residuals or position-error estimates. Six receiver ambiguity lifts are derived once from all-band training: cold-0 uses RX0/RX1 integers -1/+1 and the other five use -1/+2. Each lift is shared across its three views.

The subsequent [final A/B/C comparison](THREE_MODEL_025_RESULTS.md) completed 54 calls, 52 stationary, and sealed all twelve outcomes before the reference join. No selected row meets 0.5 km. A is a dependent low → locked-high → final-all path. B/C half-band likelihoods inherit shared discovery, proposals and candidate initialization; C also inherits the all-training receiver lifts. They are not independent end-to-end half-band pipelines. The already-qualified metadata compatibility reader handles the original sequential high-stage descriptive override without changing or rerunning numerical fits.

Key immutable SHA-256 bindings:

- Case protocol: `60a8ee712d34391a41acff07798da147cc09df803cac01982fbed383af5df9af`.
- Discovery terminal: `8dd211fb541324dfb02ff36bb21421f10e534ce0138fa2497e207576b4068087`.
- Six-proposal terminal: `f68563ed8b89ebd4a86062ddc88b69a2e08769a65be1d67141b199026bbc73fa`.
- Final-model protocol, 411 sources: `8de2770a01104df3334cb07017a957c84d390debfefc7d2539083af726885668`.
- Final-model initialization: `1dc49725092318e53b583f504fcfbcc78b7cfbdf9f5fb8daf81d830a8765107c`.

No algorithm improvement or accuracy success is inferred from these initialization results. The final report retains the seven training-selected evaluation rows and both nonstationary outcomes separately from this initialization evidence.

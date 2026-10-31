# DS27 discovery inventory versus published ownership

algo03_inventory.run() calls inventory_all_large_tracks.one() before publication_support(). For baseline jobs, one() obtains baseline_pair() replay proposed_associated_ids, including postfit-only IDs; it subtracts that replay mask before creating residual rows, omitting a native source if both current and earlier residual support have fewer than two points. publication_support() subsequently restricts owners to actual published ALGO02 gates and records replay-only IDs as unreported_postfit_ids, but does not rebuild inventory.json. The proposed/postfit-only distinction is explicit in the replay schema; inventory.summary.associated is therefore a replay/proposed count, not the published terminal count. Treating its residual inventory as the residual of published ownership suppresses unpublished support. This audit establishes an accounting/discovery-mask discrepancy, not that any replay-only ID meets acceptance gates or should be associated.

All 15 fast cases retained; 13 available snapshots audited. Final chosen index sealed: True. No fitting, GPS-truth read or inference run.

| Case | Arm | Published ALGO02 | Replay proposed | Replay-only IDs | Still unassociated ALGO04 | Long native sources absent |
|---|---|---:|---:|---:|---:|---:|
| DS27-0001 | — | unavailable | — | — | — | — |
| DS27-0002 | c0 | 3846 | 3910 | 64 | 64 | 1 |
| DS27-0002 | fitted_c | 3846 | 3910 | 64 | 64 | 1 |
| DS27-0004 | c0 | 4033 | 4033 | 0 | 0 | 0 |
| DS27-0004 | fitted_c | 4033 | 4033 | 0 | 0 | 0 |
| DS27-0006 | — | unavailable | — | — | — | — |
| DS27-0008 | c0 | 3146 | 3146 | 0 | 0 | 0 |
| DS27-0008 | fitted_c | 3146 | 3146 | 0 | 0 | 0 |
| DS27-0010 | c0 | 3339 | 3339 | 0 | 0 | 0 |
| DS27-0010 | fitted_c | 3339 | 3339 | 0 | 0 | 0 |
| DS27-0012 | c0 | 2910 | 2910 | 0 | 0 | 0 |
| DS27-0012 | fitted_c | 2910 | 2910 | 0 | 0 | 0 |
| DS27-0014 | c0 | 2980 | 2980 | 0 | 0 | 0 |
| DS27-0014 | fitted_c | 2980 | 2980 | 0 | 0 | 0 |
| DS27-0016 | c0 | 3385 | 3385 | 0 | 0 | 0 |
| DS27-0016 | fitted_c | 3385 | 3385 | 0 | 0 | 0 |
| DS27-0018 | c0 | 2828 | 2828 | 0 | 0 | 0 |
| DS27-0018 | fitted_c | 2828 | 2828 | 0 | 0 | 0 |
| DS27-0020 | c0 | 3294 | 3294 | 0 | 0 | 0 |
| DS27-0020 | fitted_c | 3294 | 3294 | 0 | 0 | 0 |
| DS27-0022 | c0 | 3191 | 3191 | 0 | 0 | 0 |
| DS27-0022 | fitted_c | 3191 | 3191 | 0 | 0 | 0 |
| DS27-0024 | c0 | 4140 | 4140 | 0 | 0 | 0 |
| DS27-0024 | fitted_c | 4140 | 4140 | 0 | 0 | 0 |
| DS27-0026 | c0 | 3042 | 3042 | 0 | 0 | 0 |
| DS27-0026 | fitted_c | 3042 | 3042 | 0 | 0 | 0 |
| DS27-0028 | c0 | 3635 | 3635 | 0 | 0 | 0 |
| DS27-0028 | fitted_c | 3635 | 3635 | 0 | 0 | 0 |

Omitted or suppressed native sources, shown once using fitted-c ownership:

| Case | Native source | Missing IDs | Published residual span (s) | Maximum gap (s) | Existing graph quality | Chosen residual IDs |
|---|---|---:|---:|---:|---|---:|
| DS27-0002 | SCAN-RX2-CH8-T001-RF12690312500.000000 | 64 | 47.840725 | 2.128955 | structure_flagged | 64 |

Precise code path: `tools/algo03_inventory.py:33` builds the inventory before `:44–45` computes/writes publication support; `tools/inventory_all_large_tracks.py:130–140` selects/subtracts replay ownership; `tools/benchmark_graph_covariance.py:68–70` explicitly labels postfit-only and proposed IDs. Both the checkout and runtime script hashes are recorded in the JSON.

Whole-source long-curve thresholds are at least 20 residual native IDs spanning at least 20 seconds; gaps are reported rather than bridged into a claimed continuous emitter. The JSON lists omitted/suppressed sources, exact IDs, chosen residual support and all input/source hashes. No acceptance or emitter-identity claim follows from a long graph curve.

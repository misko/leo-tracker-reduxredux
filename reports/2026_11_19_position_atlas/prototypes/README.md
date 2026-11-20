# Position errors from the early receiver prototypes

The ten original embedded methods reuse their eight frozen DS26 recordings. The paired variants and the tracker-to-12-track integration use the same recordings. Where shown, all four v5 roles use the same recordings and the original tile.

Wrong-tile panels contain 16 queries from eight DS26 captures. Shifted-time experiments use eight captures per offer. The 32 confirmation locations use tracks generated with later orbital elements. The receiver saw causal elements. The source study also reports earlier 48-case catalogue tests and four neighboring tiles. [Location-transfer protocol](../../2026_11_18_location_transfer/protocol.json)

The original regional receiver has a matched roof page and a geographic transfer page. The latter reports both offer conditions for 62 acquisitions. DS26 and DS29 share one roof. StarLoc contributes 11 captures across eight nearby site groups, and Altrincham contributes three windows with zero qualifying tracks. External recordings, simulated locations and missing-region queries have no portable v5 fit. [Blind study protocol](../../2026_11_18_blind_regional_receiver/holdout_private/protocol.json)

The scheduler recall and sampled-IQ pilot check measured acquisition on 108,052 probes and 16 short IQ windows respectively. The pass-event prototype withheld all eight recorded fixes in both arms. The event fixture, stationary relocation check and network validation summary provide aggregate or fixture outcomes with no per-sample coordinates. [Saved embedded results](../../2026_11_19_receiver_duty/embedded/primary-results.zip)

Rebuild the figures from the compact evidence with `.venv/bin/python -m tools.pipeline_eval.qualification.prototype_figures --out /tmp/prototype-figures`.

| Modification | Fitted calibration | Zero calibration |
|---|---|---|
| Streaming Doppler tracker | [Figure](fitted_c/early_stream.png) | [Figure](c0/early_stream.png) |
| Guided pilot search with blind reacquisition | [Figure](fitted_c/early_pilots.png) | [Figure](c0/early_pilots.png) |
| Satellite-family consensus | [Figure](fitted_c/early_consensus.png) | [Figure](c0/early_consensus.png) |
| Packed Doppler orbit table | [Figure](fitted_c/early_compact.png) | [Figure](c0/early_compact.png) |
| Stationary site forecast from prior fixes | [Figure](fitted_c/early_stationary.png) | [Figure](c0/early_stationary.png) |
| 12 tracks chosen by geometry | [Figure](fitted_c/early_coreset.png) | [Figure](c0/early_coreset.png) |
| Doppler changes only | [Figure](fitted_c/early_differences.png) | [Figure](c0/early_differences.png) |
| Marginalized position grid | [Figure](fitted_c/early_grid.png) | [Figure](c0/early_grid.png) |
| Pass-event timing only | [Figure](fitted_c/early_events.png) | [Figure](c0/early_events.png) |
| Tiny coordinate network | [Figure](fitted_c/early_network.png) | [Figure](c0/early_network.png) |
| Compact fit on archived graph | [Figure](fitted_c/early_graph_compact.png) | [Figure](c0/early_graph_compact.png) |
| Compact fit on streamed tracks | [Figure](fitted_c/early_stream_compact.png) | [Figure](c0/early_stream_compact.png) |
| Streaming tracker with 12 geometry-selected tracks | [Figure](fitted_c/early_stream_coreset.png) | [Figure](c0/early_stream_coreset.png) |
| 12 random Doppler tracks | [Figure](fitted_c/early_random_tracks.png) | [Figure](c0/early_random_tracks.png) |
| Refined Doppler-shape grid | [Figure](fitted_c/early_refined_shape.png) | [Figure](c0/early_refined_shape.png) |
| Supplied tile center, zero radio | [Figure](fitted_c/early_prior_center.png) | [Figure](c0/early_prior_center.png) |
| Simulation with supplied satellite IDs | [Figure](fitted_c/early_known_ids.png) | [Figure](c0/early_known_ids.png) |
| Streaming fix after 60 seconds | [Figure](fitted_c/early_stream_60s.png) | [Figure](c0/early_stream_60s.png) |
| Streaming fix after 120 seconds | [Figure](fitted_c/early_stream_120s.png) | [Figure](c0/early_stream_120s.png) |
| Always-blind pilot search replay | [Figure](fitted_c/early_blind_search.png) | [Figure](c0/early_blind_search.png) |
| Unbalanced family fit | [Figure](fitted_c/early_unbalanced.png) | [Figure](c0/early_unbalanced.png) |
| Float64 orbital table | [Figure](fitted_c/early_float64.png) | [Figure](c0/early_float64.png) |
| Forecast from the latest fix | [Figure](fitted_c/early_latest_anchor.png) | [Figure](c0/early_latest_anchor.png) |
| 12 longest Doppler tracks | [Figure](fitted_c/early_longest_tracks.png) | [Figure](c0/early_longest_tracks.png) |
| Full Doppler track budget | [Figure](fitted_c/early_full_tracks.png) | [Figure](c0/early_full_tracks.png) |
| Doppler changes and wrapped means | [Figure](fitted_c/early_wrapped_means.png) | [Figure](c0/early_wrapped_means.png) |
| Marginalized grid at 49 cells | [Figure](fitted_c/early_coarse_49.png) | [Figure](c0/early_coarse_49.png) |
| Coarse Doppler-shape grid | [Figure](fitted_c/early_shape_peak.png) | [Figure](c0/early_shape_peak.png) |
| Held-out region ranking with 12 geometry-selected tracks | [Figure](fitted_c/region_rank_geometry12.png) | [Figure](c0/region_rank_geometry12.png) |
| Shifted-time withholding with 12 geometry-selected tracks | [Figure](fitted_c/region_guard_geometry12.png) | [Figure](c0/region_guard_geometry12.png) |
| Held-out region ranking with all eligible tracks | [Figure](fitted_c/region_rank_full.png) | [Figure](c0/region_rank_full.png) |
| Shifted-time withholding with all eligible tracks | [Figure](fitted_c/region_guard_full.png) | [Figure](c0/region_guard_full.png) |
| Original blind Doppler grid on the roof | [Figure](fitted_c/blind_grid_roof.png) | [Figure](c0/blind_grid_roof.png) |
| Original blind Doppler grid in geographic transfer | [Figure](fitted_c/blind_grid_transfer.png) | [Figure](c0/blind_grid_transfer.png) |

[Fitted calibration PDF](fitted_c/modifications.pdf) · [Fitted calibration samples](fitted_c/modifications.csv)

[Zero calibration PDF](c0/modifications.pdf) · [Zero calibration samples](c0/modifications.csv)

# Remaining43 causal orbit inventory

This prospective metadata audit freezes the remaining DS11 panel as the 87-scan full manifest minus the disjoint original32 and additional12 session sets. It inventories all 43 sessions and compares full catalogues only for scans with an archive request timestamp in `[capture_start - 505s, capture_start)`.

No orbit propagation, radio analysis, fit, or reference position is used. New snapshots require exact archive-byte verification, file completion, and an exact provider/digest `status=published` journal receipt before capture. Exact TLE hashes and parsed SGP4 fields distinguish byte formatting or quantization changes from genuine model-input and epoch changes.

Two selections are reported. `latest_provider_capture_vs_guard` reproduces the existing exporter rule. `three_day_best_capture_vs_latest_provider_guard` uses the original baseline as fallback and the same three-day best-per-NORAD rule as the completed `causal_fresh` experiment. The direct `three_day_best_capture_vs_three_day_best_guard` comparison isolates only the newly available capture-window elements and is the selection suitable for a potential matching follow-up export. The same-guard three-day result is reported separately so historical-source selection cannot be mistaken for a capture-window update.

The journal evidence is a byte copy of `additional_causal_inventory/journal-published.log`. Replay uses the same production release as the DS11 exports and has a 180-second wall cap.

## Result

The frozen request-window census contains full-manifest indices **10, 18, 35, 60, and 75**. Their seven exact archive occurrences all pass the completion proof, with publication margins from 42.196 to 466.891 seconds before capture.

The direct three-day capture-versus-three-day guard comparison isolates **25 genuinely newer-epoch/SGP4 transitions across 22 physical NORADs**: one occurrence at index 10, none at 18, two at 35, none at 60, and 22 at 75. Indices 18 and 60 only repeat an already available payload and are causal no-ops. The guard-side three-day rule also selects NORAD 53480 0.379296 seconds newer than the latest-provider baseline in every scan; this historical difference is deliberately excluded from the 25 capture-window transitions.

Indices 35 and 75 also contain large provider-representation churn at unchanged epochs: each has 8,776 byte-only changes and 1,857 exact SGP4-field changes, of which 1,851 are eccentricity-only. Those are retained in the machine-readable audit but are distinct from the newer-epoch evidence. No propagation or fit was run.

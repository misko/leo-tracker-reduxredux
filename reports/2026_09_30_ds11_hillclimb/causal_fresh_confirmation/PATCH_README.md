# Causal freshness confirmation patches

Five slot-preserving state patches were prepared from the frozen `three_day_best_capture_vs_latest_provider_guard` inventory. The preparation used one sequential worker, one BLAS thread, and a 180-second cap for each patch. It ran no position likelihood or fit.

Indices 10, 18, and 60 are valid empty patches. Index 35 replaces 736 candidate occurrences across 60 tracks. Index 75 replaces 634 candidate occurrences across 59 tracks. The large replacement sets deliberately include all exact byte changes selected by the frozen inventory, including provider representation and same-epoch rounding changes. Index 75's genuinely newer NORAD 53505 contributes 13 of those slots.

For every replacement slot, the generator bound the original and selected two-line element digests, preserved candidate order and physical NORAD identity, and replayed the original candidate states against the exported bank. Maximum position and velocity replay discrepancies are both exactly zero for all five scans, within tolerances of `1e-8 km` and `1e-10 km/s`.

Every selected replacement snapshot is tied to an exact archive occurrence and a matching pre-capture publication proof. The independent pre-fit audit passed all five patches and checked source hashes, NPZ hashes, declared candidate/NORAD lengths, applied NPZ slots, and empty-patch invariants. The patch set is frozen in `patches/patch-manifest.json`; `patch-audit.json` records the independent audit and `patch-preparation-receipt.json` records bounded preparation timing.

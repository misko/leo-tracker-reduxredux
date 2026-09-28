# Inventory adapter readiness correction

The initial opportunity exporter exited successfully but exported zero windows because its input inventory omitted `ready: true`. The partition builder rejected that empty output, exiting 1. No satellite bank or confirmation scoring was run from it.

Preserve `opportunities/`, both initial launch/resource/terminal receipts, and the initial selected inventory. The corrected inventory derives readiness from verified source bindings and is written separately as `selected-inventory-corrected.json`. Re-export to `opportunities-corrected/`; record corrected export/partition invocations separately. The selected four sessions, caches, pose/snapshot authority, model, temporal grouping and scoring rules remain unchanged.

This is a manifest-interface correction before outcomes, not a changed panel or tuned model. Add a regression covering every field required by the actual opportunity exporter.

# Preserved failed metadata-binding attempt

All three bounded extraction attempts failed the frequency-binding assertion before producing sidecars. The implementation incorrectly compared raw receiver CFO with the baseline's canonical RF-normalized, dealiased CFO. No scientific output or input change resulted.

The archived public trajectory implementation exposes the correct `normalized_dealiased_cfo_hz` on each track point. A separately preserved [corrected extraction](../2026_09_29_quality_metadata_corrected/README.md) uses that field and retains both conventions. Original code, manifest and all three failed receipts remain here; they are not overwritten or represented as successful runs.

# Frozen receiver adapter audit

Both final position adapters match the declared intervention. All **96 combinations** of 24 scans, two c arms, and two loadings passed the structural/unit audit in `final_adapter_audit.json`.

- RF-scaled columns contribute `50 Hz × RF/11.5 GHz × temporal basis` on RX1. Additive-Hz columns contribute `50 Hz × temporal basis`. Their existing internal factor of 200 is compensated by the adapter's 0.25 basis multiplier; additive-Hz additionally divides out RF/11.5 GHz.
- Curved and predictive observations use the same corresponding loading. The extra RX2 columns are exactly zero. The original slow receiver columns are unchanged.
- Curved IDs/masks, predictive membership, values, timestamps, RF, aliases, family labels, bounds, noise, powers, causal receipts, and phase/orbit priors are preserved. The physical-factor contracts also agree between c=0 and fitted-c.
- Each adapter clones the scan and deep-copies the seed before expanding its smooth state. The original inputs remain unchanged.

The audit covers construction and physical semantics. Parent-owned paired refits separately enforce every original residual/support gate, phase convergence, bounds, and predictive-only calibration behavior. Seven numerical/unit controls pass. Final adapter sources and both position protocols were left unchanged during this audit; the lean publication inventory records their hashes and preserved source snapshots.

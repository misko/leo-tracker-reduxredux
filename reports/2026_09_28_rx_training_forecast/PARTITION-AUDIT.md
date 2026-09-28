# Independent partition audit

`audit_partitions.py` recomputes separation from the opportunity export and does not trust the partition document's `overlap_validation` field. It checks paired receivers, raw 20 ms time support, every raw projected-candidate source interval, and the legacy frequency-source intervals that previously produced training/held overlap.

The generated `partition-audit.json` records exact input hashes, denominators, overlap counts, and sample-rate coverage. Zero cross-role pairs is required for every overlap check. The legacy comparison separately reports all legacy overlaps and the 1,421 old training/held pairs; the latter must now occur only within a single new role.

Reproduce with:

```bash
python3 reports/2026_09_28_rx_training_forecast/audit_partitions.py \
  --partitions reports/2026_09_28_rx_training_forecast/partitions.json \
  --opportunities reports/2026_09_28_rx_tracking_evidence/opportunities/opportunities.jsonl \
  --frequency reports/2026_09_28_rx_tracking_evidence/held-frequency.json \
  --links reports/2026_09_27_roof_direction_subset/source_links.json \
  --output reports/2026_09_28_rx_training_forecast/partition-audit.json
```

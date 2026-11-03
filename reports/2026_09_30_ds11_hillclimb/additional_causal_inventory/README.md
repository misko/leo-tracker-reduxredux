# Additional12 causal orbit inventory

This is a prospective eligibility inventory for the already exported additional12 DS11 panel. It asks whether any exact physical NORAD in each frozen candidate bank would receive a different element if the catalogue cutoff moved from capture start minus 505 seconds to capture start.

The audit is metadata only. It does not propagate an orbit, run a fit, inspect measurements, or use reference position errors. It binds the assembled additional12 plan, identity sidecar, observations, candidate manifests, and archive bytes. Element identity is the SHA-256 of the exact two TLE lines with canonical newlines. Selection follows the exporter: latest exact source per provider, then newest element epoch per NORAD with collection time and snapshot digest as deterministic ties.

A snapshot whose filename request time lies inside the 505-second interval is not causal evidence by itself. A new source is admitted only when its archive contents reproduce the filename digest, file birth and modification times precede a matching systemd `tle_collection` provider `status=published` receipt, and that receipt precedes recording. The embedded completion proof uses the same `ds11-capture-start-snapshot-completion-proof/v1` schema as `orbit_age_audit`.

The journal evidence was captured read-only with:

```sh
sudo -n journalctl -u leo-tle-collection.service --output=short-unix \
  --since='2026-09-29 10:00:00 UTC' --until='2026-09-30 01:00:00 UTC' --no-pager \
  | rg '"event": "tle_collection"' > journal-published.log
```

Replay requires archive read permission and the repository environment:

```sh
sudo -n env PYTHONPATH=/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/src \
  /opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python \
  reports/2026_09_30_ds11_hillclimb/additional_causal_inventory/inventory.py \
  --journal-log reports/2026_09_30_ds11_hillclimb/additional_causal_inventory/journal-published.log \
  --output reports/2026_09_30_ds11_hillclimb/additional_causal_inventory/inventory.json
```

The command is intentionally exclusive-create so an existing result cannot be silently replaced. The result is useful even when no eligible update exists: that is a negative prospective result for this fixed panel rather than a fit-based selection.

## Result

All 12 scans were bound and replayed. Across 1,124 unique scan-candidate NORAD occurrences, the archive contains **zero** snapshot occurrences whose request-start timestamp is at or after the 505-second cutoff and before capture. Consequently no new snapshot reaches the stricter completion-proof step, and there are zero changed elements, zero newer epochs, and zero changed scans. The already-exported additional12 panel therefore has no capture-start freshness confirmation arm to run.

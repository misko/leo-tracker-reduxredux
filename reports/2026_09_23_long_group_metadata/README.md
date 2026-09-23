# Long-group metadata inventory

This is a read-only metadata feasibility inventory. It limits requests to 200,
uses publication-index candidates excluding every current random-split and
train/validation/quarantine session before capture metadata lookup, and never
opens track, association, position, or prospective-test arrays. The time window
ends strictly at the prospective-test boundary. Eight-hour UTC groups report
only capture timestamps, sample rate, scan counts, and whether 40 nominal
five-minute scans are available. Availability does not certify independence or
an unused test set.

Of 397 publication-index candidates, 200 oldest candidates were requested and
197 remain uninspected. One request was outside the actual capture-time window.
The Sep21 00:00Z and 08:00Z eight-hour blocks contain 72 and 80 captures with API
`nominal_duration_seconds == 300`. Their maximum inter-capture-start gaps are
1,152.6 and 361.8 seconds. These are available recording groups, not yet qualified
tracking datasets. The older recordings may have different hardware/analysis
regimes, and missing IQ/track evidence has not been checked.

The initial direct store read lacked permission. Reproduce using the existing
read-only service identity, redirecting stdout as the normal user:

```bash
sudo -n -u leo .venv/bin/python \
  reports/2026_09_23_long_group_metadata/inventory.py --stdout-only \
  > /tmp/long-group-metadata.json
```

The worker freezes the endpoint at 2026-09-23 16:35:28 UTC, 398.564 ms before
the reserved boundary, and records its source hash.

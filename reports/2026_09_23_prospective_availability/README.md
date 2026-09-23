# Prospective recording availability

This is a metadata-only availability check for recordings captured strictly after
the frozen prospective boundary `2026-09-23T16:35:28.398564+00:00`. It is not a
split, model-selection result, qualification, or position evaluation.

At query time `2026-09-23T22:12:10.187764+00:00`, the read-only publication index
had 34 entries published after the boundary. Public capture metadata placed 33 of
them strictly after the boundary; one was excluded because its capture time was
not after it. All 33 were completed nominal 300-second recordings in the partial
`2026-09-23 16:00Z`--`24:00Z` calendar block. They total 9,900 nominal capture
seconds (2 h 45 min): 10 at 2.5 MS/s, nine at 10 MS/s, and 14 at 15 MS/s.

The block was still in progress at the query time and has only 33 recordings,
below the prior inventory's metadata threshold of 40 completed nominal 300-second
recordings for a complete eight-hour group. Its capture summaries report zero
`capture_qualified` rows, although all 33 report `utc_qualified`. Therefore the
currently observed metadata do **not** establish that a fresh independent
eight-hour validation or test cohort is ready. A future model plan must set any
new split rules before a later inventory; this report makes no selection.

The original 151 TRAIN, 124 validation, and 64 TEST IDs are read only to prove
that their union has no overlap with these fresh capture IDs. The existing TEST
set is not used for tuning or availability selection.

The inventory queried `AdaptiveHopIqStore.publication_index()` in read-only mode
and the public adaptive-session capture-summary API. It did not open recording
bundles or IQ, measurement/GLRT/track outcomes, candidates, position outcomes, or
reference coordinates. The public summary has no capture-bound receiver geometry
or orientation snapshot. Each 33-row count of one current station-authority
interval means only that `captured_at` falls in that authority file's current
validity interval; it does not verify a recording's geometry binding, physical
orientation, or Earth-rotation calculation. `utc_qualified` is capture-time
metadata, not a rotation-validity certificate.

`results.json` records each candidate's public summary, failures, source hashes,
the exact query timestamp, rate counts, and these limits. Its generator hash is
`6d4ff7827c8a231cc8b03045622ee583ee38a1d247d06cbb12e23c4c1e0e599d` and its
saved result hash is
`b025adf4a8bd6ef68e0e1ba960ddf5c95599a05de058426b5eb86a88c03f8f19`.

Reproduce a later metadata snapshot (which can differ as recordings publish):

```bash
sudo -n -u leo .venv/bin/python \
  reports/2026_09_23_prospective_availability/inventory.py \
  --output /tmp/prospective-availability.json
```

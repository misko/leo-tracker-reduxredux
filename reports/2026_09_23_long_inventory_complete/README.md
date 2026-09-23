# Longer-duration validation cohort

The complete metadata inventory identifies five full eight-hour UTC bins with
at least 40 nominal five-minute recordings. This supports a separate randomized
long-duration cohort, rather than treating the previously exposed 113-scan cohort
as independent eight-hour validation.

The exposure-aware seeded assignment is frozen before any new position fits:

| Partition | Eight-hour group starts (UTC) | Scans | Summed nominal capture time |
|---|---|---:|---:|
| Train | Sep 21 00Z, Sep 21 16Z | 151 | 12 h 35 min |
| Validation | Sep 22 08Z, Sep 21 08Z | 124 | 10 h 20 min |
| Test | Sep 22 00Z | 64 | 5 h 20 min |

Seed: **20260923**. All recordings within a group stay together. Each bin spans
eight elapsed hours; summed capture time is smaller and does not imply continuous
IQ. Use nested 1/6/16/all-scan views without counting them as independent groups.

The two September 21 groups sampled for input qualification were ineligible for
test assignment. Test was randomly selected from the other three groups, followed
by a shuffle assigning two training and two validation groups. This is randomized
assignment conditioned on known exposure, not chronological splitting. Test track
evidence remains unopened in this work; historical production analyses exist, so
this is not a claim of zero historical exposure everywhere.

Training metadata is entirely 2.5 MS/s. Validation includes 102 recordings at
2.5 MS/s and 22 at 10 MS/s; test includes 56 at 2.5 MS/s and eight at 10 MS/s.
These acquisition differences must be retained in results and failure accounting,
not silently discarded to improve position accuracy. Metadata eligibility does
not guarantee qualified timing, tracks, candidate caches or successful inference.

Only two validation groups and one test group are available. Adjacent groups may
share receiver conditions and satellite visits; the split alone does not prove
statistical independence. Group uncertainty cannot be estimated precisely from
this small cohort. No new position-accuracy result is claimed here.

The inventory excludes the prior randomized cohort and all original quarantine
and reserve IDs. Capture intervals must fit within the frozen window and their
eight-hour bin. API failures remain explicit in `inventory.json`. Source hashes,
exact IDs and assignments are recorded in `manifest.json`; generation fails on
crossing captures, excluded IDs or duplicate membership.

Reproduce metadata acquisition (read-only service identity) and assignment:

```bash
sudo -n -u leo .venv/bin/python \
  reports/2026_09_23_long_inventory_complete/inventory.py > /tmp/long-inventory.json
.venv/bin/python reports/2026_09_23_long_inventory_complete/split.py \
  --inventory /tmp/long-inventory.json --output /tmp/long-manifest.json
```

The exact saved inventory is authoritative for reproducing the manifest; a later
API inventory can differ when publications or availability change. The scientific
protocol is in `SPLIT_PROTOCOL.md`. Tests cover deterministic whole-group assignment,
test exposure exclusion, capture-boundary rejection and excluded-ID rejection.

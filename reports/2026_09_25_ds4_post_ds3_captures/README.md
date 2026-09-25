# DS4 post-DS3 capture freeze

DS4 is the non-overlapping continuation of DS3. Its lower capture-start bound
is the final admitted DS3 recording at `2026-09-24T22:20:02.797011Z`, excluded.
Its upper bound is the request-time freeze at
`2026-09-25T14:57:19.173054Z`, included. Admission requires qualified UTC
timing, a terminal `completed` receipt, and finalization by that audit cutoff.
This prevents a capture that was still running at the freeze time from entering
the dataset when its manifest appears later. No reference position is stored
or used for admission or grouping.

The freeze admits **91 of 92** capture starts in the interval, from
`2026-09-24T22:30:02.544297Z` through `2026-09-25T14:40:02.098141Z`. All use
`radio_pluto_5d4d`; 36 recordings use 2.5 MS/s and 55 use 10 MS/s. The 14:50
capture is retained in the audit as excluded because it finalized at 15:03,
after the request-time cutoff.

The sealed dataset has three evaluation scopes derived from one chronological
session inventory:

- **Single scans:** one whole-session unit for every admitted recording.
- **Groups of eight:** non-overlapping chronological chunks of exactly eight
  whole sessions. DS4 has 11 such units covering 88 recordings. The final
  three sessions are recorded as a remainder and are not represented as an
  eight-scan result.
- **Full dataset:** one unit containing all 91 admitted sessions.

All receivers, visits, tracklets, and later derived evidence from a recording
must remain with its `session_id`. The grouping contains no fitted values,
satellite identities, reference coordinate, or post-seal result.

The raw tree is read-only and accessible through the `leo` service account.
To reproduce the freeze without modifying it:

```bash
sudo -n -u leo .venv/bin/python \
  reports/2026_09_25_ds4_post_ds3_captures/build_manifest.py \
  --output-dir /tmp/ds4-post-ds3 \
  --manifest-logical-path \
  "$PWD/reports/2026_09_25_ds4_post_ds3_captures/manifest.json"
```

`manifest.json` records every capture in the fixed interval, its admission
decision, raw manifest path and byte digest. `evaluation-units.json` records
the exact single, eight-scan, remainder, and full-dataset memberships.

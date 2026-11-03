# DS18: all sealed adaptive recordings after DS17

Minted **34 whole recordings**, **75,144 retained visits**, and **9,017.28 seconds
(2.5048 hours) of valid IQ per receiver. Both receivers remain together.
Referenced compressed IQ totals **271,807,838,388 bytes (271.81 GB)**.

| Property | Frozen value |
|---|---|
| Capture start, inclusive | 2026-10-08 14:36:56 UTC |
| Capture start cutoff, exclusive | 2026-10-08 23:08:51 UTC |
| Boundary authority | DS17's frozen window endpoint |
| Recording completion | Sealed by the cutoff |
| Recordings | 34: 33 published, one firmware archive |
| Sample rates | 22 at 2.5 MS/s; 12 at 10 MS/s |
| In-window exclusions / unsealed partials found | 0 / 0 |
| Overlap with DS16 or DS17 | None by session or uncompressed IQ digest |
| Admission gates | No analysis-readiness, signal-strength, or localization gate |

The authority is [local/manifest.json](local/manifest.json), protected by
[local/seal.json](local/seal.json). Manifest SHA-256:
`894a6f4b7055e5f6bd602f94ce3acf7f722f204c68c2b521a06dfd6be35a7516`.
Membership is immutable and labeled DS18-001 through DS18-034 by recording
start time. The frozen cutoff is the first inventory timestamp for this request;
later recordings belong to a future successor. Whole-recording start boundaries
do not claim continuous sample-level coverage. DS17's manifest and seal are
copied into the local snapshot. The previously minted datasets are preserved.

The unpublished sealed archive is `scan-fw-4e603fa090384662`. Its inclusion does
not depend on publication or completed analysis. Evaluation must report missing
analysis or unavailable inputs explicitly and retain every assigned member in
coverage accounting rather than selecting only recordings with good results.

## Prior research exposure and evaluation

[verification.json](verification.json) reconciles source snapshot identities,
visit and compressed-byte totals, and disjointness from both preceding datasets.
It also maps prior research labels to DS18 membership: **24 recordings** were
already evaluated as NEW, FRESH, LATER, or RESERVED; **10** have no match in the
reviewed registry. Registry absence is not proof of unseen results. No new
validation split or independence claim is implied by minting a dataset.

The active position-error agent is asked to evaluate DS18 alongside DS16 and
DS17, reporting each dataset separately: membership and completed counts, mean,
median, p95, worst error, convergence/fallbacks, and paired regressions against
the deployed baseline. Matched `c=0` and fitted-`c` arms must retain observations,
candidate sets, other priors and search budgets; frequency-fit effects are
reported separately from position accuracy. Previous research exposure must be
preserved. Any newly randomized validation split must group whole independent
recordings and record its seed before outcome access.

DS16's named membership contains 63 recordings, whereas the familiar numerical
regression used 48. Reports must retain that distinction and account for the
other 15 rather than describe the subset as the complete dataset. DS17 contains
51 recordings.

## Reproduction and verification

The existing DS17 metadata mint now accepts explicit successor identity,
parent, and frozen boundaries. Its default DS17 arguments remain unchanged.
DS18's seal includes the exact mint source and original offline test source
used for inventory. No raw IQ was copied, decompressed or rehashed.

```bash
/home/mouse9911/gits/leo-hard60-default/.venv/bin/pytest -q \
  reports/2026_10_08_ds17_post_ds16/test_mint.py \
  reports/2026_10_08_ds18_post_ds17/test_successor_mint.py

/home/mouse9911/gits/leo-hard60-default/.venv/bin/python \
  reports/2026_10_08_ds17_post_ds16/mint.py verify \
  --dataset-id DS18 --parent-dataset DS17 \
  --parent reports/2026_10_08_ds17_post_ds16/local \
  --start 2026-10-08T14:36:56+00:00 --end 2026-10-08T23:08:51+00:00 \
  --output reports/2026_10_08_ds18_post_ds17/local
```

All **18 offline tests**, Ruff, snapshot seal verification and an independent
metadata reconciliation pass. The mint read published recordings through the
read-only `AdaptiveHopIqStore` port and inventoried firmware interchange
manifests in the configured spool under the production service account.
The live inventory is not atomic; storage availability can change. IQ remains
referenced in its existing locations, with no retention hold. No new RF capture,
analysis job, publication, service change, or remote push was initiated by minting.
The full source snapshots are local and Git-ignored.

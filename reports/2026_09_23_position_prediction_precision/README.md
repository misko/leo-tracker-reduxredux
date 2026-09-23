# Quarter-second prediction precision audit

Cached quarter-second orbital states were compared with fresh SGP4 propagation at
the exact observation-plus-tau epochs. The deterministic sample uses three scans from
the frozen random-group training partition, four tracks and three cached candidates
per scan, tau values -5/0/+5 seconds, and three truth-free coordinates: the prior
training solution plus the Sacramento and Reno prior centres.

| Doppler difference | Result |
|---|---:|
| Raw RMS | 0.00466 Hz |
| Raw maximum absolute | 0.01214 Hz |
| RMS after per-track/candidate/tau mean removal | 0.00209 Hz |
| Maximum absolute after mean removal | 0.00896 Hz |
| Training winner changes within sampled support | 0 / 36 |

Every queried epoch was checked against the saved cache range before indexing. None
required extrapolation or negative indexing. The exact replay used catalogue bytes
whose SHA-256 equals each cache's recorded causal snapshot digest, and used the cache's
saved first-sample UTC nanoseconds.

The interpolation discrepancy is three orders of magnitude below the typical
training residual and about three orders below the reported few-hertz response to a
300 m displacement. It did not change any sampled training candidate/tau winner.
Quarter-second interpolation, epoch conversion, and cached frame transformation are
therefore not a plausible present bottleneck for sub-300 m inference.

This is a bounded numerical audit rather than an exhaustive proof: it covers 36
track-coordinate cases and three tau nodes. `precision_audit.json` contains every row
and binds the split manifest, cache manifests, catalogue digests, joint scorer, and
audit source.

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python tools/research/audit_position_prediction_precision.py \
  --manifest reports/2026_09_23_position_random_group_split/manifest.json \
  --replication-root reports/2026_09_23_day_position_validation/replication \
  --joint-tool tools/research/sixteen_joint_compare.py \
  --output <fresh-output-directory>
```

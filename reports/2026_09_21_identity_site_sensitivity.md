# Observer-site sensitivity of frozen track classifications

## Question and protocol

The persisted scanner reviews use 37.858988° N, 122.478103° W, altitude -29 m. The
positioning/beam study uses 37.84903264307456° N, 122.4856541910174° W, altitude 0 m, about
1.29 km away. This bounded diagnostic asks whether changing only that known observer coordinate
changes retrospective TLE candidate ranks.

The sample was fixed before scoring: the first 20 tracks ordered by `(session_id, tracklet_id)`
from the frozen 988-track position corpus. All 20 happen to come from
`scan-hop-01b11a5d776e7369`, so this is a deterministic sensitivity probe, not a representative
corpus estimate. It includes both receivers and 854 observations (505 training, 349 randomized
evaluation).

The scorer reconstructed the exact published track points and verified their CFO values and
support-center times against `/tmp/dual-full-export.npz`. Both site arms use the same observed
data and the exact persisted deterministic randomized split. At each site, the standard
retrospective review protocol independently refits the training-only offset and integer tau on
the -5 through +5 second grid. Candidate screening and Doppler prediction use the same strictly
causal catalogue snapshot,
`sha256:699a1342b42e7014ab0ee1ac11f72bd534cae477bf824ca7aeeb11973ac8c7c7`.
The persisted-site arm reproduces all stored top-two IDs, tau values, offsets, and training and
evaluation RMS values numerically.

## Result

No leading catalogue number changed in the 20-track prefix. One track changed its second-place
candidate: track `sha256:128f9fd8676bbdbc01b10eb5b1bae5052cf66198a5f15b59e59a9982c9cf04dd`
kept leader 67852, while runner 64071 was replaced by 63148. Two tracks changed candidate-bank
size by one object because the site-dependent horizon screen changed; neither change affected
their leading candidates. Seventeen tracks retained the complete top-five ordering.

The coordinate difference was nevertheless material to the study's confidence classification.
All 20 tracks pass the persisted-site research rule of leader evaluation RMS at most 150 Hz and
runner RMS at least three times the leader RMS. Only 17 pass at the user site:

| Track suffix | Leader | Persisted RMS / ratio | User-site RMS / ratio | Cause |
|---|---:|---:|---:|---|
| `8ee8073c` | 65343 | 106.13 Hz / 7.74 | 154.51 Hz / 5.59 | RMS exceeds 150 Hz |
| `403dcf54` | 65348 | 69.40 Hz / 4.25 | 106.70 Hz / 2.99 | ratio falls below 3 |
| `e7eaaae3` | 67079 | 127.36 Hz / 3.64 | 170.95 Hz / 3.13 | RMS exceeds 150 Hz |

Across the sample, median leader evaluation RMS changes from 91.98 Hz to 82.63 Hz. Per-track
changes span -72.95 to +48.38 Hz, with a median of -1.68 Hz. Three leaders select a different
tau. The absolute fitted-offset change has median 681.7 Hz and maximum 3,134.3 Hz. These
nuisance changes absorb part of the coordinate perturbation, but not enough to preserve all
threshold decisions.

The bounded evidence therefore does not show a leader-identity change in this prefix. It does
show that the 1.29 km site inconsistency can change runner ordering and clear/ambiguous status.
Any full-corpus count based on the 150 Hz/three-times gate should be recomputed at the coordinate
used by the downstream positioning study. This remains a known-site sensitivity diagnostic;
neither arm supplies blind satellite identity truth.

## Reproduction

The complete per-track result is
[`results.json.gz`](2026_09_21_identity_site_sensitivity/results.json.gz), SHA-256
`254517d9f8814f54e07a269b9fcb451dbb87044093c3bcd30650495bf11c167f`.

```bash
sudo -n -u leo env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv/bin/python tools/research_identity_site_sensitivity.py \
  --selection /tmp/dual-full-export.json \
  --prepared /tmp/dual-full-export.npz \
  --cache /tmp/lt3d-research-20260921 \
  --output /tmp/identity-site-sensitivity-20.json \
  --maximum-tracks 20
```

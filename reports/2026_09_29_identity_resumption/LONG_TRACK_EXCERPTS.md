# Early-header signs over seconds along existing trajectories

The resumed within-visit tests previously covered 120 milliseconds. This new
experiment samples three points across each of two approximately 28-second
DS10 trajectories. It uses existing stored IQ only; it is not new RF collection.

## Selection and exact binding

Choose DS10-F010-T0031 and T0040: same session, receiver 0, channel 2, lower
edge, 10 MS/s. The former is the previously studied conditional candidate 63400;
the latter is a same-instrument comparison with conditional candidate 58453.
These associations are not decoded identities. Reconstruct both trajectories
through the existing public analysis/storage APIs and require every visit and
nanosecond support-center time to match the archived capture manifest.

Divide each trajectory into three equal elapsed-time intervals and select the
highest acquisition-margin observation in each interval, without consulting
header signs. Recover at most 15 frames from a 20-ms stored excerpt at each
selected point. This is six excerpts total, with a 180-second process limit.
The completed recovery process exited successfully within that bound.

| Track | Visits | Selected time offsets, seconds | Qualified frames per excerpt |
|---|---|---|---|
| T0031 | 1085, 1132, 1181 | 0, 6.498, 13.172 | 7, 7, 2 |
| T0040 | 1421, 1482, 1517 | 0, 8.260, 13.012 | 2, 7, 7 |

Qualification requires held-out pilot coherence greater than 0.5. Sampling
thirds does not imply that selected observations span the entire trajectory;
their actual coverage is about 13 seconds. The six excerpts contain 32 qualified
frames. No low-quality frames were promoted to increase coverage.

## Comparison and controls

For every excerpt, use its first qualified frame to fit label-blind population
centering; evaluate on the remaining qualified frames. Compare real signs at
symbols 2–7 for both the original four carriers (24 signs/frame) and a fixed
26-carrier support (156 signs/frame). Normalize centered vectors and compute
symmetric discovery-to-evaluation cosine similarities between excerpts.

The statistic is mean within-trajectory similarity minus mean between-trajectory
similarity, excluding self-pairs. Evaluate all 20 balanced assignments of three
excerpts to each group; take the maximum statistic across the two feature sets
for each assignment. These are descriptive control ranks, not calibrated
satellite-identity p-values: trajectory labels are strongly confounded with time.
All underlying recordings have also been inspected before.

| Features | Within-minus-between cosine similarity | Maximum-feature partition rank |
|---|---:|---:|
| Four carriers | +0.0491 | 0.20 |
| 26 carriers | +0.0411 | 0.30 |

Nearest observation time alone assigns the correct trajectory for all six
excerpts. Therefore, a small positive within-track contrast cannot distinguish
identity from temporal continuity. With only two tracks, the available partitions
also have very limited inferential resolution. Receiver consensus was not tested
in these new single-receiver excerpts. Physical trajectory continuity does not
guarantee an unchanged satellite, beam, or message stream.

## What this changes

We can recover early-header observations separated by seconds along the same
stored trajectory, closing an actual coverage gap. The first bounded comparison
shows no compelling stable identity fingerprint. This establishes usable input
for longer-timescale structural tests without claiming a decoded field or
mistaking short 120-ms excerpts for a full long encounter.

`long_track_excerpts.py` writes source manifests, candidate bindings, raw-excerpt
hashes, recovered NPZ hashes, quality gates and method hash to ignored
`local/long-track/recovery.json`. It refuses to overwrite an existing receipt.
`long_track_compare.py` verifies those NPZ hashes and writes the complete matrices,
partition controls and method hash to `local/long-track/comparison.json`.

Run recovery using the pinned installed runtime with read access to the existing
store. The output-exists guard deliberately prevents accidental repeat work:

```sh
sudo -n -g leo env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 timeout 180 /opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python -I /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_29_identity_resumption/long_track_excerpts.py
```

Run comparison with:

```sh
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy python reports/2026_09_29_identity_resumption/long_track_compare.py
```

Component tests verify time-based selection, acquisition-margin selection and
exclusion of self-pairs from the contrast. Both passed, as did Ruff. No golden
fixtures, production code or persisted public contracts were modified; numerical
data remain ignored and uncommitted.

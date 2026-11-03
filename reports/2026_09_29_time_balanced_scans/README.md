# Time-balanced eight-scan selection

Tests observation selection rather than additional model flexibility. For each
dataset, regroup the existing 24 scans from its early/middle/late panels into
three eight-scan sets, each spanning all three windows. Compare against refits
of the original three eight-scan panels using exactly the same model and starts.

**Decision: temporal spreading helps DS7 and DS8 medians, but does not deliver
reliable sub-km accuracy and substantially increases elapsed time.** A matched
timing-start audit also exposed local optimizer modes; future comparisons should
include training-only timing-grid initialization rather than rely on zero-time
starts alone. Do not select solver endpoints using known geographic error.

## Results with the supplementary six-start procedure

All eighteen selected solutions qualify. The same three cold starts plus three
training-only timing-grid starts are available to every contiguous and balanced
set. The table is supplementary to the preserved frozen primary experiment.

| Dataset | Contiguous median m | Balanced median m | Sub-km sets, contiguous → balanced | Median span h, contiguous → balanced | Held total change |
|---|---:|---:|---:|---:|---:|
| DS7 | 2,023.56 | 1,416.56 | 0/3 → 1/3 | 0.825 → 10.014 | -79.148 |
| DS8 | 1,721.06 | 1,422.84 | 0/3 → 1/3 | 0.943 → 7.779 | +33.753 |
| DS9 | 841.75 | 1,042.82 | 2/3 → 1/3 | 0.824 → 12.372 | +56.334 |

The three balanced sub-km results are DS7 balanced1 at837.68m, DS8 balanced0
at722.12m, and DS9 balanced2 at559.21m. These are reported outcomes of frozen
timestamp selection, not a prescription to choose those sets by their error.
All three balanced medians remain above1km. The aggregate held-score change is
+10.939, but DS7 worsens and the comparisons share the same corpus; they are
not independent significance trials. No causal claim that geometry alone explains the changes
is established: temporal spreading can also average changing systematic errors.

![Supplementary matched six-start results](grid_comparison.png)

[Supplementary full table](grid_TABLE.md) and `grid_summary.json` include all
sets. Original results remain in [primary table](TABLE.md), `summary.json`, and
`comparison.png`. In that frozen three-start primary experiment, contiguous
medians were2,023.56/1,721.06/876.13m and balanced medians were
1,688.30/1,422.84/1,042.82m for DS7/8/9; sub-km totals were3/9 in both arms.
Do not mix primary controls with supplementary balanced results.

## Why the timing-start audit was necessary

The primary DS8 early and middle controls converged to training scores116.430
and357.892 below previously known solutions, despite passing local gradient
checks. The [documented supplementary audit](TIMING-START-AUDIT.md) initialized
each recording's timing from its training-only41-node score curve, for the same
three fixed E/N starts. The final choice uses the largest qualified TRAINING
score among all six starts. It never uses reference or held score for selection.

This found materially higher training scores in9/18 sets, including both affected
DS8 controls. Better training score need not mean smaller geographic error:
the primary DS8 early control's804.17m error becomes1,435.66m at the better
training optimum. Its apparently favorable sub-km endpoint is not retained
merely because it lies closer to the known reference. Local stationarity alone
is insufficient evidence of global optimization.

All54 primary starts and53/54 additional starts qualify; all18 supplementary
selected endpoints qualify. Batched timing scores replay the scalar model within
3.64e-12 and selected endpoint derivative audits within5.10e-6. Every process
returns zero inside90seconds. Primary jobs total376.93 process-wall seconds and
additional jobs361.44seconds, with three workers. All input/source hashes verify;
the manifest test and Ruff checks pass. Both arms contain exactly4,328 tracks
and198,806 observations over the same72 scans across DS7–DS9.

The next useful data-budget comparison is to pool more of these existing scans
over the same long span, reporting accuracy versus scan count and elapsed time.
The current evidence does not justify replacing the roughly one-hour operating
window with a ten-hour window for only three sub-km outcomes out of nine.

## Frozen selection and fair comparison

Sort the 24 distinct scans in each dataset by recorded start UTC, then assign
chronological rank modulo3. The resulting three sets are disjoint and each has
two or three scans from every original window. The frozen manifest contains
every session ID, original input binding, window label, timestamp, and span.
No measurement value, candidate assignment, geographic error, or held score
selects membership. The partition test verifies exact coverage and checks
measurement-value independence and duplicate rejection.

Both arms use all 24 scans exactly once per dataset: identical observations,
training/held masks, candidate banks and model constants overall. Each set
uses the q020 candidate/unassociated-trend mixture, a shared E/N position and
one timing offset per recording. Three identical fixed starts are used in
every fit, selected solely by training score among numerically qualified fits.
Existing combined-panel optima do not initialize these runs. The summary
checks exact session coverage and equal total tracks/observations across arms.

The original sets span roughly0.82–1.06hours between their first/last scan starts.
The time-balanced sets span7.78–12.37hours. These are elapsed start-to-start
spans, not total receiver dwell or IQ recording time. This is explicitly a
different-latency comparison; it does not promise better accuracy in the
original roughly one-hour window. It also does not establish an optimal
geometric design—only a deterministic temporal stratification.

## Evidence and limits

[Protocol](PROTOCOL.md) was frozen before geographic outcomes. `manifest.json`
binds its generator and original observations. [Full table](TABLE.md) and
`summary.json` retain every set and any missing/unqualified output. Result files
preserve all three starts, optimizer messages, gradients and derivative audits,
selected coordinates, held scores, session coverage and source/input hashes.
Process receipts retain exits. The dataset-wide held totals compare the same
underlying observation corpus across arms, without implying that individual
sets are paired or independent trials.

The reference is the inherited exposed, unsurveyed site. Measurements and
candidate exports have already been explored; this is not a new-site or
untouched-data validation. Interleaved held samples can share systematic errors
with training samples. No RF collection, production edits, golden fixture
changes, or remote publication occurred.

```bash
python3 -m unittest discover -s reports/2026_09_29_time_balanced_scans -p 'test_*.py'
python3 reports/2026_09_29_time_balanced_scans/manifest.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_29_time_balanced_scans/batch.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy python reports/2026_09_29_time_balanced_scans/summarize.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with matplotlib python reports/2026_09_29_time_balanced_scans/plot.py
OPENBLAS_NUM_THREADS=1 timeout 90s uv run --no-project --with numpy --with scipy python reports/2026_09_29_time_balanced_scans/grid_run.py DS8_contiguous_early
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_29_time_balanced_scans/grid_batch.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy python reports/2026_09_29_time_balanced_scans/summarize.py grid
OPENBLAS_NUM_THREADS=1 uv run --no-project --with matplotlib python reports/2026_09_29_time_balanced_scans/plot.py grid
```

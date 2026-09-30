# Four narrower-band matched-time opportunities

All four remaining same-receiver, same-channel, same-edge, different-conditional-ID
opportunities were tested at 5 MS/s. This extends the fixed simultaneous-track
protocol; it does not repeat failed visits or select replacements after seeing
their header signs. No new RF was collected.

## Fixed selection and recovery

For each pair, divide its shared observation times into three elapsed-time
intervals and select the maximum weaker-candidate acquisition margin in each.
Recover both candidates from the identical stored 20-ms excerpt at each selected
visit, using at most 15 frames and the unchanged held-pilot threshold >0.5.
Exact trajectory visit/time binding and identical per-visit raw-excerpt SHA256
are required. Four bounded offline processes completed successfully, each with
a 180-second limit. Earlier 10-MS/s outputs were preserved.

| DS7 pair | Selected visits | Qualified frames, candidate A/B |
|---|---|---|
| F020 T0028/T0034 | 1094, 1124, 1141 | 0/0, 0/0, 0/0 |
| F035 T0033/T0039 | 1512, 1545, 1552 | 0/0, 0/6, 0/6 |
| F042 T0022/T0027 | 893, 910, 996 | 2/2, 1/0, 0/2 |
| F042 T0046/T0051 | 1817, 1838, 1855 | 1/0, 0/0, 0/0 |

Only visit 893 supplies at least two qualified frames for both candidates.
The remaining visits do not support a discovery/evaluation header comparison.
This is coverage failure, not proof of different or absent identity fields.

## The one usable matched visit

The candidate associations for F042 T0022/T0027 are legacy conditional NORAD
57460/67203; these are not decoded RF identities. Use symbols 2–7 at the 11
common nonpilot carriers: 66 real signs per frame. The first qualified frame
is the donor and the remaining frame evaluates. Qualified frame indices are
3/13 for candidate A and 2/13 for candidate B; no alignment search is performed.
This compares coordinate patterns, not proven simultaneous transmitted messages.

| Donor → evaluation | Candidate A | Candidate B |
|---|---:|---:|
| Candidate A | 40/66 (60.6%) | 43/66 (65.2%) |
| Candidate B | 37/66 (56.1%) | 42/66 (63.6%) |

Within-candidate agreement is 82/132 (62.1%), versus 80/132 (60.6%) across
candidates: only two additional agreements. Coordinates include common constants
and correlated signs, so these counts must not be treated as independent
Bernoulli trials. No significance or identity claim follows. A single usable
visit also cannot test persistence across repeated observations. No independent
receiver-consensus test is available in this single-receiver comparison.

Across both bandwidths, the five inventoried same-receiver opportunities have
now received their fixed bounded prototypes. That does not exhaust every stored
visit or every possible trajectory; it completes this selection-defined test.
The main result is sparse matched-time recovery coverage, with one weak and
uninformative header comparison.

## Scripts, provenance and tests

`simultaneous_tracks.py --pair 0` through `--pair 3` select only these four
predefined opportunities, each in its own ignored output directory. The original
no-argument 10-MS/s target and overwrite guard remain intact. Recovery was run:

```sh
for pair in 0 1 2 3; do
  sudo -n -g leo env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 timeout 180 /opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python -I /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_29_identity_resumption/simultaneous_tracks.py --pair "$pair" || break
done
```

The exact executed source is archived in ignored
`local/simultaneous5/executed-recovery.py`; its hash matches all four receipts.
The working script subsequently received only a line-wrap fix.
`simultaneous5_audit.py` validates those receipts and NPZ hashes, independently
recomputes quality gates from metadata, and records per-excerpt pilot maxima
and medians. `simultaneous_signs.py` produces the matrix above from only eligible
visits, excluding donor frames from evaluation. Reproduce their outputs with:

```sh
uv run --no-project --with numpy python reports/2026_09_29_identity_resumption/simultaneous5_audit.py
uv run --no-project --with numpy python reports/2026_09_29_identity_resumption/simultaneous_signs.py
```

Six focused selection, counter, invariance and coverage tests passed, plus the
new directional donor/evaluation test. Ruff passes for the changed scripts.
Numerical outputs remain ignored; golden fixtures and production code were not
changed. The overall investigation remains incomplete: no semantic satellite
identifier or independently validated persistent identity signature is recovered.

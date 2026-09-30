# Matched-time, same-receiver candidate comparison

The preceding two-track comparison was confounded with time. We therefore
searched the complete 1,393-entry qualified DS7/DS8/DS9/DS10 inventory for tracks
sharing recorded visits on the same receiver, edge and channel, with different
conditional satellite labels. Five pairs satisfy this coverage criterion:
four at 5 MS/s, one at 10 MS/s. Three additional pairs use different receivers.
All eight different-label pairs have legacy conditional labels, not verified
satellite identities. Common visits alone do not prove two distinct satellites.

## Bounded prototype

Use the only same-receiver 10-MS/s opportunity: DS7-F069-T0007 and T0017,
conditionally associated with 55774 and 59040. The trajectories share 13 visits.
Reconstruct them using the public analysis/storage APIs and verify their complete
visit sequences and support-center times against the archived census.

Split the shared support into three equal elapsed-time intervals. In each,
select the visit maximizing the weaker acquisition margin of the two candidates.
No recovered header signs enter selection. For each candidate recover at most
15 frames from the same stored 20-ms IQ excerpt. Raw-excerpt SHA256 equality
confirms identical input samples for the two candidates at each selected visit.
Timing/CFO candidate parameters differ; this does not itself prove two emitters.

The offline process completed successfully within its 180-second bound:

| Stored visit | T0007 qualified frames | T0017 qualified frames |
|---|---:|---:|
| 853 | 0 | 0 |
| 872 | 1 | 0 |
| 876 | 0 | 0 |

Qualification retains the existing held-pilot-coherence threshold greater than
0.5. None supplies the minimum two qualified frames per candidate required
for a discovery/evaluation comparison. **Abstain from header correlation.**
This is a recovery-coverage failure, not a negative identity result. Acquisition
margin and quality at each track's previously selected strongest excerpt do not
guarantee usable recovery at the newly selected shared visits.

## Interpretation and remaining scope

This experiment removes the large time gap between candidates at input selection,
but the recovered data do not support the intended controlled comparison. The
threshold was not relaxed and visits were not repeatedly substituted after
observing failure. Four narrower-band same-receiver opportunities remain in the
inventory; they have fewer observable carriers and the same conditional-label
limitation. The result does not establish that every possible shared visit is
unusable, nor that the remaining corpus has been exhausted.

## Reproducibility

`simultaneous_tracks.py` performs bounded read-only recovery and refuses to
overwrite its existing receipt. It was run with:

```sh
sudo -n -g leo env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 timeout 180 /opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python -I /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_29_identity_resumption/simultaneous_tracks.py
```

The exact executed source was saved as ignored `local/simultaneous/executed-recovery.py`
before two line-wrap-only lint fixes. Its hash matches the recovery receipt.
`simultaneous_coverage.py` reproduces the complete opportunity inventory, verifies
the archived method and NPZ hashes, checks identical raw input hashes, and writes
`local/simultaneous/coverage.json`. Run this pure-Python audit with:

```sh
python3 reports/2026_09_29_identity_resumption/simultaneous_coverage.py
uv run --no-project --with pytest pytest -q reports/2026_09_29_identity_resumption/test_simultaneous_coverage.py
```

The focused test checks the per-candidate minimum and rejects mismatched raw
excerpts. It and Ruff pass. Numerical artifacts remain ignored. No new RF,
production changes, fixture updates, or data commits were made.

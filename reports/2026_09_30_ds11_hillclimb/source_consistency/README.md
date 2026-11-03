# Raw-source conflicts are real; hard source-consistent deletion does not improve DS11

**Interpretation superseded by the later [probe semantics audit](../probe_overlap_semantics/README.md):**
shared raw-probe groups do not establish duplicate or mutually exclusive
detections.2215 of2221 shared groups contain distinct candidate IDs; only six
reuse an exact candidate. The [waveform coexistence test](../probe_coexistence/README.md)
supports additive pilot contributions in four of six tested shared probes.
The historical counts and failed deletion experiment below remain valid, but
their references to "conflicts" do not establish physical incompatibility.

The corrected pinned provenance adapter finds extensive reuse of raw probe
source groups across exported DS11 tracks. On the eight fixed screen scans,
2,221 training source groups conflict across tracks and involve 4,487 of 16,016
training observations (**28.02%**). This is an observation about the exported
data's dependence structure and remains true regardless of the model result.

A deterministic training-only remedy does not improve localization. The
maximum-coverage source-disjoint subset retains 356 of 489 tracks and 75.25% of
training observations. All eight fits qualify, but median error worsens from
3108.162 m to 3514.231 m, mean worsens from 3481.538 m to 3605.878 m, and only
four scans improve. P90 changes from 6046.037 m to 5962.703 m. The predeclared
gate required at least five wins, at least 10% median reduction, and nonworse
P90, so the arm stops without replication.

The model selects tracks using only training source-group IDs and training
counts. It preserves every retained track's observations, mask, full candidate
mixture, and independently profiled CFO. Held frequencies, held group
membership, candidate identity, reference position, and fit outcomes cannot
change membership. Native likelihoods are not compared across the subset and
all-track models because their dimensions differ. The common all-track IID held
diagnostic at the subset endpoints totals +3.940 nats and has mixed scan signs;
it does not reverse the geographic failure.

This result rejects greedy hard deletion as a DS11 position improvement. It
does not validate treating tracks that share a raw source as independent. A
future alternative would need a dimension-matched likelihood over competing
interpretations of the same observations; simply deleting 19--30% of each
scan's training support removes useful constraints as well as conflicts.

The initial all-32 provenance attempt was interrupted after its runtime was
judged too costly for the iteration. It wrote no result artifact. The exact
captured progress and interruption are retained in `interrupted.receipt.json`.
The subsequent frozen screen-8 audit completed and produced `diagnostic.json`
and the digest-bound `source_groups.json` sidecar. No failed attempt was
relabelled as a completed audit.

Five component tests pass: exact IID parity with no conflicts, deterministic
maximum-coverage disjoint selection, held/reference independence, resource and
partition binding, and finite-difference gradient agreement. Full numerical
results and gate arithmetic are in `summary.json`; the frozen rules and launch
chronology are in `PROTOCOL.md`.

```bash
sudo -n env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  /opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python \
  -m pytest -q reports/2026_09_30_ds11_hillclimb/source_consistency/test_model.py
python3 reports/2026_09_30_ds11_hillclimb/harness.py summarize source_consistency wave1
```

No RF collection, archive mutation, production change, golden-fixture change,
or remote publication occurred.

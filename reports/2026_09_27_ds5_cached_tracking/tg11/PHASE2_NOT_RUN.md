# TG11 phase-two stop receipt

Phase two was prepared but neither frozen nor executed. The frozen phase-one
receipt completed all four planned development visits and passed both cost
gates, but failed the preregistered scientific gate. Consequently
`phase2_authorized` is false, and `run_phase2_replay.py` rejects the receipt
before creating a phase-two source lock or loading any phase-two IQ.

The measured phase-one median process-CPU results were:

| Rate | Application | TG11 | Speedup | Absolute TG11 budget | Cost gate |
|---:|---:|---:|---:|---:|:---:|
| 2.5 Msps | 1515.495 ms | 16.032 ms | 94.528x | 143.427 ms | pass |
| 5 Msps | 4071.329 ms | 33.150 ms | 122.815x | 389.020 ms | pass |

The scientific failure occurred on
`newdev-r2500000-scan-fw-40ebc07665464c7d-v001078`. The unchanged application
comparator had no positive pair on either receiver. TG11 emitted an active RX0
pair, which could not associate to any pair in the comparator's full response.
This is an extra positive under the frozen gate, so it cannot be reclassified
as retention and the larger replay cannot proceed.

The separate screen-coordinate audit also found that the rank screen's
projected epoch is not calibrated to the acquisition epoch closely enough for
the frozen 4 microsecond routing gate. This is consistent with phase one's
blind routes and prevents interpreting the cost result as a cache-guided
speedup. It does not alter the phase-one stop decision.

Frozen evidence:

- `phase1_cost_results.json` SHA-256:
  `7877fdd40972a9bc70c705b434bbc33207f735bd3d8a78f93767ea1cd5b1f38f`
- `source_lock_phase1.json` SHA-256:
  `bfc021b8d16f2c6f6b004e18a3656e47d31a4d7cd400af56aab038c57c1cc70e`
- Holdout IQ and outcomes were not opened.

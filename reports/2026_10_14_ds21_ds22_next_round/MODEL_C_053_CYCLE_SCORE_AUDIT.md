# C053 negative cycle: exact likelihood and prior accounting

The move from the fixed high-band position to the selected full-band position
trades improved lower-band likelihood against worse upper-band likelihood.
Most satellite/clutter assignments remain stable: mean posterior overlap is
0.99468 low and0.99690 high. This final displacement is not a wholesale
association collapse like the earlier distant-basin failures.

| Selected release minus high-position profile | Objective contribution |
|---|---:|
| Low-band NLL | −2.846675 |
| High-band NLL | +2.371777 |
| Common timing prior | −0.001881 |
| Relative satellite timing prior | +0.745925 |
| Receiver clock prior | −1.292026 |
| Group calibration prior | +0.000044 |
| Total | −1.022837 |

The largest opposing channel contributions are CH1 NLL−3.941830 and
CH8 NLL+2.954894. Relative satellite timing regularization resists the move;
receiver-clock regularization favors it. Therefore attributing this specific
displacement solely to the satellite timing prior would be incorrect. The
likelihood also favors it slightly overall, so removing clock regularization
alone is not proven to solve the localization error.

Compared with the previous1.027646 km full incumbent, the new1.419297 km
selected state improves both low and high NLL (−12.077278 and−6.908817).
Its relative timing prior falls7.989761 while clock prior rises0.667643.
Different transitions have different mechanisms; these should not be pooled.

This read-only audit made6 objective evaluations and3 explicit orbit calls,
zero fits and zero reference reads in11.681 seconds. It exactly replays saved
scores, reconstructs native posteriors, partitions channel likelihood, and
closes all four physical prior terms. The actual-model component test and
Ruff pass. No model or prior is promoted on this evidence.

Source `e5f6cc514`; namespace
`/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-c-cycle-score-audit-053-v1`.
Result SHA256 `9b1f18a20b96f3f0e85d1c10a3a1f90ae676c470737683fcec6cb0fcfbd6c9a6`.
Seal SHA256 `6aed0bd6cfca84ff1b3e81ad689479cf5cbf58587f596c59abe1b29df7193571`.

# Repeated regional checks on three saved offers

One northern near-boundary solve asked three times whether the same regional evidence required withholding. Keeping the first certified answer saved 50 probe evaluations and 0.45 s through publication. On the physical DS30-0016 recording and the northern far omission, the solver asked once. Those cases provide no repeat work to remove. [Frozen protocol](terminal-proof-reuse-protocol.md) · [All six receipts](measurements/terminal-proof-reuse.json.gz)

| Saved detector packet and offered region | Scored points, original → reuse | Cache hits | Regional scorer CPU s | Saved input through exit, elapsed s | Decision in both builds |
|---|---:|---:|---:|---:|---|
| Simulated north, truth outside by 100 m | 75 → 25 | 2 | 0.668 → 0.214 | 6.924 → 6.474 | Published a false fix |
| Physical DS30-0016, containing | 24 → 24 | 0 | 0.103 → 0.102 | 5.569 → 5.587 | Published |
| Simulated north, truth outside by 52.5 km | 96 → 96 | 0 | 0.335 → 0.346 | 3.459 → 3.638 | Withheld |

Each case had one pair on one low-priority Gauss core. The lookup cost 0.55 ms across the three northern near-boundary requests. This reuse applies only within one inference and checks the supplied region, prepared catalogue identity, graph identity and scoring inputs. The cache stores only an eligible early decision that the existing test does not require withholding. [Implementation](terminal_proof_reuse.py) · [Component tests](../../../tests/pipeline_eval/test_terminal_proof_reuse.py)

Both calibration arms, terminal and measurement owners, optimizer paths, numerical grids and all 32 applicable PNGs reproduced the corresponding originals. On the physical case the zero/fitted errors were 1.479/1.849 km. On the northern near omission the errors were 0.103/0.115 km and both publications were invalid because the truth was outside. The initial comparison flagged the grid's own elapsed-time field. The final scorer retains both original artifact hashes, binds them back to each individual run and compares every grid field except that timing field between arms. It rescored the same six outputs. [Run and scorer](terminal_proof_trial.py) · [Geographic reference comparisons](local-future-omissions.md)

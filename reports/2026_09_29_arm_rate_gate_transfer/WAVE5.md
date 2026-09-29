# Wave5 held-out transfer

The combined 0.312 rate gate plus degree-one/block-32 conditioned screen was
run on the prepared DS8 and DS9 panels with the frozen transfer evaluator and
audit. All four gate thresholds were selected on DS7; DS8 and DS9 were not
used for that selection. No ARM binary was run.

## DS8

| Variant | Candidates | Recovered / 785 | Unmatched | Conditioned ms | Fused ms |
|---|---:|---:|---:|---:|---:|
| Ungated Wave4 | 5,632 | 774 | 1,018 | 18.815 | 117.741 |
| 0.312 gate | 3,624 | 773 | 733 | 17.482 | 109.239 |
| Wave5 combined | 3,624 | 773 | 733 | 8.157 | 73.387 |

Wave5 exactly preserves the 0.312 gate's matched reference-hit identities.
Per-rate recovery is also identical: 114/115 at 2.5 MS/s, 199/203 at 5 MS/s,
216/218 at 7.5 MS/s, and 244/249 at 10 MS/s.

## DS9

| Variant | Candidates | Recovered / 908 | Unmatched | Conditioned ms | Fused ms |
|---|---:|---:|---:|---:|---:|
| Ungated Wave4 | 5,632 | 888 | 1,128 | 15.652 | 113.429 |
| 0.312 gate | 3,689 | 886 | 829 | 12.266 | 87.382 |
| Wave5 combined | 3,689 | 884 | 831 | 6.637 | 77.631 |

The difference is confined to 2.5 MS/s. Relative to the 0.312 gate, Wave5
loses two matched sealed-reference identities and gains none. Both identities
are duplicate reference ranks for receiver 1, window 9 of visit 1937 in
session `scan-fw-4e1ee6318427beb7`; both have epoch 247 and approximately
249489.662 Hz tracking CFO. Recovery at 2.5 MS/s changes from 273/275 to
271/275. The 5, 7.5, and 10 MS/s counts remain 251/259, 163/170, and 199/204.

The identity records are stored beside each Wave5 cohort in
`hit-identity-diff-vs-gate-312.json`; the comparison is reproducible with
`compare_wave5_hit_identities.py`.

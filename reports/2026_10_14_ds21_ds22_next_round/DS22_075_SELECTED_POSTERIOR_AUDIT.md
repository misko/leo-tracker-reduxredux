# DS22-075: distinct low-band assignments and a constrained high-band estimate

The full C winner is stationary and has the best raw objective of all six original endpoints, including rejected ones. Only two full endpoints passed acceptance, but accepting another currently rejected endpoint would not improve the training selector. Its configured distance is 77.587 km versus own-low 23.428 and own-high 51.146 km; these distances remain unconfirmed comparisons, not verified accuracy.

A bounded zero-fit audit replayed the three original selected endpoints in their own genuine frames, without transporting nuisance parameters between views.

| Quantity | Full endpoint low observations | Own-low endpoint | Full endpoint high observations | Own-high endpoint |
|---|---:|---:|---:|---:|
| NLL | 22588.166861 | 22870.083114 | 16311.855557 | 16053.085878 |
| Effective signal mass | 1202.063662 | 1163.557748 | 926.336090 | 935.568107 |
| Windows | 1819 | 1819 | 1336 | 1336 |

The farther full solution has better low-band likelihood than the closer separately selected low solution. The high-band separately selected solution improves its own likelihood. Satellite-plus-clutter posterior overlap is 0.482072 between full and own-low, and 0.813017 between full and own-high; MAP identities agree on 47.719% and 81.512% of matched windows. These comparisons align exact window and satellite identities. They demonstrate different inferred assignments rather than only a small smooth displacement.

Full prior components are common timing 0.665932, relative timing 255.290064, and group calibration 0.393558. Own-low components are 0.047833/284.970080/0; own-high 0.172908/253.666116/0. Each native objective and its component accounting replays within 1e-7. No common receiver-clock term exists in these unchanged original C states.

The full winner is interior at radius 4.852901 km in its 25 km disk; own-low is interior at 19.370719 km. Own-high is on its 25 km disk boundary. Its analytic outward derivative is −3.472138 objective units/km, but the prespecified one-sided finite differences at 0.001 and 0.0005 km are +2.048201 and −0.711880. Those finite steps do not yet establish stable agreement with the derivative. No radius expansion, retry, or new fit followed this audit. A smaller-step diagnostic would be a separate bounded test, not evidence already established here.

Source `03ea9bbb4`; five objective evaluations, zero fits, 30.315 seconds, internal cap 120 seconds. Component tests cover posterior normalization/alignment and clutter-inclusive overlap. Actual saved-state objective, prior, domain, and posterior checks passed. Receipt `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-075-selected-audit-v1/report.json`, SHA256 `158f89631f5cd56f3e5a272176001c6dff3c6c17b7c2a1b44e0f452642909a3d`. No reference or held observations were read by the diagnostic.

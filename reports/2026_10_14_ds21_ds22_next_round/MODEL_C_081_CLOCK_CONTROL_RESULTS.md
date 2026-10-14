# DS21-081 matched native receiver-clock control

Adding the existing receiver-clock model improves the selected position error
only modestly:15.114904→13.934381 km. All four matched fits pass independent
KKT checks. This does not solve C's second major DS21 failure.

| Model | Source endpoint | Error (km) | Objective | NLL | Prior | KKT |
|---|---|---:|---:|---:|---:|---:|
| Original | Challenger, selected | 15.114904 | 26250.271159 | 25891.873900 | 358.397260 | 0.000417863 |
| Original | Incumbent | 253.242525 | 28251.044115 | 27838.816660 | 412.227455 | 0.000394163 |
| Receiver clock | Challenger, selected | 13.934381 | 26093.650843 | 25699.474515 | 394.176328 | 0.000103683 |
| Receiver clock | Incumbent | 252.768949 | 27891.975770 | 27392.078889 | 499.896881 | 0.000177763 |

The two source endpoints come from the sealed acceptance-shortfall control.
They are not selected using reference position. Each model receives both
states, unchanged source25 km disks,20-second/600-iteration budget, same bank,
observations, frame, timing priors and fitted c. Clock coefficients initialize
at zero; objective, physical/group gradients, satellite responsibilities and
clutter probabilities nest exactly in the original model. Initializer
projection above1e-12 is forbidden. Original accepted endpoints remain
eligible in the original arm; clock fits are selected separately by training
objective. Reference evaluation follows completion and sealing of all four.

Runtime51.310 seconds,4 new fits,4 qualification objectives. Actual native
nesting and pre-reference validation tests pass (4 total), as does Ruff.
The next six-fit conditional channel-view comparison retains both clock
endpoints and the same full-derived bank/frame/priors to test whether the
remaining full-band error exceeds either half under matched conditions.

Driver `ad3aee7fe`, evaluator `7374cee55`.
Namespace `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-c-clock-control-081-v1`.
Terminal SHA256 `00a6ba825a2757018a553ccb0d411696a7990165137419f914fedcd83ccb16aa`.
Seal SHA256 `3df27779ad1c2866ccc143b86a9da558fbff4fe3abb6de142af022fdfae115b4`.

# The one-fit provisional salvage rule reverts on DS30-0155

The frozen extra fit restored **85 independently nominated observations** at the original curved gate, but lost **39 observations** that had passed that gate at the ordinary seed. The rule requires all original survivors, so it reverted before the provisional paired finish. The ordinary repair then dropped the same two late fragments and published the exact previous cumulative roster and fix. The trial charged **0.184 CPU s**. [Frozen protocol](provisional-salvage-0155-protocol.md) · [Signed comparison](measurements/provisional-salvage-0155.json.gz)

## Where the original roster changed

The sealed crossed fits held the same full named receiver input. With the **named roster**, the named and cumulative fitters produced **0.972 / 1.157 km** and **0.955 / 1.142 km** of horizontal error. With the **cumulative roster**, they produced **1.687 / 1.764 km** and **1.685 / 1.777 km**, respectively. The lists differ by 225 removed and 79 added observations. All 3,273 shared observations retained their component, NORAD, role and signed alias. The paired fitter choice within each list moved the endpoint at most 18.3 m. [Crossed fit experiment](cross-roster-0155.md)

| Stage | Signed component event | Rows |
|---|---|---:|
| Independent salvage | RX1 CH1 T001 renominated NORAD 59267 at alias +1, phase +0.75 s, from the component with 97 named rows | 85 nominated |
| Second curved gate at ordinary seed | RX1 CH1 T001 rejected again | 97 named rows ultimately absent |
| Second curved gate at ordinary seed | Salvaged RX1 CH2 T001 (NORAD 58979) and RX1 CH7 T000 (NORAD 100030) survived | 40 + 39 added |
| Matched finish and common-support repair | RX1 CH6 T001 (NORAD 59267) failed both arms | 61 removed |
| Matched finish and common-support repair | RX1 CH8 T000 (NORAD 100030) failed fitted `c` and was removed in both arms | 67 removed |

The ordinary route started with 3,430 curved rows. Its first gate left 2,940. Independent salvage nominated 386, yielding 3,326 expanded rows. The second gate left 3,051, with six earlier salvage nominations accounting for the 275 dropped rows. The last paired repair took 3,051 curved rows down to 2,923 and kept all 429 predictive rows. The final signed-phase update was unqualified. The first two gates and the late paired repair therefore have different evidence and operate at different times. [Original same-input publication](prospective-0155-solver.md)

## What the extra fit did

The existing policy fit the same expanded 3,326 rows with their independently nominated signed aliases and the original nuisance design. The in-domain seed moved **2.633 km** to `(6.784537, −5.973360)` km east and north of the offer center. The fixed-support objective declined from **34,366.388** to **34,349.076**. Rechecking at this point admitted all 85 nominated rows from RX1 CH1 T001. The same gate now rejected the 39 RX1 CH7 T000 rows that had survived at the original seed. The rule reverted before it rebuilt predictive entries or ran the provisional paired fit. The two late losses therefore proceeded through the same ordinary repair, and the 39 original CH7 rows remained in the published result.

Both arms completed on the original containing offer. The scored publication reproduced the previous cumulative terminal, all 3,352 ordered owners in each arm, the signed 179-point grid and path, and eight encoded and decoded PNGs. All four native orbit legends matched the fitted owners. The saved worker used the original verified inventory, packet, orbit archive and offer. Stock labels, cross-roster outcomes and survey coordinates were used only by the separate scorer.

| Saved route | Horizontal error c=0 / fitted c | RF RMS c=0 / fitted c | Solve CPU | Process elapsed / CPU |
|---|---:|---:|---:|---:|
| Named v3 | 0.972 / 1.157 km | 155.420 / 155.382 Hz | 21.549 s | 25.571 / 25.499 s |
| Archived cumulative | 1.685 / 1.777 km | 154.034 / 154.039 Hz | 15.227 s | 18.271 / 18.228 s |
| Provisional trial, reverted | 1.685 / 1.777 km | 154.034 / 154.039 Hz | 14.586 s | 17.645 / 17.636 s |

The fit and recheck charged **0.183518 CPU / 0.183523 elapsed s** directly. The total clocks compare separate sessions and the candidate process incurred zero input blocks. The faster aggregate clock supplies no measured saving from the added trial. The final location remains 713 / 620 m worse than named v3. This transfer shows that a better in-domain fixed-support objective can exchange track support without satisfying the unchanged recovery rule. [Prior reverted transfer on dense DS30-0008](provisional-salvage-dense.md)

## Reproduce

The single paid run used the committed adapter at `bf91318b3` after protocol freeze `68b7a7703`. Its output remains at `/dev/shm/leo-provisional-0155-run01/`. The untouched numerical rule is [provisional_salvage.py](provisional_salvage.py). The first launcher invocation stopped at a module import before launching a solver. The completed invocation used the source checkout first for the outer launcher and the frozen release first in its isolated worker. The independent scorer uses the source `src` reader for read-only publication verification. No waveform or detector call ran. Nine focused tests passed.

Under the low-priority CPU 2 Gauss lock, run `provisional_salvage_0155.py launch NEW_TMPFS_ROOT` with the original staged request available. Use `provisional_salvage_0155.py score ROOT NEW_RECEIPT.json` with `src` on the scorer import path. [Transfer adapter](provisional_salvage_0155.py)

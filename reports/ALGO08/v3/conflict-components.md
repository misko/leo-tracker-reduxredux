# Conflict components in the paid satellite search

The current search does not split into independent local fits on either saved physical recording. At fixed receiver settings the observed dense DS30-0008 choices form **21 local components**, with at most 22 tracks. Shared satellite phase reduces that to 19 components, with at most 25 tracks. The receiver calibration and smoothing terms join all **112** tracks. Independent medium DS30-0057 similarly goes from 13 local components to **one 39-track component**. The common position also connects all tracks in each arm, and fitted RF coefficient `c` is active on every observed track. [Frozen scope](conflict-components-protocol.md) · [Paid alternatives and component receipt](measurements/conflict-components.json.gz)

| Measured dependency scope | DS30-0008 components / largest | DS30-0057 components / largest |
|---|---:|---:|
| Exclusive observations after the original Graph | 112 / 1 | 39 / 1 |
| Local overlap of gate-passing satellite alternatives | 71 / 10 | 21 / 5 |
| Local overlap including the actually consumed gate-independent nominees | 21 / 22 | 13 / 11 |
| The same choices with shared satellite phase, including disjoint time support | 19 / 25 | 9 / 13 |
| Plus receiver offsets, drift and smoothing | 1 / 112 | 1 / 39 |
| Plus common position, in either calibration arm | 1 / 112 | 1 / 39 |

The observer captured actual visible gate-passing alternatives, the lowest visible nominee consumed by discovery, and their integer alias lifts at each of 16 paid association states on both recordings. It preserved every pre-finalist node digest from the earlier complete publication. A proposal offers exclusive assignments for its track's observations. Two tracks that can use the same satellite over intersecting time intervals enter the local graph because the shared orbit can couple them. The original solver can legitimately assign distinct overlapping observations to that satellite. Among the nominee-inclusive edges, 87 dense and 14 medium satellite overlaps involved different aliases. Equal alias integers on different satellites do not create edges. [Observer and original-port checks](conflict_component_trial.py)

The original Graph enforces exclusive observation assignment before cold association. At its earlier lane arbitration, there were **215 actual polynomial proposals with 31 pairs sharing an observation**, in 195 lane-local components, largest five, on dense. Medium yielded **61 proposals and four overlapping pairs**, in 58 components, largest three. The entire underlying arbitration, including work outside conflict resolution, cost 348 and 85 ms CPU respectively in the diagnostic. These are paid upper scopes for that earlier stage. The exact duplicate rule already removed nine and three proposals in their respective executions. [Pre-arbitration measurements](measurements/conflict-components.json.gz)

## Check against the genuine late owner switch

Replacing only the first 192 visits' short measurements caused the two published arms to reassign the same **222** observations from NORAD **67511** to **63478**. All switched observations occur at visits **3,508–5,571**. The 13,146 canonical native rows after the intervention prefix are identical. Both alternatives occurred on three of the original cold tracks, covering **143 conditional observations**. Those tracks overlap in time and belong to the same local component when taking the union over paid states. Both candidates use alias `+1` on all three. Across the seven affected tracks, 63478 never passed the original observed pre-arbitration gate. No single paid association state exposed both labels on any of the seven tracks. The other **79** switched observations were predictive and occupy four tracks on which neither owner appeared in the original cold choices. The genuine alternative is therefore only partially captured by the nominee-inclusive local union. The gate-only graph would lose it. [Physical intervention](dense-8ms-prefix.md) · [Pinned observation and branch audit](measurements/conflict-components.json.gz)

## Paid repeated work

| Work scope | DS30-0008 | DS30-0057 |
|---|---:|---:|
| Original full-shape profile calls in the diagnostic | 1,792 | 624 |
| Repeated track/satellite/alias labels across paid states | 1,608 | 569 |
| Profile calls with repeated full state and original nominal base identity | 336 | 0 |
| CPU inside those confirmed repeated profile calls | 0.142 s | 0.000 s |
| Prior complete grouped rank CPU | 4.046 s | 1.107 s |
| Prior complete cold phase CPU, inclusive of rank | 5.555 s | 1.346 s |

Dense finalists shared 100–105 of their 112 assignments. Medium finalists shared 37–38 of 39. That similarity supplies no exact reuse credit for their global fits. The repeated-state metric requires the same receiver, phase and smooth parameters, initialization point, method, and the same original nominal array identities. The 0.142 s is the CPU consumed by those verified repeated full-shape profile calls on this diagnostic. The already grouped path has a different cost. Whole-rank and cold-phase clocks are ceilings for substantially broader work. A decomposition that retains the other global fits cannot claim either complete interval. [Dense and medium exact controls](exact-solver-0008.md) · [Medium comparison](exact-solver-0057.md)

These results rule out treating the measured local components as independent exact solvers. A decomposition conditioned on common parameters would still need the shared fit, wider candidate recovery for the observed physical switch, and the original objective verification. This experiment measured two pre-finalist traces only. It ran no new position fits, waveform reads or backing archive reads. Four setup attempts stopped before ranking. The accepted replays ran one rank each under the shared Gauss CPU 2 lock, nice 15, I/O priority 7 and one numerical thread. Twelve focused and adjacent tests passed. The uncompressed receipt SHA-256 is `000e40fb6f7b4d660f2bae5ea4de579d9f780273fd692fe279d052190556622e`. [Component tests](../../../tests/pipeline_eval/test_conflict_components.py)

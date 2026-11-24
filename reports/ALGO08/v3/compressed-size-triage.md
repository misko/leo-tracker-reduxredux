# Smaller compressed members still carry position evidence

On the preselected confirmation recording DS30-0124, skipping the smallest compressed member in each eligible group of four would remove **868 of the 3,584 observations assigned to satellites** in the candidate's fitted solution. An equally spaced schedule at the same sample budget would remove **876** on average. The size rule omits 24.6% of visits and 24.2% of those assigned observations. It offers little isolation of expendable data. [Frozen schedule](compressed-size-triage-protocol.md) · [Per-recording counts and selected attempts](measurements/compressed-size-triage.json)

| Evidence omitted | Development, size rule / fixed-phase mean | DS30-0124, size rule / fixed-phase mean | Retrospective minimum on DS30-0124 |
|---|---:|---:|---:|
| Issued visits | 8,512 / 8,512 | 1,664 / 1,664 | 1,664 |
| ALGO08v3 passing receiver lanes | 6,443 / 6,529 | 1,620 / 1,694.75 | 1,430 |
| Candidate passing receiver lanes | 6,901 / 6,974.5 | 1,710 / 1,822.5 | 1,628 |
| Satellite-assigned observations, fixed-zero calibration | 4,188 / 4,197.5 | 868 / 876 | 740 |
| Satellite-assigned observations, fitted calibration | 4,188 / 4,197.5 | 868 / 876 | 740 |

Each phase control skips the same slot in every complete group. The mean covers the four possible slots. A separate retrospective calculation chooses the member with the fewest true observations in each group. Even that choice drops at least **740 observations (20.6%)** from the confirmation solution. On DS30-0049, the size rule would drop **71 of 268** owners, versus 56.5 on average across fixed phases.

The development rows cover seven measured pairs among the first eight assignments. DS30-0107 had no complete quartet. DS30-0452 was awaiting verification of its relocated input at this snapshot. The confirmation schedule used only the signed compressed and uncompressed lengths, segment order and visit counts. The check then joined those selections to authenticated detector packets and owner digests. Every recording was from the Gauss site.

These are counts from intact full-data solutions. Removing observations could change assignments and move the position in either direction. The support counts provide little reason to pay for a new raw timing or position run of this rule. [Scoring code](compressed_size_triage.py)

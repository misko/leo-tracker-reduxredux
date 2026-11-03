# Recovery identity audit

The eight b1000 fitted-c windows called strongly restored by the existing net-coverage criterion are dominated by one **model-assigned** catalogue ID, but they are not all single-ID segments. Every one has a dominant ID covering at least70% of all original points; seven cover at least85% of assigned points. Window007 is materially mixed: ID66544 accounts for40/54 points and ID59841 for13/54. No independent emitter identity truth is available, and multiple real emitters may occur in a coherent window.

This is a read-only audit of35 saved NPZs, seven complete protocols, all15 requested windows and693 fixed original points. Full source files contain20084 observations. It made zero model/objective calls, zero fits, zero CFO/held scores and no new position or reference reads. It took0.132 seconds under an external120s TERM/125s KILL cap. All saved endpoints are retained irrespective of KKT; these counts do not replace strict scientific selectors. Original c0 is unavailable rather than imputed.

## The eight descriptive strong-restoration windows

Strong restoration retains the prior report's criterion: net assigned gain divided by original missing points is at least80%. It is a coverage label, not a dominance or verified-identity threshold. The70%/85% dominance descriptions above are summaries of observed counts, not fitted or selection thresholds.

| Window | Assigned/N | Dominant model ID | Dominant/N | Dominant/assigned | IDs with≥3 | Switches/eligible adjacent pairs |
|---|---:|---:|---:|---:|---:|---:|
| DSX01-001 | 80/86 | 62052 | 78/86 | 78/80 | 1 | 2/50 |
| DSX01-005 | 33/33 | 67849 | 31/33 | 31/33 | 1 | 1/18 |
| DSX01-007 | 54/54 | 66544 | 40/54 | 40/54 | 2 | 12/34 |
| DSX01-008 | 49/50 | 60127 | 42/50 | 42/49 | 2 | 7/31 |
| DSX01-009 | 34/34 | 67704 | 29/34 | 29/34 | 2 | 3/21 |
| DSX01-010 | 38/46 | 62502 | 34/46 | 34/38 | 1 | 2/21 |
| DSX01-013 | 23/28 | 66854 | 23/28 | 23/23 | 1 | 0/11 |
| DSX01-015 | 32/36 | 58362 | 28/36 | 28/32 | 1 | 4/18 |

## All fifteen fitted-c windows

Each cell is assigned/N followed by the dominant model-ID count. Complete protocols are compared without selecting a different method for individual windows.

| Window | Original | Fixed profile | Expanded profile | b1000 profile |
|---|---|---|---|---|
| DSX01-001 | 13/86; 64936:3 | 79/86; 62052:78 | 45/86; 62052:34 | 80/86; 62052:78 |
| DSX01-002 | 1/35; 60727:1 | 11/35; 66154:10 | 13/35; 66154:12 | 12/35; 66154:10 |
| DSX01-003 | 0/27; None:0 | 0/27; None:0 | 0/27; None:0 | 0/27; None:0 |
| DSX01-004 | 6/44; 46043:1 | 10/44; 59937:3 | 11/44; 59937:3 | 13/44; 62043:3 |
| DSX01-005 | 1/33; 63485:1 | 31/33; 67849:28 | 33/33; 67849:32 | 33/33; 67849:31 |
| DSX01-006 | 12/72; 55493:3 | 33/72; 63434:17 | 36/72; 63434:20 | 34/72; 63434:16 |
| DSX01-007 | 16/54; 59841:13 | 54/54; 66544:39 | 54/54; 66544:39 | 54/54; 66544:40 |
| DSX01-008 | 8/50; 67704:2 | 48/50; 60127:43 | 48/50; 60127:43 | 49/50; 60127:42 |
| DSX01-009 | 4/34; 55489:2 | 34/34; 67704:29 | 34/34; 67704:29 | 34/34; 67704:29 |
| DSX01-010 | 2/46; 59869:1 | 25/46; 62502:22 | 33/46; 62502:31 | 38/46; 62502:34 |
| DSX01-011 | 9/43; 53390:2 | 15/43; 52577:3 | 11/43; 47385:2 | 23/43; 57985:12 |
| DSX01-012 | 14/66; 64212:7 | 16/66; 61912:6 | 27/66; 48117:10 | 25/66; 48117:7 |
| DSX01-013 | 1/28; 68102:1 | 22/28; 66854:21 | 23/28; 66854:22 | 23/28; 66854:23 |
| DSX01-014 | 3/39; 59550:1 | 11/39; 60728:8 | 32/39; 57864:26 | 12/39; 60728:8 |
| DSX01-015 | 6/36; 60728:1 | 33/36; 58362:30 | 34/36; 58362:29 | 32/36; 58362:28 |

Window003 remains0/27 in every fitted-c protocol. The b1000 partial windows004/006/011/012 have dominant counts only3/44,16/72,12/43,7/66, respectively, despite assigned counts13/44,34/72,23/43,25/66. Thus point coverage can conceal substantial fragmentation. Candidate expansion's window014 gain is comparatively concentrated:26/39 points on ID57864 among32 assigned, versus b1000's8/39 on ID60728 among12 assigned. This is a difference between complete algorithms, not permission to splice their per-window outcomes.

The c0 matched protocols are retained separately in windows.csv, summary.json and identity_zero-c.png/.pdf. They are not pooled with fitted-c outcomes. For example, b1000 c0 window005 is33/33 on ID67849, while window002 splits25 assigned points between ID66154(11) and ID63307(10), plus four singletons. Better total counts alone therefore do not establish one recovered trajectory.

## Adjacency, ordering and limits

Switches compare consecutive chronological **observed** rows that are both assigned, in the same RX/channel/actual-RF lane, with gap≤1s. Unassigned rows and larger gaps break adjacency. All exclusions and pair denominators are saved. Zero switches with few eligible pairs are weak evidence; irregular sampling and multiple emitters prevent interpreting a switch as an error. The1s limit is a descriptive reporting convention, not an emitter-persistence prior.

Original assignments and model IDs match the frozen source-context labels. Every NPZ has the exact full ordered source time vector and retained row count. b1000 additionally has exact observation IDs/channels and explicit model RX0/1 to metadata RX1/2 conversion. Older original/fixed/expanded NPZs lack persisted row IDs; their producer/common-observation ordering is source-bound, but equal-time row swaps cannot be independently ruled out from those NPZs alone. This limitation is explicit in summary.json.alignment. No labels from unassigned rows enter identity counts.

Version1 stopped at the receiver-convention guard before any aggregate; its source and plan are preserved. Version2 adds the explicit conversion with two regression tests; it does not loosen any scientific threshold. Seven component tests pass, including denominator/loss retention, exact ordering, empty membership and switch semantics. Source hashes in plan_v2.json are verified before and after the audit.

A next trajectory model should preserve multiple coherent candidate sequences and report per-ID support, residual/time consistency and gaps rather than equate assigned count with verified recovery. These descriptive counts alone do not justify a same-emitter transition prior, truth labels, dropped observations or a model promotion.

Artifacts: summary.json contains all105 rows and complete ID histograms; windows.csv is the flat table; identity_fitted-c.png/.pdf and identity_zero-c.png/.pdf retain the same original denominators for assignment and dominant-ID coverage.

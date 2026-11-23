# DS30-0160 ownership regression

The cumulative fit dropped exactly **114 signed observations** from the stock roster in both calibration arms. All **923** retained rows kept the same observation ID, NORAD and role. There were zero additions, owner switches or role switches. The losses span three RX1 fragments and remove two complete satellite families. The recovered candidate trace places the two curved losses at the **second curved gate**, after salvage had found the original NORADs and full observation spans. [Ordered comparison and trace](measurements/owner-0160-audit.json.gz)

## Exact owner changes

| Fragment | NORAD | Removed role and count | Actual RF, GHz | Capture-relative span, s | Measured signed CFO range, kHz |
|---|---:|---|---:|---:|---:|
| RX1 CH1 T000 | 62127 | 65 conditional | 10.9403125 | 4.613–54.936 | −174.574 to −26.138 |
| RX1 CH5 T002 | 57781 | 17 predictive | 11.9403125 | 49.442–61.494 | +18.487 to +31.535 |
| RX1 CH6 T002 | 57781 | 32 conditional | 12.1903125 | 98.036–121.427 | −117.654 to −44.791 |

Each arm kept 861 of 958 conditional and 62 of 79 predictive rows. The original and candidate track-RMS figures show 29 and 26 fitted-c fragments, respectively, with identical component, NORAD and count labels on all 26 surviving fragments. The ordered row join also proves equality of the surviving ownership in `c = 0`. Observation IDs come from the original session, native receiver and hardware start counter. Time and signed CFO follow the installed winning-observation convention. RX1 denotes original native receiver ID 0. The receipt preserves every removed ID, visit, actual RF and timing record.

## Where the routes separated

Both public fixes use the same full native detector packet, offered region, archive and `history_support` recovery. The original candidate process exited at a wrapper assertion after publication, before it serialized ordered owners. The corrected saved trace reproduces the terminal, encoded figure manifest, recorded path and numerical grid content from that first candidate publication. Its grid elapsed time differs. The cumulative route's first pre-recovery proposal returned a bare `AssertionError` after cold discovery and before recording a support gate, then attempted installed fallback. The recovered `history_support` route completed the research proposal. The captured exception lacks a traceback of its own.

1. The recovered candidate completed all three cold finalists because the prefix comparison was ambiguous. Branch 1 won the two-round candidate cold scores **6297.04 / 6315.90 / 6307.18**, starting both later fits at **(3.759869, −3.118094) km** east and north of the offer center. The original named fit started both recorded arms at **(0, 0) km**. The candidate trace does not expose the named cold finalist scores or its earlier masks.
2. The candidate's first curved gate reduced support from **1,032 to 842** observations. Dropped fragments included RX1 CH1 T000 and RX1 CH6 T002. Fine salvage then nominated all **65** points for 62127 at phase **−4.25 s** and all **32** for 57781 at **−0.25 s**, each at alias lift **+1**.
3. Salvage restored **137** points in total. The second curved gate evaluated the recovered support at the same cold location and left **861**. It rejected both target curved fragments again, even with the salvage NORADs. RX1 CH5 T002 did not enter the four later predictive entries, which contributed **62** points. The retained trace does not give a separate rejection reason for that predictive fragment or the exact failing metric of the two curved fragments.
4. The ordinary joint fit passed both arms on **861 conditional plus 62 predictive** points. The signed phase update did not qualify, so the returned solution was this ordinary fit. The output loss had already occurred before either final position fit. The trace supports a branch and timing diagnosis. It does not isolate how much of the location shift comes from the roster, initial fit location or a changed weighting or phase model.

| Outcome | Stock c=0 / fitted c | Cumulative c=0 / fitted c |
|---|---:|---:|
| Horizontal error | 0.798 / 1.089 km | 1.915 / 2.022 km |
| Published terminal RF RMS | 126.335 / 126.093 Hz | 127.012 / 126.950 Hz |
| Offset from offer center, c=0 | (4.445, −6.072) km | (4.151, −4.723) km |
| Offset from offer center, fitted c | (4.492, −5.498) km | (4.233, −4.550) km |

## One roster-only intervention, scoped but unrun

Capture the installed named solver's selected conditional and predictive context before it builds the publication packet. First reproduce the published owner digest, objective and endpoints in each calibration arm without changing any input. Then take the exact candidate roster as the deletion mask on that named context. Clear the **97** removed conditional observation IDs from the original mask and remove the **17** removed IDs from their complete predictive entry. Preserve the signed frequencies, orbit snapshots, aliases, model, original phase references and prior means, family powers, RF and receiver nuisance design and priors, optimizer domain and budgets. Retain the original nuisance label dimensions so the only change to the objective is the absent row contributions. Leave discovery, salvage, support gates and reassignment out of this intervention.

Give both roster comparisons the verified named seed and phase references for the relevant arm. Read back the unmasked fixed-reference objective at the named endpoint before running one paired masked refinement. Compare the two endpoint displacements with the published stock-to-cumulative displacement and report RF fit separately. Reproduction of that displacement would establish sufficiency of removing the three fragments at the named fit state. A smaller or differently directed displacement would leave seed, phase and nuisance differences as competing explanations. Use the survey only after the fixed paired results are sealed.

The receipts omit the executable stock likelihood context, so this would need **one staged named numerical execution** to capture it. Measured DS30-0160 named solve cost is **12.565 CPU s** including its 179-point grid. The candidate's comparable paired finish cost was **0.121 CPU s**, and the candidate's full numeric solve was **11.584 CPU s**. These are measured budget anchors. The masked pair's time is unmeasured. It needs neither waveform reads nor another standard PNG render. No numerical solve ran in this audit.

## Reproduce the desk audit

Run `python3 -B reports/ALGO08/v3/owner_0160_audit.py NEW_RECEIPT.json` with the original `/dev/shm/leo-v3-saved-0160-pair-01` and corrected `/dev/shm/leo-v3-saved-0160-confirm-01` products present. The script binds and replays both published owner digests, checks the corrected publication against its first output, and emits the signed row deltas and recovered trace. Two focused tests passed. [Receipt reader](owner_0160_audit.py)

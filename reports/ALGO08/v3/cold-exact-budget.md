# Full-observation cold discovery cost on the cumulative route

The full mixed DS30-0008 saved profile placed **4.853 CPU s** in the ordered full-catalogue rank and **1.714 CPU s** in the rest of the cold stage. The same profiled publication took **24.617 solve CPU s** and **28.877 s elapsed** through exit, with exact prior scientific output and all eight PNGs. These clocks include profiling overhead. [Protocol](cold-exact-budget-protocol.md) · [Complete profile](measurements/cold-exact-budget-profile.json.gz)

| Scope in the actual cold profile | Calls | CPU, s | Attribution |
|---|---:|---:|---|
| Ordered full-catalogue rank | 1 | 4.853 | Inclusive |
| Cold work outside rank | 1 | 1.714 | Disjoint from rank |
| Native posterior kernel | 67 | 1.565 | Exclusive across rank and remaining cold work |
| Broad association | 16 | 1.673 | Inclusive, within rank |
| Whole-curve white profile | 1,792 | 0.843 | Inclusive, within broad association |
| Initial discovery statistics | 13 | 0.798 | Inclusive, within rank |
| Projector evaluation | 20 | 0.589 | Inclusive, overlaps association and ranking |
| Phase-seed improvement | 3 | 0.408 | Inclusive, within rank |

The active path already reuses duplicate associations, nominal centre gathers and graph edges, and completed only the leading finalist after its three ordered prefixes. Previous time-moment shortlists lost the original winner and exact rescoring could not recover it. The exact representative-contrast filter cut full profile calls without a comparable rank-time reduction. Reusing common unweighted likelihood blocks is possible, but common posterior coefficients and final noise weights differ between finalist assignments. The entire observed native adapter cannot yield a multi-second saving on this cold scope, even before preserving full objective calls. [Earlier race](cold-finalist-race.md) · [Existing centre reuse](cold-track-row-transfer.md) · [Exact track-moment rescore](track-moment-exact-rescore.md) · [Assignment reuse ceiling](dense-assignment-reuse.md)

## Sparse row substitution on the original scorer

Even with nominal rows cached, the dense profile copied 637,750,080 bytes to overwrite 2,237,472 shifted cells. The prototype backs up only the shifted rows, temporarily substitutes their original scaled predictions in the original Fortran-order array, calls the pinned full-observation curve profiler, then restores the cache even on exception. A private visibility mask preserves the ordinary reducers and all exact row numbering. Unsupported source, borrowed layout or profiler binding retains the ordinary path. [Frozen comparison](cold-borrowed-rows-protocol.md) · [Implementation](cold_track_row_reuse.py) · [Tests](../../../tests/pipeline_eval/test_cold_track_row_reuse.py)

| Saved pair | Full copy → backup bytes | Rank CPU, s | Cold CPU, s | Whole CPU, s | Whole elapsed, s |
|---|---:|---:|---:|---:|---:|
| DS30-0316 medium | 238,200,512 → 2,905,648 | 1.378 → 1.421 | 1.793 → 1.857 | 12.189 → 12.771 | 12.194 → 12.774 |

The medium candidate ran first. It preserved six ranked assignments, the exact selected branch and phase reference, both calibration arms, 2,002 ordered observation-owner-role rows per arm, exact grid/path and eight encoded and fully decoded PNGs. The lower counted copy traffic did not improve the measured medium process or rank. Nineteen component tests passed, including restoration after a thrown exception and exact Fortran-order likelihood diagnostics. Both completed medium workers had zero input blocks. [Medium pair](measurements/cold-exact-budget-medium.json.gz)

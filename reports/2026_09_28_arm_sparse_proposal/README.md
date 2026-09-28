# Sparse coarse proposal with full local repair

This report contains a proposal experiment, not an exact coarse replacement.
It starts from verification-fusion V1 and changes only how coarse candidates
are proposed.

Compile-time budgets select evenly spaced subsets of the original 16 frames
and 12 anchor symbols: 1/3, 2/6, or 4/12. The cheap grid still evaluates every
epoch and all 11 public CFOs with the original samples, templates, per-position
normalization, magnitude, and local addition order. It retains 32 separated
peaks using the established circular epoch/CFO separation.

The exact selected indices are `floor(i*16/F)` for frames and
`floor(i*12/S)` for symbols. Thus 1/3 uses frame 0 and symbols 0,4,8; 2/6 uses
frames 0,8 and symbols 0,2,4,6,8,10; and 4/12 uses frames 0,4,8,12 and every
symbol. The follow-up 8/12 budget uses even frames 0 through 14 and every
symbol. `LEO_SPARSE_CENTERS` is independently overrideable and defaults to 32.

For each proposal center, the union of center ±2 epochs is cleared and
recomputed by the original `coarse_fp32_cell`, which uses all 16 frames, all 12
symbols, and all CFO lanes. An explicit eligibility mask admits only repaired
interior epochs whose two linear neighbors are also repaired; endpoint epochs
require their sole in-range neighbor to be repaired, matching the baseline's
implicit `-INFINITY` outside the grid. The original local-peak
scan and top-eight retention then run on those eligible cells. This prevents
an unrepaired or hidden grid boundary from creating a final peak. Fine,
conditioned, fused verification, and final GLRT stages are unchanged.

The 16-frame/12-symbol build is a control: it runs the original complete
coarse grid and the unit requires byte-exact grid parity. Sparse-build units
cover all rates, partial and full nonzero inputs, and zero inputs; every
eligible repaired cell must exactly equal the original full grid. These tests
establish repair mechanics, not proposal recall.

Repair proves exact scores only around proposed centers. It cannot guarantee
recovery of a true full-grid peak outside those neighborhoods, nor a peak that
moves by more than the repair radius. Recall must be measured against the
original individual-hit inventory.

The host64 full-budget control matches all 11,264 candidate objects
and 1,669 original hits. The 32-center sparse screens recover only 101/1,669,
403/1,669, and 1,036/1,669 hits at 1/3, 2/6, and 4/12 respectively, so all
three fail the 80% quality gate. With 128 centers, 4/12 recovers 1,247/1,669
mixed-rate hits (74.72%) and 388/485 at 2.5 MS/s (exactly 80%), so it still
fails the mixed gate. The 8/12, 128-center build recovers 1,521/1,669
mixed-rate hits (91.13%) and 454/485 at 2.5 MS/s (93.61%), passing both host64
gates. Completed host704 testing recovers 18,404/19,581 original hits with
eight frames and 15,545/19,581 with four frames. At 2.5 MS/s the respective
figures are 4,347/4,573 (95.06%) and 3,715/4,573 (81.24%). Four frames fails
80% at 7.5 and 10 MS/s and across the mixed-rate cohort.

On the matched four-dwell ARM set, eight frames takes 27.807735 s/dwell
(1.21290x) and recovers 113/119 hits. Four frames takes 22.918122 s/dwell
(1.47168x) but recovers only 87/119 (73.11%). Host results on these same
four cases agree. Thus four frames is not a robust 80% setting even though
the larger 2.5 MS/s host aggregate exceeds 80%.

The current 1/3 source also passes ASAN/UBSAN, including all-rate endpoint
retention fixtures. Every normal and sanitizer source snapshot and receipt,
including rejected variants, is archived under `builds/`. Both selected
128-center ARM units pass. See REPORT.md for CPU0 measurements, individual
hit and window counts, independent audits, and the remaining real-time gap.

# Proposal8 half-grid tracking min1 with full coarse

This artifact uses eight evenly spaced proposal frames, a half proposal FFT
grid, and min1 neighbor proposal tracking, while retaining the 16-frame coarse
stage and all 22 downstream windows and final GLRT frames. It is an explicit
approximate proposal tradeoff.

Copied stale `arm4`, `host32`, and `host704` evidence from the coarse8 triple
artifact was removed before qualification. Fresh host32 recovered 906/948
reference-positive hits. Fresh host704 recovered 18,805/19,581; by rate it is
2.5: 4,442/4,573, 5: 5,244/5,466, 7.5: 5,036/5,186, and 10: 4,083/4,356.
The ARM build is cross-compiled only; no ARM result is recorded here.

Root's fresh ARM4 physical result used this artifact: 578.7260805 ms per dwell,
116/119 recovered hits, and 170 emitted candidates. This is a physical
qualification result, not copied evidence.

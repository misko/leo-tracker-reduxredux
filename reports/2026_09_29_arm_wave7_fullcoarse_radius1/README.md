# Full-coarse proposal8 half-grid tracking min1, radius 1

This approximate variant retains all 22 windows and full 16-frame coarse and
final GLRT paths. It reduces each proposal region to radius one.

Host32 recovered 904/948 and host704 18,465/19,581. Root's ARM4 physical run
measured 506.3549985 ms per dwell, recovered 108/119 hits (90.76%), and emitted
154 candidates. These results are approximate tradeoff evidence.

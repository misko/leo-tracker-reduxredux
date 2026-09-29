# Frontier radius-1 PGO qualification

This is an approximate proposal method: eight proposal frames, half proposal
FFT grid, min1 neighbor tracking, radius-one proposal regions, and full
16-frame coarse and final GLRT processing. It uses PGO profiles for proposal
core, proposal tracking, conditioned CZT, FFT, and fused probe.

Root's disjoint ARM heldout32 run covers 32 dwells and 704 windows, not the
full DS7 cohort. It measured 473.79482775 ms per dwell and recovered 854/921
standard hits with 1,116 emitted candidates. The same panel's Wave5 result was
917.6329126875 ms and 904/921, a 48.368% runtime reduction with 50 fewer
recovered hits. The 11 ARM units passed.

For context only, the exact histogram-PGO option measured 758.592 ms and
recovered 904/921 on this panel. These outcomes are separate methods: the
frontier result does not claim exact parity or full-cohort quality.

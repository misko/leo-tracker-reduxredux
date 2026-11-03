# Curved-family cohort repair checkpoint

The active goal is unachieved; no verified sub-0.5 km localization. This report
adds concrete fixed-known-GPS association evidence and controlled model audits.
Read `curved_only/` as the authoritative phase pipeline. Parent-level inventory,
screen, competition and association are preserved superseded v1 artifacts.

V1 mistakenly locked competing candidate phases even when supported only by
linear fragments. The correction locks only phases with admitted measured-curved
support in either arm. Old linear tracks cannot nominate, rank, lock or veto
curved phase proposals; their final matches still require every gate. The v1
source files are preserved under `pre_curved_only_lock_source/`.

V2 inventory is complete. Eight nominations are unchanged (4 S01, 3 S03, 1 S04).
Sixteen scalar phase screens and ten full-bank 601-phase competitions complete
successfully. Each passing family remains unique even with the previously
linear-only competing owners unlocked. Accepted phases: S01 69546 -0.70 s,
100320 -3.70 s; S03 59552 -0.75 s, 64112 -0.65 s; S04 61912 -1.40 s.
Gate-passing ranges are not confidence intervals or authenticated identity.
S01 62052/63474 and S03 59547 remain rejected, without member pruning.

V2 association completes all five scans and both c arms. Gains are +282 / 0 /
117 / 105 / 0 points by scan in each arm, total +504 (400 curved, 104 linear).
No old losses or relabels occur in this dataset, though old linear survival is
not a phase-selection criterion. c0 10405 -> 10909 / 20084 (54.3169%), 335
merged tracks; fitted-c 10386 -> 10890 / 20084 (54.2223%), 312 tracks. All 18338
original Graph IDs remain accounted for, including two explicit background IDs.
The earlier 173-point single-family gain is included, not additional to +504.

Independent RF-reference and phase-prior sensitivity searches are complete at
parent level (12 each, matched c arms). Alternative RF coefficients fail the
frequency-fit comparison even when their endpoint happens to lie nearer GPS;
they are rejected as model repairs. Phase-prior floors do not remove the bias.
No absolute RF/UTC calibration was inferred from the input adapter integrity
audit. See README for the complete tables, qualifications and input authority.

All bounded jobs are terminal. Scalar screen 48804; v2 full competitions
19545/8819/8358/33033/95824/24740/17972/25585/98298/77003; final association
43164; report rendering 59057. Earlier v1 and model sensitivity handles are
terminal as recorded in their artifacts. The 65-test focused suite and Ruff
checks pass. No new collection, QNAP changes or golden updates.

Separate continuation `../2026_10_17_position_information/` tests nuisance
identifiability, actual DS22 merging and a blind common-position pilot. The
larger position and wider-DS22 requirements remain active.

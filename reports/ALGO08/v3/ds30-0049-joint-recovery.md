# DS30-0049 joint short-lane restoration

The joint perturbation reduced horizontal error by **940.291 m fixed-zero**
and **836.433 m fitted**, exceeding the sums of the independently measured
improvements by 86.732 m and 197.555 m. The fitted result recovered 31.93% of
the original 2.620 km error gap. Both arms still exceed the original installed
error by more than 1.7 km. [Frozen receiver and scoring protocol](ds30-0049-joint-recovery-protocol.md) · [Recorded scientific worker and score](measurements/ds30-0049-joint-recovery.json.gz)

## Verified receiver perturbation

The generation-2 installed and sparse receivers share the original region,
clocks, recording and inventory authority, 986 issued visits, 54 exclusions,
and 932 admitted stereo visits. The joint derivation inserts 104 installed
selected tuples into literally empty sparse short lanes and substitutes 72
installed tuples for disagreeing short winners. RX0 contributes 30 insertions
and 59 substitutions. RX1 contributes 74 insertions and 13 substitutions.
The 242 anchors, 284 strict matches, 161 sparse-only positives and 1,001
both-empty short lanes preserve the original sparse rows byte for byte under
the canonical encoding. All 1,864 opportunities remain in order, with 704
winners versus 600 originally.

An independent read of each prior single-intervention packet reproduced both
disjoint sets of edits and all donated tuples exactly. No owner, satellite or
geographic reference entered derivation. The earlier four-edit anchor
publication also replaced the strict matches and excluded sparse-only
positives. It answers a different question and uses 543 pre-Graph rows.
[Four-edit proof](ds30-0049-anchor-only.md)

The sealed packet has SHA-256
`e7b515480f5bdcefb021e70afc8f3a76fcd73f2e909871101503e1a89e098fb9`.
Its independent research recipe and ordered edit ledger are bound to both
authentic receiver packets. Preparation cost 0.122 s wall and 0.119 s CPU.
The installed-runtime preflight verified the original causal cutoff, all
48 staged catalogue bodies in memory and the existing verified portable
index. The solver and handoff call counters stayed at zero. The exact packet,
plan, watch and direct admission receipt are kept read-only in
`/srv/postgres-nvme/leo-ds30-research-worktrees/0049-joint-recovery-archive-01`.
The original worker directory is `/dev/shm/leo-v3-joint-recovery-0049-01`.

## Measured controls and joint result

| Saved publication | Fixed-zero error | Fitted error | Fixed-zero gain over sparse | Fitted gain over sparse |
| --- | ---: | ---: | ---: | ---: |
| Original installed | 1,825.738 m | 1,420.395 m | 2,646.184 m | 2,619.837 m |
| Original sparse | 4,471.923 m | 4,040.232 m | 0 m | 0 m |
| Empty lanes only | 4,148.133 m | 3,662.974 m | 323.790 m | 377.258 m |
| Shifted winners only | 3,942.154 m | 3,778.612 m | 529.769 m | 261.620 m |
| Sum of the two independently measured gains | | | 853.559 m | 638.878 m |
| Joint intervention | 3,531.632 m | 3,203.799 m | 940.291 m | 836.433 m |

Both single interventions start from the same sparse packet. Their sum is an
arithmetic reference for the interaction after Graph and ownership rerun. The
joint worker passed the 250 m two-arm development gate. This diagnostic uses
installed selected outcomes. It measures a saved-packet perturbation.
[Empty-only control](ds30-0049-empty-recovery.md) · [Shifted-only control](ds30-0049-shifted-winner-repair.md)

The ordinary lean route ran Graph once and assigned 508 observations across
17 tracks, versus 399 across 15 on sparse. Final ownership was 334 IDs,
two satellites and nine tracks in each arm. The joint fit retained 262 of
268 sparse owners with the same satellite and role, added 72 and dropped six.
It retained 318 of 320 installed owners with the same satellite and role.
This includes 43 of the 44 installed-owned insertions and all 48 installed-owned
shifted rows in each arm. The joint roster owns 44 insertions total because
one different inserted ID became owned.

Conditional RF RMS was 145.630 Hz fixed-zero and 145.652 Hz fitted. The
original sparse values were 168.634 and 168.814 Hz, and installed values
were 129.663 and 129.671 Hz. The joint all-owned figures were 163.944 and
159.130 Hz on its broader ownership, versus 168.634 and 168.814 Hz sparse and
145.914 and 141.298 Hz installed. Frequency and geographic gains apply to the
achieved supports. Both arms returned an interior fix in the signed original
25 km offer. The standard 179-position grid replayed both endpoints with
zero objective discrepancy. The path bound the same input, owners, terminal
and position PNG. All eight standard PNGs were independently decoded and verified.

## Conditioned comparison to full short-lane restoration

The previously scored anchor-only control takes installed 20 ms factors on
every short lane and preserves the sparse full-anchor factors, including the
twelve extra anchors. Its charted installed-packet reference had exact
endpoint parity with original installed. Both files and controls used the
same original offer and scored against the same independent receiver reference.

| Ordered comparison | Fixed-zero improvement | Fitted improvement |
| --- | ---: | ---: |
| Original sparse → joint, sparse anchors and ordinary matches retained | 940.291 m | 836.433 m |
| Joint → all short lanes restored, same sparse anchors | 793.312 m | 750.904 m |
| All short lanes restored → installed, removing twelve sparse-only anchors | 912.581 m | 1,032.499 m |
| Cumulative sparse → installed | 2,646.184 m | 2,619.837 m |

The middle contrast also replaces 284 strict matches and removes 161 sparse-only
short positives together, leaving 543 observations and 323 owners per arm.
Four of the 323 owners use the extra anchors. The final contrast is the
anchor effect conditioned on complete installed short-lane restoration.
The three increments telescope the measured endpoints along this order.
Different orders can change the support and interactions.
[All-short-restored and retained-anchor control](ds30-0049-anchor-only.md)

## Independent transfer inputs

DS30-0086 has the complete verified original generation-1 pair
`407765fa47754cc99556143888b286e88f4674ab21836d3f437ac8af4c2ca439`.
Both original offers agree exactly. The independently retained installed
and genuine unfiltered sparse packets are byte-identical to the official
native digests `8a56dd84…` and `3a5063c9…`. Both validated saved copies and
all 50 original causal bodies are currently resident, as is the pinned
portable index. Ordinary charted sparse has archived full scientific parity
with its original publication. An existing charted installed-packet result
supplies a fixed-fitter comparator. DS30-0086 and DS30-0049 are separate
captures from the same roof. [Exact original pair and saved crossover](field-receiver-solver-cross-0086.md) · [Original mixed saved parity](sparse8-cfo-epoch.md)

The completed transfer improved both arms relative to original sparse by
152.088 m fixed-zero and 82.864 m fitted, below the 250 m DS30-0049
development yardstick. [Joint DS30-0086 result](ds30-0086-joint-recovery.md)

## Admission record

The first 15-second watch found no qualifying storage deferral. A separate
direct attempt returned `EAGAIN`; an earlier import error stopped before
admission. Both previous receipts record zero numerical children.
[Earlier packet custody and admission receipts](measurements/ds30-0049-joint-recovery-custody.json)

The subsequent bounded waiter kept the lease free during all nonquiet polls.
After 3.511 seconds it obtained the shared lease nonblocking, reconfirmed
the live driver had no active child, and rechecked all 48 cached bodies and
the portable operand before spawning one worker. The bulk and local weighted
queue averages were 0.867 and 0.148, and full I/O PSI avg10 was 0.90%.
The verified portable index attached with 17 sidecar hits, eight original
staged bodies in the used set, and zero fallback. The worker exited normally
after **8.194 s wall and 7.418 s CPU** on CPU2, nice 15, idle I/O, and one
numerical thread. It charged 176,424 process input blocks and 384 major faults
across the full saved child. It used one bound handoff and performed no
receiver or selected-history rerun, raw waveform access, or backing reads.
Scoring took place after the prediction was sealed and the lease released.
The worker made no end-to-end receiver measurement.

The worker's source froze at `55f8c5950` and the waiter at `e1c4a8a49`.
The prediction SHA-256 is `749757161fc1e525d20b103035664f3e33b80f76d1fad0ef790b3bc9c577225b`.
The independent score SHA-256 is `67fc475c3136d63cf5f7518578a809cb3534f0ac51ebee50cac4b150a015b80b`.
Twenty-two component and adjacent checks passed.

# Actual incremental demand on the physical 20/8 ms receiver

The incremental reader brought forward the first verified stereo
callback by **30.0–31.2 ms** and cut **74.3 MiB** of peak RSS on the
resident DS30-0169 member. It did not improve complete acquisition in
both orders. Acquisition CPU changed **+4.57 ms and −1.84 ms**. The
complete fresh worker was slower in both comparisons. The trial stopped
at the frozen gate, so there is no dense transfer or whole-recording
measurement.

| Fresh run order | Source reader | Acquisition CPU / wall (ms) | Member scope through signoff CPU / wall (ms) | Launch through exit CPU / wall (s) | Peak RSS (MiB) |
|---|---|---:|---:|---:|---:|
| A → B | Released whole | 260.618 / 260.624 | 962.113 / 962.157 | 2.031 / 2.033 | 329.86 |
| A → B | Incremental | 265.189 / 265.195 | 984.203 / 984.246 | 2.140 / 2.142 | 255.60 |
| B → A | Incremental | 263.884 / 263.890 | 995.211 / 995.253 | 2.185 / 2.186 | 255.48 |
| B → A | Released whole | 265.728 / 265.964 | 990.991 / 991.488 | 2.066 / 2.068 | 329.77 |

The whole reader made one ordinary read of **78,852,856 bytes** in each
process. The candidate pulled the same bytes in **76 read operations**
of at most 1,048,576 bytes as the installed Zstandard stream requested
them. Both raw read paths used actual demand with no injected release
times, sleeps, staging copy or prefetch helper. Timed read CPU fell
14.469→9.121 ms and 14.773→8.922 ms. Incremental compressed SHA updates
used 15.737 and 15.714 ms. Complete acquisition outside the native
calls fell **1.543 and 5.042 ms**. The unchanged native calls cost
**6.114 and 3.199 ms** more in the respective comparisons. The member
scope includes descriptor open, pinned runtime checks, the receiver and
the signed evidence write. Through-exit additionally includes
interpreter/module setup and parity checks.

## Verification and memory

Both release-order comparisons started and ended with all **19,252
payload pages** plus the full signed index and manifest resident. All
four processes charged zero input blocks. Linux tmpfs residency limits
the measurement to this authenticated resident source. It gives no
time distribution for real cold or network storage. The previous
incremental-ingress experiment used a 20/12 ms receiver and replayed
arrival readiness timelines. Its earlier seal improvement does not
transfer to this actual 20/8 ms input. [Prior incremental measurement](incremental-ingress.md)

Measured from compressed demand, first verified callback was
47.429→17.395 ms and 48.542→17.385 ms. Authority still required
complete compressed and decoded verification. From the same demand
boundary, the final sealed packet went **259.987→264.478 ms** and
**265.227→263.194 ms**. Advancing provisional detection supplies no
early authoritative result. The reviewed feed retains the original
index and independently verifies each immutable decoded window before
the receiver sees it. It verifies all compressed bytes, final digest,
EOF and stable descriptor before the packet can escape, and retains the
original whole-decoded member and framing checks.

All runs verified the same 64 original decoded I/Q digests, excluded the
same 13 visits and allocated the same 16 full and 86 short native
calls to the 51 admitted stereo opportunities. Original timing, signed
CFO, scores, candidate rank and clocks match the authenticated earlier
20/8 ms reference. The packet SHA-256 in all four runs is
`b2a16bc1290bd3cabf383e85cd32d2438e3c84ccd4cac25f4ba168738314e9eb`.
No new physical scope was opened. The memory result applies to this
one-member implementation, whose bounded compressed objects avoid the
whole original compressed allocation.

## Reproduce

The [protocol](incremental-live-eight-protocol.md) was frozen at
`89d464ad9` and the [runner](incremental_live_eight.py) measured at
`9bebcf220`. Use `python -BPs -m reports.ALGO08.v3.incremental_live_eight
launch FRESH_TMPFS_ROOT` with the released Python and original
research and release import paths under the existing low-priority Gauss
CPU2 lock and a single numerical thread. The pinned
[receipt](measurements/incremental-live-eight.json.gz) records commands,
all four scopes and the exact failed transfer gate. Eight component
tests passed, including unpaced delivery, late compressed/decoded
authority failures, immutable retained samples and cancellation before
commit. No dense loader or numerical publication ran.

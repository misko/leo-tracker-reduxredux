# Fixed-window proposal diagnostic: repeated recovery, extra cost

The study completed 171 window searches over all 57 inactive receiver visits
from the 64-visit local-tracking development replay. It finished in 21.96 seconds
with stable sources and unchanged IQ. No held-out recording was opened. The
pair-geometry unit test passes, covering late-to-earlier confirmation, timing,
frequency, nonoverlap and missing evidence.

Each of the fixed seed windows 0,5,10 independently recovers the same eleven
reference-associated inactive receivers: three at 2.5 MS/s and eight at 5 MS/s.
The first accepted candidate is used; later candidates are not selected by
reference agreement. Seed10 also produces one unmatched 2.5 MS/s output.
Seeds0/5 produce no new unmatched outputs in this particular development cohort.

| Rate | Inactive receiver visits | Seed0 mean search CPU | Seed5 mean search CPU | Seed10 mean search CPU |
|---|---:|---:|---:|---:|
| 2.5 MS/s | 28 | 64.74 ms | 61.68 ms | 63.83 ms |
| 5 MS/s | 29 | 174.33 ms | 192.39 ms | 187.17 ms |

Timing includes the window conversion, ten-candidate acquisition, Python scores,
tone-conditioned native evidence and three-integer raw early confirmation. It
excludes primary tracking, IO and initialization. It is not a complete detector
benchmark. All three seed searches run independently for every target; this is
not a live schedule with early exit across windows or a two-acquisition visit cap.

Receipt-only accounting for trying seed0 then seed5, stopping on the first active
pair for each receiver, costs 105.57/280.74 ms per original visit at the two rates
for search alone. Trying 0,5,10 costs 156.13/409.49 ms per visit. Neither schedule
adds a recovery here. These sums use measured independent searches and do not
measure an integrated schedule, cache effects, or the required primary cost.
The three-window schedule already consumes more than one tenth of the earlier
application CPU on this cohort before primary processing is added. Do not
promote it as a 10x solution.

## Implication for the next candidate

This cohort lacks a useful temporal acquisition challenge: every recoverable
inactive identity is recovered at every seed. It does not invalidate the
separate holdout evidence of later-window-only reference detections, and does
not prove that probe0 is universally sufficient. Expand the development cohort
to fixed, disjoint sessions or predeclared intermittent-signal fixtures before
selecting the adaptive search policy. Do not tune and requalify on the consumed
holdout. An integrated candidate also needs control tests because searching
more windows increases opportunities for unmatched detections.

The measured search cost reinforces the original caching opportunity: reusing a
recent recovered timing/frequency hypothesis with fresh confirmation could avoid
repeating acquisition. That requires local timing measurement, bounded physical
frequency innovation, key/expiry checks and fallback on failed evidence. The
earlier zero-drift cache diagnostic failed timing agreement, so simply copying
the last rescue result is not justified. No rescued-track speedup is claimed by
this proposal study. The active unmatched-frequency identity also remains beyond
the reach of an inactive-only rescue.

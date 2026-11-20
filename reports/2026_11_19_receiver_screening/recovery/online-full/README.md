# Sequential native smooth-clock stop on the full roof corpus

Each native worker receives its own causal sample-counter prefix and independently rebuilds Graph at 120, 180, 240 or 300 seconds. The full trial applies the pilot's unmodified 1 km agreement rule, four shared fitted NORADs and two shared orbits with new observations. Each arm takes its first qualifying point and stays resolved while the other arm continues. The runner stops launching workers when both arms resolve. At the deadline unresolved arms take the ordinary 300-second decision. [Frozen protocol](PROTOCOL.md) · [Source binding](source-lock.json) · [Roster and input authority](plan.json)

The comparison uses archived smooth-clock terminal outputs. The original request digest, causal catalogue, native file, deployed sources, byte count and probe count establish the terminal frontier where the fresh run can verify it. The compact-v5 secant comparator uses the existing sealed matched roof records. Its input support is the whole original capture. The calibrated controls and stopping results are scored on the same frozen site. The prior nine distant and 32 close omissions form separate panels. [Pilot and direct terminal parity](../online-prefix/README.md)

The first concurrent run exposed a race in the host-side prefix slicer. Several threads could change the pilot helper's temporary cutoff while another thread was slicing a recording. The audit found 126 affected queries. Those receipts were excluded from scoring and chart discovery. The rerun serializes that host-only slicer and checks both sides of every sample frontier before launching a worker. The original eight-case pilot prepared inputs serially. The receiver, stop rule, and roster are the same in the rerun. [Discarded pass receipt](discarded-host-cutoff.json)

## Coverage, accuracy and omissions

The corrected run completed all 176 offers. The scorer independently verified all 605 fresh prefix frontiers and 176 complete terminal frontiers. Each arm published 122 of 135 matched roof offers. Zero calibration selected 33 at 180 seconds and another 38 at 240 seconds. Fitted calibration selected 41 and another 32. The remaining publications came from the ordinary 300-second deadline. [Sample frontier audit](frontier-audit.json) · [Sealed predictions](raw.jsonl.gz) · [Scores](scores.json)

| Matched roof receiver | Published, zero / fitted | Within 1 km, zero / fitted | Median position error in km, zero / fitted | P95 position error in km, zero / fitted |
|---|---:|---:|---:|---:|
| Stable native stop | 122 / 122 | 35 / 43 | 1.327 / 1.290 | 4.463 / 4.512 |
| Native terminal | 119 / 119 | 35 / 41 | 1.530 / 1.284 | 4.463 / 4.751 |
| Compact v5 secant | 135 / 135 | 73 / 68 | 0.977 / 0.989 | 2.936 / 2.817 |

The stable rule retained all 119 terminal publications in each arm and added three. Median paired geographic change across those common publications was 0 km in both arms. The 122 paired comparisons with compact v5 give median stable-stop disadvantages of 0.355 km and 0.291 km at zero and fitted calibration. Median conditional RF RMS was 149.68 / 121.90 Hz at stable stop and 151.72 / 126.03 Hz at the native terminal. Compared with compact v5 on paired publications, the stopped conditional RMS increased by a median 73.92 / 47.87 Hz. The frequency and position metrics use separate evidence.

| Omitted cohort | Stable native stop, false fixes per arm | Terminal smooth clock, false fixes per arm |
|---|---:|---:|
| Nine distant omissions | 0/9 | 0/9 |
| Thirty-two close omissions | 3/32 | 3/32 |

Both arms returned the same three false offers as the terminal, all at the ordinary 300-second deadline. DS26-0102 errors were 4.548 / 4.678 km with truth 1.89 km outside. DS26-0235 errors were 8.242 / 8.293 km with truth 1.50 km outside. DS26-0070 errors were 14.549 / 14.964 km with truth 1.68 km outside. Every omitted offer reached the deadline without an early stable publication. [Distant controls](distant-omitted-positions.jsonl.gz) · [Close controls](near-omitted-positions.jsonl.gz)

## Timing boundary

The measured workers process stored native GLRT factors on a pinned host. The acquisition and delivery clock brackets come from each original recording. The time scenario starts each worker after the later of its nominal sample cutoff, last included delivery and completion of its predecessor. The sequential work was actually executed to the selected stop. The scenario assumes that measured host work can overlap acquisition. It excludes raw IQ detection and physical target hardware timing. The terminal comparison uses its archived host duration. [Availability and position coverage](published-by-time.png)

Across the 119 common publications, median scenario time was 244.9 s at zero calibration and 244.1 s with fitted calibration, compared with 306.2 s at the terminal. Among earlier publications, the median time gain was 63.7 s at zero calibration and 122.2 s with fitted calibration, reflecting the different mix of 180- and 240-second stops. Every early publication advanced its host scenario, by at least 60.6 s. Maximum measured worker wall time was 8.35 s.

The corrected nine-CPU run finished in 289.1 s, with no failed or timed-out workers. It launched 605 workers and stopped each pair after both arms resolved. Thirty offers used two workers, 39 used three and 107 used four. Repeated work across the cohort consumed 1,996.63 summed wall seconds and 1,711.77 CPU seconds. Per matched offer, median worker totals were 10.37 wall seconds and 8.85 CPU seconds, including any worker needed only by the other arm. A single archived terminal job had medians of 6.03 wall seconds and 5.68 CPU seconds. Compact-v5 archived wall time had a median of 129.88 s. The archived jobs ran under their own host conditions. Constructing a prefix file offline had median measured staging overhead of 0.54 s per job. This staging validates the complete archive and is accounted for in the measured batch wall time. The acquisition scenario uses native worker cost after delivery of each available prefix.

## Reproduce

Use the native deployment bundle and the original causal archive declared by the pilot. The new work path stores one temporary native prefix at a time per active case. The report contains compressed per-attempt receipts and eligibility decisions, without duplicating the original native RF corpus.

```sh
mkdir -p /tmp/online-full-report
.venv/bin/python -m tools.pipeline_eval.qualification.online_full \
  --work /tmp/online-full-work --report /tmp/online-full-report \
  --cpus 0 1 2 3 6 8 9 10 12 --budget-s 390
.venv/bin/python -m tools.pipeline_eval.qualification.online_full_results \
  --report /tmp/online-full-report
.venv/bin/python -m tools.pipeline_eval.qualification.online_full_figures \
  --report /tmp/online-full-report
```

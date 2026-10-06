# Ten-minute capture gap and exact Hough selection

On 2026-10-06 the automatic adaptive capture timer was changed from a
three-minute wait to a ten-minute wait after the capture service finishes.
The roughly five-minute capture and 50/50 2.5/10 MS/s policy remain unchanged.
This lowers nominal input from about 7.5 scans/hour to about 4 scans/hour;
service overhead can make the actual rate lower.

The installed override is
`/etc/systemd/system/leo-v052-adaptive.timer.d/zzz-ten-minute-gap.conf`, copied
from `deploy/systemd/leo-adaptive-ten-minute-gap.timer.conf`. It clears calendar
and previous monotonic settings and sets `OnUnitInactiveSec=10min`. The timer
was reloaded and restarted without restarting the capture service. Verification
showed the previous capture completed at 01:23:30 UTC and the next trigger was
01:33:30 UTC, exactly ten minutes later. This is a completion-to-start gap,
not a ten-minute start-to-start schedule. The setting persists across reboot.

## Why the queue grew

At the initial audit, 88 jobs were pending (13 analysis, 75 tracking) and 19
were leased (13 analysis, 6 tracking). Over the preceding four hours:

| Queue stage | Jobs created | Jobs completed |
| --- | ---: | ---: |
| GLRT analysis | 30 | 37 |
| Tracking, including position publication | 37 | 19 |

GLRT was reducing its backlog while handing completed scans to tracking faster
than tracking finished them. Tracking gained 18 jobs over that window. In the
combined queue, 30 new scan jobs versus 19 final tracking completions implies
11 additional outstanding jobs, since GLRT-to-tracking transitions transfer work.
In the last hour, 12 tracking jobs arrived and 8 completed. There were no duplicate
outstanding jobs for the same session/stage and no expired active leases.
Zero outstanding jobs had `attempt_count > 1`; this counter does not include
normal yields, so it is not proof that work never resumed.

The recent four-hour tracking throughput was 4.75 scans/hour. Four new scans/hour
should eventually permit drainage if that throughput holds. Existing GLRT work
will continue feeding tracking first; the tracking-only queue can temporarily
grow even as total outstanding work falls. This is not a reliable clearance ETA:
the rate mix, position workload, server contention, and outstanding GLRT scans
all matter. Keep the existing 13 analysis / 6 tracking limits.

## Optimization

The Hough line finder now selects only the highest accumulator entries with
partitioning, then sorts that small selection. It preserves stable tie ordering,
including boundary ties, and leaves the candidate search, thresholds, scientific
configuration and output contracts unchanged. Nonpositive/full-size selections
retain the previous slicing behavior.

The earlier bounded prototype saved 3.45% preparation CPU on one 2.5 MS/s
capture and 35.02% on one 10 MS/s capture. Those are preparation-stage results,
not full tracking speedups. See
`reports/2026_10_06_server_runtime_profile/README.md` and its raw evidence.

Validation includes component-owned ordering and complete Hough-output tests,
existing line-finder and persistent-trajectory tests, and saved-session replay
through `tools/benchmark_hough_sources.py`. The latter compares the complete
input-evidence digest using the old and new source modules and alternates order
across sessions. It reads saved products and does not publish analysis or capture RF.

Deployment uses a pinned copy of only `leo/analysis/cfo_lines.py` in the existing
production overlay. New job subprocesses import the optimized version; running
jobs keep their already-loaded version and finish normally. Keep a backup of
the previous file for atomic rollback. Do not replace the entire overlay, which
also contains the lease, memory and GLRT improvements.

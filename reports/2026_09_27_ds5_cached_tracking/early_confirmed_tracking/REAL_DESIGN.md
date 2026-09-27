# Development comparison after controls

The frozen control run completed all 66 executions without a required-policy
failure. Evaluate all 64 original recorded development visits, chronological
within their independent sessions, using independently stateful original and
early-confirmed controllers and the current full application call. Rotate the
three methods within visits. Use fresh application pair inventory with the
existing 2us/8kHz association criteria. Report receiver identity retention,
extras, visit loss, additional confirmations, complete-call CPU and wall time.

This version has no rescue. Compare against the original native baseline as
well as the application; do not interpret removal of unmatched results alone
as a successful 10x replacement. The research target remains >=97% reference
receiver retention per rate, zero lost associated visits and >=10x paired CPU
savings, with no additional unmatched receiver outcomes versus native baseline.
These are development results, not final validation. No original holdout read.

Freeze this runner, sources and membership before IQ loading. One campaign,
CPU0, numerical threads=1, 300-second bound; include conversion/controller/
confirmation in timing and exclude file IO, initialization and serialization.
Partial runs and all quality failures are preserved as results.

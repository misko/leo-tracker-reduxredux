# Single detector-control invocation

Started after the exact amended-scope preflight passed on 2026-10-26 UTC.
Unified execution session: `80038`. Internal cap 120 s, per-slot cap 20 s,
outer timeout 125 s plus 5 s termination grace. This is the sole invocation
of the frozen sixteen paired-window slots; failures are retained.

The deployed code/environment, continuous synthetic law, known sampled-template
boundary mismatch and all scenarios are bound by `protocol.json`. This run
does not read recorded IQ, collect RF, construct tracks or estimate position.

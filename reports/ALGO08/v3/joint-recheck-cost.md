# Timing budget for targeted full-length receiver checks

The two saved joint-repair experiments improved fitted error by 836 m on DS30-0049 and 83 m on DS30-0086. The repairs used the signed outputs of the installed full-length detector. If a short detector could name exactly those same opportunities for a full revisit, the extra positive full callbacks would cost an estimated **0.63–0.75 s** and **3.68–4.37 s**, respectively. Both recordings already exceeded half the installed wall time before those checks. [0049 saved position result](ds30-0049-joint-recovery.md) · [0086 saved position result](ds30-0086-joint-recovery.md)

| Recording | Target full calls / original short calls | Measured ALGO08v3 / candidate wall (s) | Additional native seconds with perfect advance scheduling | Additional native seconds after short result | Other saving needed to halve this recording's wall time after a short-first recheck |
|---|---:|---:|---:|---:|---:|
| DS30-0049 | 176 / 1,622 | 18.68 / 13.60 | 0.48–0.60 | 0.63–0.75 | 4.89–5.01 s |
| DS30-0086 | 1,028 / 8,372 | 91.27 / 58.84 | 2.79–3.47 | 3.68–4.37 | 16.88–17.58 s |

Each restored or replaced lane has a positive installed outcome. The short-first column prices a full positive callback on each target. Advance scheduling also credits the short empty or positive callback that the receiver would skip. The range spans four observed, serial donor mean costs. Each endpoint uses one donor for both apertures. The number of original calls and both end-to-end clocks come from the same field recording as the saved packet. [Field timings and donor clocks](first30-empty-call-roof.md) · [Inputs, field clocks and per-donor costs](measurements/joint-recheck-cost.json)

This sensitivity holds the rest of each field run fixed. It grants a free, perfectly selective scheduler, assumes the full callback reproduces the desired factor and continuation choice, and charges no extra I/O. Changes in graph construction, position fitting, real selection errors and contention could change the actual cost. The saved solves measured position effects separately. A per-recording half-time budget helps size the work, while the release gates use the sum and paired median across the full panel. [Reproducible calculation](joint_recheck_cost.py)

# Causal multi-track bank experiment

This directory contains one frozen server replay of a three-track bank per
`(session, receiver, channel, edge, rate)` key. It uses only observations made
by the strategy. The independent packed V4 result is a comparator and never
creates, selects, repairs, merges, or evicts a track.

Each visit scores every live supported prediction against fresh IQ with the
full-aperture V3 known-state GLRT. Compatible positive checks are all recorded
and updated; the current largest margin selects the strategy output, with lower
track ID as the fixed tie break. If no check is accepted, a natural-stride V4
blind call confirms the top three ranked windows. Its top observation remains
the strategy output, while every distinct positive fitted observation may
populate the bank.

The bank has a two-second per-track TTL and a global discovery counter per key.
One selected cache-hit visit increments that counter regardless of which track
wins. Every completed blind discovery resets it, including a negative blind
result. At the 32-observation interval, cached scoring is suppressed for that
visit, but the bank retains internal predictions so a fitted blind observation
can refresh the corresponding track and preserve its learned derivative.

`design.json` freezes the strategy, selection, identity, capacity, fallback,
timing, and rejection gates. `bank.py` contains no detector reference. The
standalone runner uses one warmup and three timed repetitions, alternates
reference/strategy call order, charges all cache checks and actual fallbacks,
and verifies caller IQ and native receipts. It evaluates the 256 receiver-visits
in `new_data/cases.json` once. The 24 supported constructed receiver-controls
are isolated cold acquisitions and therefore test acquisition decisions only,
not state continuity.

Run the component tests with:

```sh
.venv/bin/python -m pytest -q \
  reports/2026_09_27_ds5_cached_tracking/multitrack/test_bank.py \
  reports/2026_09_27_ds5_cached_tracking/multitrack/test_runner.py
```

The frozen replay is rejected. See `REPORT.md` and the row-level
`results.json` receipt.


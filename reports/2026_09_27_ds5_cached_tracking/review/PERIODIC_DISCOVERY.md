# Periodic-discovery counter review

Reviewed source: `tracking.py` SHA-256
`0597aaf35e53e3f7652d599fc870afa9358440c542509fd0ed4b4fdb462a990f`.
The v4 and final v6 development receipts pin this same source hash.

## Finding

The suspected counter reset is not present in the frozen source. `update()`
initializes a new count to zero, but for every positive, nondiscovery update
with prior state it assigns
`previous.accepted_since_discovery + 1`. That assignment is outside the
`if compatible` learning block. Learning compatibility controls the CFO and
timing derivative estimates; it does not control the periodic-discovery count.

This distinction matters because `accepts()` permits up to 8 kHz of physical
CFO innovation, while derivative learning permits only
`5000 Hz/s * dt + 2000 Hz`. A measurement can therefore be accepted as fresh
evidence without being suitable for derivative learning.

## Public-API reproduction

A minimal sequence used a 2.5 MS/s key, 120 ms visit spacing, and a positive
`predicted_verified` observation 3 kHz above each prediction. Each observation
passed `Tracker.accepts()` because 3 kHz is below 8 kHz. It failed the learning
bound, approximately 2.6 kHz at 120 ms, so the learned CFO rate stayed zero.
After the discovery seed, the observed state was:

```text
visit 0: discovery, count=0
visit 1: predicted, innovation=3000 Hz, cfo_rate=0, count=1
visit 2: predicted, innovation=3000 Hz, cfo_rate=0, count=2
visit 30: predicted, innovation=3000 Hz, cfo_rate=0, count=30
visit 31: predicted, innovation=3000 Hz, cfo_rate=0, count=31
visit 32 begin: periodic_discovery
```

This matches the protocol's 32-visit cycle: one discovery followed by 31
accepted cached visits. An accepted cached check outside the learning bound
does not extend discovery coverage indefinitely.

## Receipt impact and minimum safeguard

`dev_strided_v6_final.json` contains 16 cache hits in total, no
`periodic_discovery` row, and a maximum observed per-key cached streak of three.
Thus the receipt did not exercise the threshold, although its pinned source has
the correct counting behavior. The development result cannot serve as empirical
qualification of the 32-visit policy.

Do not change the frozen implementation or receipts. Add a regression test in
the next source version that runs the sequence above and requires visit 32 to
return `periodic_discovery`. If a divergent branch has placed the counter
assignment inside `if compatible`, the minimum repair is to dedent only that
nondiscovery counter assignment to the current location. Keep derivative
learning unchanged and retain the historical receipt under its pinned hash.


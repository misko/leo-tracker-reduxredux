# Shared physical timing and longer-block qualification

This experiment retains the seed-20260923 split and the same two validation groups
of ten and twelve scans, plus each group's first scan. No retrospective-test
recording is used. Historical exposure and conditional candidate/seed limitations
still apply. No geographic error tunes the hypothesis.

## Shared start time

Export saved timing authorities through the public read-only tracking-source port
for the 22 validation recordings. At each geographic trial, profile one timing
offset per scan on 17 equally spaced points between the saved earliest and latest
start times relative to its estimated midpoint. At that shared timing, choose each
track's satellite identity and constant frequency offset from training frequency
rows. Retain a zero-timing control and capped800/robust150 shared-timing arms.

Use the same duration weights, own-window published seeds, prior intersection and
optimization budget as preceding experiments. The scan-level timing selection
must optimize the same loss as the location objective. Preserve every attempted
window, including boundary or convergence failures. Seal inference before
reserved-frequency and reference-coordinate scoring. Report all chosen scan
offsets, timing-boundary rates, and finite-grid resolution limitations.

The host capture bracket does not establish absolute UTC or TLE error. This tests
a physically motivated restricted model; it does not declare broader shifts
impossible or assume that timing correction alone will deliver 300 m.

## Older-block qualification

The metadata inventory found 72 and 80 captures in the Sep21 00Z and 08Z eight-hour
blocks. Inspect only deterministic first/middle/last recordings from each block
initially. Use public ports to check actual track evidence, timing authority,
receiver/sample-rate regime and causal-catalogue availability. Do not use position
errors or known receiver coordinates to select recordings. Record missing support
and investigate existing contract-compatible sources before proposing adaptation.
This sample cannot certify every recording or an entire block's continuity.

## Receiver identity mapping

Independently inspect one training recording to see whether the track observation
IDs can be joined unambiguously to RX/channel identity through existing public
contracts. Cached evidence alone lacks these fields. A valid derived join may
enable later per-RX drift analysis without changing published contracts; ambiguous
or missing mappings must remain explicit.

No production deployment, RF campaign, or prospective-test access is included.

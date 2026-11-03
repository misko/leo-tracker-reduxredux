# Scan-0 pilot gain survives nominal temporal-support alignment

Using the eight-frame pilot's nominal measurement center lowers the long-arm
reference error to **745.342m**, compared with765.072m for original IID and
751.262m when retaining the original GLRT timestamp. The total improvement is
**19.730m (2.58%)**. Nominal support alignment therefore does not explain away
the earlier gain on this scan. This remains one exposed-scan mechanism test
against the existing unsurveyed roof reference, not a validated DS11 policy.

| Input | Original GLRT timestamps | Nominal pilot timestamps | Change from original IID |
|---|---:|---:|---:|
|Original IID|765.072m|—|—|
|Short pilot, symbols2–65|773.810m|767.233m|+2.160m|
|Long pilot, symbols22–221|751.262m|745.342m|-19.730m|

Both arms use all111 previously measured training corrections. Each target row
evaluates every retained candidate at its own shifted time using the unchanged
causal state bank and interpolation. All other rows and all65 target
localization-held timestamps and values remain unchanged. The timing search
has a5ms guard at each bank boundary; all compared endpoints are interior.
There are no new IQ reads, orbit downloads, satellite selections, or position
priors. The conditional MAP assignments remain unchanged for all62 tracks.

All eight starts qualify and exit0, taking6.52–11.33seconds each. Maximum
within-arm EN disagreement is0.00038m for short and0.00128m for long. Five
component tests pass. Verification rehashes the frozen sources and results,
checks training-score endpoint selection, reproduces reference errors, and
matches each corrected row's prediction to the existing scalar interpolation
exactly for every candidate. Held-row predictions match exactly as well.

The long arm's original-model held score changes by+0.039913nats; its
changed-training held score is0.054425nats below the original control. Thus
the small geographic gain still lacks improvement in that predictive metric.
Held measurements retain their original GLRT estimator; this is not a uniform
waveform re-estimation. Nominal geometric centers do not establish actual
amplitude-weighted frequency-estimator timing.

Plan SHA256:
`5197ccf4d53ec33f0df3ef65a43a83f378b9e5175ce2d5c524da49839d1be95d`.
The [protocol](PROTOCOL.md), [outcome](outcome.json), and
[verification](verification.json) preserve the comparison. Selections were
saved before geographic scoring. Every fit has a terminal receipt in `runs/`.
An initial unprivileged batch launcher failed to execute the release Python
before starting any fit; the privileged launcher then ran the eight attempts
once. The first post-fit verification incorrectly compared a result enriched
with geographic error against its pre-geography selection; removing only that
additional field fixes the verifier. No fit was repeated or altered.

Next: replicate on the already-selected scan16/NORAD67103 using both pilot
arms with nominal support-aware predictions. Its124 training observations and
81 untouched target held observations were selected before new waveform
outcomes. No model promotion or broader accuracy claim follows this result.

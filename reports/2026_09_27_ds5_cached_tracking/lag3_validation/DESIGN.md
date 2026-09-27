# Independent proposal-coordinate challenge

Before candidate evaluation, fix membership to all 20 physical cases (40
receivers) in `lag3_controls/cases.json`, SHA-256
`5bc58aab84ce75d3704d08a294333010745caec382da5f059b04c9e5a5473188`.
Use the completed, frozen lag-3 kernel without changing its proposal count,
support threshold, timing refinement or carrier estimation. Execute only after
the worker's real-data cost benchmark releases its timing slot.

Compare every returned proposal with each injected pilot using physical 750 Hz
circular timing within 2 microseconds and CFO within 8 kHz. Report raw
coordinate matches separately from supported matches, and report coverage of
each trajectory in mixtures. A match to either injected pilot does not imply
both were found. Noise and tone controls have no pilot coordinate target;
their supported proposals are counted without calling them false detections.

This is 40 proposal-only calls, not detector integration. It is useful even
when the cost gate fails, to distinguish scientific feasibility from runtime
feasibility. No GLRT thresholds or detection decisions are inferred. No
performance timings are reported, and no real-data/holdout labels enter this
audit. The generated controls omit unknown data/QAM and frequency-selective
channels, so good results would not establish real-signal robustness.

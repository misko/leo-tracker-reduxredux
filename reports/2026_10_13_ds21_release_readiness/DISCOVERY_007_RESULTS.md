# DS21-007 training-only discovery

The first missing development initialization completed in one bounded slice:
**100 points in 335.007 seconds**. This is discovery readiness, not a final
position estimate or a localization-accuracy result. No reference position,
held observation projection or locked recording was used.

| View | Fixed-position fits | Stationary | Retained nonstationary |
| --- | ---: | ---: | ---: |
| CH1–8 | 100 | 96 | 4 |
| CH1–4 | 100 | 100 | 0 |
| CH5–8 | 100 | 99 | 1 |

All calls used fitted `c`. These fits retain the original discovery core's
5-second/200-iteration per-view limit, 100-point hierarchical budget and all-view
search priority. They are not the four-call DS21-039 model controls. Failed
points were not retried or replaced. The terminal contains three separated
training-selected states; six downstream proposals and final model estimates
have not yet been produced.

The adapter reproduced the original census: 2,987 all-band windows, 1,807 low-band
windows and 1,180 high-band windows, with original evidence hashes, training
partition, coordinate and calibration frames. The causal catalogue contained
11,129 Starlink entries; the original bank builder retained 970 and completed in
4.432 seconds. Discovery uses this broad bank, not DS21-039's later 43-satellite
association bank.

The source/input protocol was sealed before training preparation. The final
protocol bound exact preparation and causal catalogue bytes before propagation
or fitting. It archived 310 scientific source files. Internal slice limit was
480 seconds, external TERM 495 seconds and KILL 500 seconds. The slice completed
normally. A subsequent cached-terminal validation reproduced the hierarchy and
selection from saved scalar scores, validated all points and sources, and
performed no new numerical preparation, propagation or fit.

The adapter's 10 owned tests passed in both the worker and integration
worktrees; integration runtime was 23.75 seconds. Tests cover training-only
preparation, original-core routing, checkpoint reuse, timing and source tampering,
causal catalogue checks, orphan rejection and the whole-slice deadline.

Immutable receipt bindings:

- Protocol: `sha256:315d01ecbf5113cfe5abe4a219139abd33669f5a25efcf745fa0e9dc11284e44`.
- Terminal: `sha256:3b4660b8a3480f01015c46acdb80e53b456b1369d52bc3f23698584ee6758fee`.
- Catalogue: `sha256:7e988daf0b396ea3cb196f6d8a009a7a37f9d76cabd8da4cfeabd85d8cc521c4`.
- Implementation integration commit: `b1aed4ddd`.
- Local evidence namespace: `local/discovery-007-v1` within this report directory.

Among the 34 fast development recordings, the historical five retain their
discovery/proposal caches. DS21-007 now additionally has a completed discovery;
28 still lack discovery and 29 still lack downstream proposal caches. No new
full-DS21 performance claim follows from this initialization milestone.

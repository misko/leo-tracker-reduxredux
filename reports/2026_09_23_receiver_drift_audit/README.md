# Training-only receiver-drift diagnostic

This audit tests whether one linear frequency slope per scan explains residual
structure after candidate identity, integer timing, and constant CFO are selected per
track. It uses the first 12 cached scans in the frozen random-group **training** order.
Each scan is evaluated at its own published Sacramento-or-Reno selected coordinate;
the lower published residual chooses the seed. No geographic truth or validation/test
recording is read.

| Diagnostic | Result |
|---|---:|
| Scans / selected tracks / reserved rows | 12 / 442 / 4,841 |
| Shared scan slope, median | 0.62 Hz/s |
| Shared scan slope, range | -9.18 to +5.35 Hz/s |
| Shared scan slope RMS | 4.14 Hz/s |
| Unchanged inner-reserved RMS | 197.19 Hz |
| Shared-slope inner-reserved RMS | 194.66 Hz |
| Scans with lower inner-reserved RMS | 9 / 12 |
| Tracks selecting tau at ±5 s | 8.14% |
| Correlation: timing-boundary flag vs absolute slope disagreement | 0.445 |

The frozen shared slope lowers aggregate complementary-row RMS by 2.54 Hz. The result
is directionally useful but modest relative to the roughly 197 Hz residual scale.
Individual-track slope IQRs range from 7.6 to 20.4 Hz/s, substantially wider than the
between-scan shared-slope distribution. This weak coherence does not support treating
the fitted value as a calibrated oscillator drift.

The timing-boundary correlation is a warning: tracks whose selected integer tau hits
±5 seconds tend to disagree more strongly with their scan's common slope. A shared
drift term can absorb some timing, identity, orbit, or track-curvature error. A next
model should keep a null arm, report tau-boundary rates, constrain slope from training
data, and compare whole-scan predictive score rather than interpreting slope
physically.

The cached track contract contains no receiver, channel, device, or RX identifier,
so this original audit used one slope per scan. A subsequent
[exact public-contract reconstruction](../2026_09_23_receiver_identity_mapping/README.md)
successfully joined all 840 cached observations in one training scan to receiver
identities. Per-receiver modeling is therefore possible when that reconstruction
passes for every included observation; it does not require undocumented storage
details. The numerical results above remain the original scan-level audit.

`receiver_drift.json` contains scan-level slopes, track-slope scatter, seed coordinates,
reserved scores, timing-boundary fractions, and source/cache digests. Reproduce with:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python tools/research/audit_position_receiver_drift.py \
  --manifest reports/2026_09_23_position_random_group_split/manifest.json \
  --replication-root reports/2026_09_23_day_position_validation/replication \
  --joint-tool tools/research/sixteen_joint_compare.py \
  --output <fresh-output-directory>
```

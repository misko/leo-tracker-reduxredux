# Partition-dependent identity changes at a frozen blind position

This is a diagnostic of four high-confidence identity changes between the
chronological and five-block association runs. It is not satellite-identity
truth or an independent forecast evaluation. The five-block run used these
same observations to select candidates, and its Sacramento-set location was
also inferred from the same blind dataset.

The diagnostic freezes the selected five-block location at latitude
37.83079045 degrees and longitude -122.42539562 degrees, propagates both the
chronological and five-block candidate with the causal TLE available at each
observation time, and evaluates both candidates against the same observed
trajectory. For each candidate and partition policy, the only fitted value is
one constant frequency offset, estimated from that policy's training samples.
No reference position, phase model, beam calibration, orbit correction, or
cross-track shared offset is used.

The Doppler predictions and every residual/RMS metric use the analysis model's
canonical 11.2 GHz carrier. The native channel RFs in the table identify the RF
paths; they are not the frequency scale used for the reported residuals.

## Numerical result

All RMS values are in hertz. `train/test` means the partition policy's training
and held-out masks. Episode hashes are shortened only for display.

| Episode | RF path | Old -> new NORAD | Chronological old | Chronological new | Five-block old | Five-block new |
|---|---:|---:|---:|---:|---:|---:|
| `fa1b8229` | RX1 / ch3 / 11209.687498 MHz | 55461 -> 60943 | 268 / 1980 | 325 / 280 | 1185 / 862 | 321 / 294 |
| `ff355e16` | RX0 / ch3 / 11209.687498 MHz | 69833 -> 68812 | 252 / 1020 | 339 / 553 | 644 / 409 | 448 / 245 |
| `203bcb0f` | RX0 / ch3 / 11440.312496 MHz | 69332 -> 64943 | 312 / 1610 | 444 / 477 | 954 / 749 | 524 / 336 |
| `216ceffe` | RX0 / ch2 / 11190.312500 MHz | 69332 -> 64943 | 191 / 1496 | 417 / 423 | 917 / 599 | 463 / 401 |

The old candidate has the lower chronological training RMS in all four tracks,
which explains the early-segment preference. The new candidate has the lower
chronological held-out RMS in all four: 280--553 Hz versus 1020--1980 Hz. Under
the five-block masks, the new candidate also has the lower training and
held-out RMS in every track. The residual plots show the old candidate
diverging through the later arc while the new candidate supports more of the
long-track shape.

This pattern is evidence that the reassociation is driven by trajectory shape
rather than solely by a fitted constant offset. It does not validate the new
NORAD IDs. Candidate selection was performed using the same full trajectories,
so the chronological held-out figures are descriptive post-selection results.
The new candidates also retain visible curved residual structure and roughly
245--553 Hz held-out RMS, which limits the strength of any identity claim.

## Repeated e201 trajectory shape

The two e201 tracks both change from NORAD 69332 to 64943 and have strongly
correlated normalized, demeaned gross observed shapes on their common time
interval: correlation 0.999993 and normalized RMS difference 0.003724 over 128
interpolated points without extrapolation. That result is driven mainly by the
common Doppler curve; it is not a test of residual independence or
paired-receiver corroboration. Both tracks are from RX0, on different channels
(ch3 and ch2), at different RFs, and share no source-group ID. The interpolation
is a descriptive comparison only; common acquisition or processing effects can
also produce repeated shape.

## Provenance and limitations

[`results.json`](results.json) records the full observation arrays, masks,
candidate curves, fitted offsets, exact metrics, input paths, and SHA-256
digests. [`manifest.json`](manifest.json) binds the numerical JSON, CSV, and PNG
artifacts. The main bound inputs are:

- association comparison: `sha256:1ed446c35b4606d449d037951bf9638e7437a26b85a330883327866e4fbeb8eb`
- five-block refinement result: `sha256:f61eb25a70198e22dabdafd7647db8b03194bc3f1652cecab7ea05d31472f246`
- refinement seal: `sha256:37916eba09936ba6af9a0ef63c828c8210ac3d3a4f50db4754540eb18daeaffa`
- evidence inventory: `sha256:2c9a022000d7769180c46f0273f2b81ae3f102fa3f3d526bc8e317e6ef246ce2`

The chronological and five-block masks answer different sampling questions;
their RMS values should not be interpreted as exchangeable estimates of one
generalization error. The fixed location, the four selected conflicts, and the
replacement candidates are post-selected. Nominal TLE propagation errors,
receiver frequency behavior, and unmodelled carrier dynamics remain possible
causes of the residual structure.

The reproduction paths below are the frozen temporary inputs recorded by the
five-block report and acquisition/refinement seals. A relocated archive must
restore those inputs, including their recorded hashes, or pass equivalent
paths with the same sealed content.

Reproduce the saved artifacts from the repository root with:

```bash
.venv/bin/python reports/diagnose_partition_identity_changes.py \
  --comparison /tmp/joint-partition-association-comparison.json \
  --refinement /tmp/recent-five-block-regional-v1/sacramento-set-refinement-v2/result.json \
  --evidence /tmp/five-block-input-check-v1/recent-regional-evidence-v1 \
  --output /tmp/partition-identity-diagnostic-reproduction
```

The figure is [`partition-identity-residuals.png`](partition-identity-residuals.png),
and the compact metric export is [`metrics.csv`](metrics.csv).

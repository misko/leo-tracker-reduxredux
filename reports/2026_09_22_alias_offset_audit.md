# Frozen blind-offset alias audit

This read-only diagnostic uses the frozen blind residual export. It selects the
91 episode candidates whose frozen conditional weight is at least 0.9, undoes
the 11.2 GHz normalization, and compares each training-fitted constant offset
on the circle with period `1 / 4.4 us = 227272.727 Hz`. It does not refit
position, identity, alias, or receiver calibration and does not use truth.

The first four scans used the **lower pilot edge**, with actual RF centers near
10.7097, 10.9597, 11.2097, and 11.4597 GHz. The last scan used the **upper pilot
edge**, near 10.9403, 11.1903, 11.4403, and 11.6903 GHz. These labels come from
the source capture lanes; they do not identify LNB high- or low-side mixing.

Across the four lower-edge scans, the circular means are -40.24 kHz for RX0 and
-30.61 kHz for RX1. Circular RMS spreads are 11.16 and 20.14 kHz, while median
absolute deviations are 3.39 and 3.73 kHz; large outliers drive the difference.
The upper-edge scan instead gives +30.20 kHz for RX0 and +30.77 kHz for RX1,
with circular RMS 10.25 and 3.09 kHz.

At the narrower scan/receiver/channel level, 26 groups contain at least two
tracks and 15 have circular RMS below 5 kHz. Several groups are tight, but e3bc
RX1 channel 3 has 57.85 kHz RMS. Leave-one-track residuals in the JSON show that
one shared circular mean is not uniformly predictive.

The structure is plausible as a receiver-plus-pilot-edge nuisance. The earlier
non-alias-marginalized shared-constant failure does not by itself falsify that
narrower hypothesis. It is not established as calibration or identity evidence.
Each offset is the training mean residual for a candidate and location selected
from the same CFO trajectories. Free per-track constants made the regional
likelihood invariant to these means, so clustering was not rewarded directly,
but catalogue, orbit, location, and track-branch errors can still induce
post-selection concentration. No NORAD repeats across scans at the reported
weight thresholds, preventing a direct cross-scan satellite control.

Existing alias-aware line utilities and persistent-hop reconstruction already
handle the 227.27 kHz circle within tracks. A future controlled ablation may use
a robust hierarchical offset indexed by receiver and declared pilot edge, while
retaining an outlier mixture and integer-alias marginalization. It must select
the nuisance only from training tracks, score separate evaluation tracks, and
must not pool lower and upper edges until an RF sign convention is independently
established. Free per-track offsets remain the truthful descriptive baseline;
their profiled scores are not predictive probabilities or a formal predictive
ceiling.

## Predeclared scope for a future ablation

The 91-track cohort above is selected by a posterior-weight outcome and is
suitable only for describing the observed clustering. A predictive ablation
must instead start with all 165 RF tracks, freeze whole-track folds using RF-only
identifiers before reading identity weights, and retain tracks whose blind
candidate mixture is weak or null-dominated. For each fold, it may fit a robust
circular intercept from the other tracks with the same receiver and declared
pilot edge, summing over the full causal catalogue, explicit null, integer pilot
aliases, and a broad outlier component. The intercept and every hyperparameter
must then be frozen before scoring the held-out tracks. No continuous constant
or candidate identity may be learned from a held-out track. Channels and tracks
must receive balanced effective weight, and groups without adequate training
support must abstain.

This would remain a **conditional diagnostic**, not independent position or
association validation. The frozen blind position was fitted using the shapes
of all 165 tracks, including tracks later assigned to an offset-evaluation fold.
The first ablation therefore must not refit or select position, choose a branch,
or claim out-of-sample geolocation accuracy. It tests only whether offsets from
other RF tracks improve conditional frequency prediction at that already-frozen
position. The latent parameter should be called an acquisition-convention
circular intercept; the analysis supplies no authority to interpret it as a
physical LO or LNB calibration.

## Reproduction and source bindings

From the repository root, reproduce the machine-readable audit with:

```bash
sudo -u leo .venv/bin/python tools/research/audit_blind_alias_offsets.py \
  --residuals /tmp/blind-residuals-v1 \
  --rf-shards /tmp/recent-position-rf-shards-v1 \
  --output /tmp/recent-alias-offset-reproduction.json
```

The JSON binds the frozen residual manifest digest and the SHA-256 digest of
each of the five RF source shards under `provenance.rf_shard_digests`. Pilot-edge,
receiver, channel, and actual-RF values are verified against those source lanes;
they are not inferred from channel number or session order.

Artifacts:

- `2026_09_22_alias_offset_audit/audit.json`
- `tools/research/audit_blind_alias_offsets.py`
- `tests/tools/test_audit_blind_alias_offsets.py`

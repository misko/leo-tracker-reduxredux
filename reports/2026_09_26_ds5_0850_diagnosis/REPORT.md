# DS5 08:50 failure: association and shared timing interact

## Finding

The poor known-location result is substantially driven by an **inconsistent association/timing procedure**: choose each track's satellite at zero timing, freeze those IDs, then impose one learned timing correction on all tracks assigned to each satellite. At this scan, several frozen groups contain tracks requiring incompatible corrections.

A bounded training-only joint assignment/shared-timing diagnostic reverses the probabilistic ranking and substantially reduces the known-site residuals. This identifies a weakness in the earlier evaluation; it does **not** establish decoded satellite identities or a physically validated orbit correction.

Session: `scan-fw-dc1153010e57ac76`, 2026-09-26 08:50 UTC, 39 tracks. Persisted Sacramento and Reno locations are respectively 128.93 km and 123.53 km from the reference. Their coordinates remain fixed throughout this investigation.

## What drives the failure

Eight tracks were selected retrospectively for diagnosis: all reference tracks frozen to satellite 64068 or 53139. Together they account for 129 of 421 evaluation observations. Under the original shared-age model, these groups contribute an average predictive NLL of **12.892** per observation, versus **6.364** for the other 31 tracks.

| Frozen reference group | Track structure | Independent timing fits | Shared fit consequence |
|---|---|---|---|
| 64068 | Two receiver pairs on channels 2 and 3, around 40–76 seconds into scan | Approximately -16.8, -9.8, +3.3 and +3.7 s | Shared timing about -6.3 s; evaluation RMS 1.3–3.3 kHz |
| 53139 | Two receiver pairs on channels 1 and 3, around 205–235 seconds | Channel 1 about -16.8 s; channel 3 about -1.5 s | Shared fit about -1.5 s fits channel 3 but leaves channel 1 at 1.5–2.6 kHz |

This is evidence that these assignments are not mutually compatible under the assumed one-correction-per-satellite model. It is not independent proof that any particular satellite ID is wrong: unmodeled frequency/geometry effects could also produce inconsistent equivalent timing.

## Diagnostic experiment

For the eight selected tracks only:

1. At **each of the three locations independently**, screen the full 11,117-candidate inventory on a coarse timing grid from -30 to +30 seconds in 3-second steps, ranking by training-only centered RMS.
2. Keep the six best candidates per track/site plus its original frozen candidate. No site's shortlist is passed to another site.
3. Refit these candidates at 0.1-second resolution over +/-60 seconds, using the existing normalized Student-t(4), 100 Hz residual scale and frozen historical age priors. CFO remains training-profiled. No scan-clock or linear-drift parameter is added.
4. Compare two ways of choosing IDs: independently per track by integrated training score, and an approximate **joint training-only coordinate search** that scores each candidate change with the satellite's other assigned tracks included.
5. The other 31 tracks keep their candidate IDs. Their observations still constrain any shared satellite timing; they cannot be ignored when assigning a new track to their satellite.

The joint method uses 8 starts at the reference site and 7 at each other site. All starts converged within the 20-pass limit. It optimizes a training objective only; it does not read evaluation scores when selecting IDs. This is local assignment optimization, not exhaustive joint identity marginalization or a new geographic search.

## Results

Predictive NLL per evaluation observation; **lower is better**:

| Assignment method | Known location | Wrong Sacramento | Wrong Reno |
|---|---:|---:|---:|
| Original zero-timing frozen IDs | 8.3642 | **7.2272** | 7.3278 |
| Independently reselect IDs, then pool timing | 7.7370 | **7.5185** | 7.8341 |
| **Select IDs with shared timing in the training objective** | **6.5881** | 7.1570 | 7.2535 |

Uncapped posterior-expected weighted RMS:

| Assignment method | Known location (Hz) | Wrong Sacramento (Hz) | Wrong Reno (Hz) |
|---|---:|---:|---:|
| Original frozen IDs | 1,271.4 | 390.2 | 400.7 |
| Independent reassignment followed by sharing | 4,172.3 | 635.1 | 689.4 |
| Joint training reassignment | 394.5 | 385.6 | 396.9 |

The known location wins the joint model's probabilistic score, but **RMS alone still slightly favors wrong Sacramento**. No localization error has been recomputed or improved by a geographic search.

### Why independent reassignment can make things worse

At the reference site, independent reassignment chooses 65843 with about +42.8 seconds for two channel-1 tracks. Other, unchanged tracks were already assigned to 65843. Pooling those tracks afterward forces the large correction onto them, driving their evaluation RMS to approximately **16.5 kHz and 13.4 kHz**. The resulting overall 4.17 kHz RMS is not a timing-boundary issue: the assignment decision ignored its effect on existing tracks.

The joint objective instead retains 53139 for the channel-1 pair and moves the conflicting channel-3 pair to another candidate. It makes six assignment changes among the eight target tracks at the reference site, versus two at each wrong site.

## Reference-site assignment changes under joint training

These are best-fitting model hypotheses, **not confirmed satellite identities**.

| Track prefix | Channel / receiver | Frozen → joint ID | Joint timing MAP (s) | Original → joint evaluation RMS (Hz) |
|---|---|---|---:|---:|
| 0b8ea715 | 3 / 0 | 64068 → 50844 | +41.9 | 3,252 → 385 |
| 98dbb677 | 3 / 1 | 64068 → 50844 | +41.9 | 2,849 → 487 |
| 4ab49bf1 | 2 / 1 | 64068 → 65844 | +26.9 | 1,307 → 62 |
| ad1be37a | 2 / 0 | 64068 → 65844 | +26.9 | 1,837 → 195 |
| 4d0b0dcd | 1 / 1 | 53139 → 53139 | -16.8 | 1,498 → 224 |
| c950fd59 | 1 / 0 | 53139 → 53139 | -16.8 | 2,591 → 321 |
| 2b1e41fc | 3 / 0 | 53139 → 62314 | -13.5 | 82 → 87 |
| eb90e4ae | 3 / 1 | 53139 → 62314 | -13.5 | 139 → 164 |

The paired-receiver/channel structure is consistent with splitting mixed model-association groups. Two already well-fitting tracks become modestly worse; this is not a claim that every residual improves.

## Track construction and recording timing checks

- Reconstructed the TLE-blind trajectory and verified its configuration digest against the prepared input.
- Checked every target observation against its original candidate binding, including canonical RF normalization and alias index.
- Three receiver pairs have no alias-index changes in either track. The late channel-3 receiver-1 track has four changes, but its concurrent difference from receiver 0 remains on a much smaller frequency scale than a full alias cycle.
- Matched same-channel receiver observations within 2 ms. Pair counts are 45, 26, 31 and 35; standard deviations of inter-receiver frequency differences are approximately **71, 74, 55 and 133 Hz**. Constant receiver offsets of about 2 kHz are handled separately by the per-track CFO nuisance. This supports coherent paired measurements; it does not rule out subtler tracking or RF-model errors.
- First-sample host-relative bracket width is **0.3633 s**, and realtime/monotonic offset spread is **3.419 microseconds**. Neither explains an observed tens-of-seconds clock step. Absolute UTC bias is not independently certified by this metadata.

There is no affirmative evidence here that a gross alias slip or observed clock discontinuity explains the failure.

## Important remaining warning: the corrections are still large

The joint reference solution uses +41.9 seconds for a 50844 element set about 22.04 hours old, and -16.8 seconds for 53139 elements about 22.04 hours old. Under the prototype's zero-centered t4 prior for that age bin (scale 0.642 s), the untruncated two-sided tail probabilities beyond those magnitudes are about **3.3e-7** and **1.3e-5**. These are prior tail areas, not probabilities that the assignments are wrong.

This demonstrates that likelihood gains can overwhelm the age prior and select rare timing hypotheses. The +26.9-second candidate 65844 uses the broad pooled prior because its elements are only 6.79 hours old and that age range lacks sufficient calibration data. Thus the apparent probabilistic improvement is **not** evidence of physically correct orbit corrections. Uncertain association, mismodeled Doppler, frequency drift and observation dependence remain viable explanations.

## Recommendation

The next solver prototype should make association decisions **inside** the shared satellite-timing model, preserving candidate uncertainty rather than selecting each track independently and pooling afterward. Every candidate reassignment must account for all tracks already assigned to that satellite.

Before evaluating this across DS5 or deploying it:

- improve the physical/calibration treatment of large equivalent timing corrections and very young TLEs;
- account for temporal/receiver dependence rather than treating all observation factors as fully independent;
- validate on fresh independent groups, with no reference-derived corrections or shared geographic proposals;
- retain explicit association/model-mismatch warnings when fits require extreme corrections.

This investigation diagnoses an evaluation/model-selection weakness. It does not justify merely increasing timing limits, discarding the eight tracks, or declaring the newly selected IDs correct.

## Verification and artifacts

The frozen baseline reproduces the DS5 values to better than 1e-8 nats/observation at all three sites. **23 tests pass**, including three new checks for training-only shortlist selection, correct shared-latent group scoring, and joint assignment independence from evaluation values.

- `investigate.py`: read-only orchestration and source-binding audit.
- `joint_selection.py`: pure numerical, training-only bounded coordinate search.
- `coarse_candidates.json`: independent site-specific candidate shortlists.
- `results.json`: trace provenance, candidate fits, all three model comparisons, group contributions and multi-start receipts; includes evidence/snapshot/code hashes.
- `test_investigate.py`: diagnostic tests.

Reproduce with the installed API Python environment and single-threaded BLAS:

```sh
python reports/2026_09_26_ds5_0850_diagnosis/investigate.py
```

`--reuse-coarse` reuses the same local coarse shortlist for repeated fine diagnostics. No production behavior, DS5 inputs, previous result artifacts or RF recordings were changed.

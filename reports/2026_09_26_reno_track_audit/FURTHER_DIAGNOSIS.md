# Further diagnosis: 12:50 UTC scan

Scope: `scan-fw-d86e8f23c0624bac`, five selected tracks, fixed known receiver location. No geographic search, cross-prior candidate sharing, production changes, or new RF collection. Satellite IDs remain model-selected hypotheses, not decoded truth.

## Main result

The longest tracks have a reproducible satellite-conditioned timing mismatch, not simply a coarse-grid minimum. This is consistent with orbit-model error plus residual systematic frequency error. It does not establish the physical cause or prove the satellite identity.

Timing and constant frequency offsets were selected on the original training observations; RMS below uses the original evaluation observations. Candidate comparison was restricted to the previously retained three reference candidates per track, not a new full-catalogue search. Fine timing grid: -15 to +15 seconds in 0.1-second steps.

| Track prefix | Span (s) | Preferred satellite | Timing (s) | Evaluation RMS (Hz) | RMS after diagnostic linear residual fit (Hz) |
|---|---:|---:|---:|---:|---:|
| ad00e08d | 51.72 | 63850 | -7.3 | 213.67 | 115.81 |
| d4446f2d | 50.59 | 63850 | -7.7 | 106.80 | 26.56 |
| f34dd5e9 | 37.44 | 63850 | -8.4 | 97.39 | 71.90 |
| 46b5f08c | 40.25 | 61518 | +0.2 | 35.66 | 26.97 |
| 7f350671 | 32.70 | 63643 | -10.6 | 853.46 | 595.42 |

The linear residual fit is an additional training-only diagnostic at the already selected timing, not a joint timing/drift optimizer or a production recommendation. Positive tau means evaluating the orbital prediction at t + tau.

## Timing versus orbital elements

- Satellite 63850's elements were 50.46 hours old despite the snapshot being only 1.79 hours old. Satellite 61518's elements were 5.20 hours old.
- On 32 seeded random whole-one-second-bin splits, conditional fitted timing ranges were -8.0 to -7.2 s for ad00e08d, -7.9 to -7.4 s for d4446f2d, -8.6 to -8.2 s for f34dd5e9, and +0.1 to +0.3 s for 46b5f08c. These are sensitivity checks, not confidence intervals or independent validation.
- The host-relative first-sample bracket was 0.364 seconds wide, and realtime/monotonic offset spread during capture was 1.377 microseconds. This does not explain a measured 7-second host clock step. It also does not certify absolute UTC accuracy or exclude constant host-clock bias.
- The clean control occurs later in the scan, so satellite-specific and time-dependent effects are not fully separated.

Changing only to earlier causal orbital elements, with fixed geometry and identities and a -30 to +30 s grid at 0.1 s resolution, gives:

| Satellite / track | Element age (h), current → earlier | Timing (s), current → earlier | Evaluation RMS (Hz), current → earlier |
|---|---:|---:|---:|
| 63850 / ad00e08d | 50.46 → 64.58 | -7.3 → -6.1 | 213.67 → 178.99 |
| 63850 / d4446f2d | 50.46 → 64.58 | -7.7 → -6.4 | 106.80 → 77.81 |
| 61518 / 46b5f08c | 5.20 → 49.05 | +0.2 → -1.3 | 35.66 → 53.05 |

This directly demonstrates sensitivity of fitted timing to the element set. Older elements happen to improve the two long-track fits; element age alone is not a reliable accuracy ranking. None of these changes removes their several-second discrepancy. The sampled causal snapshots did not offer fresher 63850 elements.

## Track construction and association

- Every analyzed observation was checked against its reconstructed trajectory and original candidate binding, including RF normalization and alias index.
- The two longest tracks are separate receivers observing the same RF channel at overlapping times, not duplicate source records. There are 77 observation pairs within 2 ms and no shared source-group IDs. Their fine-fit residual correlation is approximately 0.81, supporting a shared systematic component without identifying whether it is orbital, transmitter, or receiver-related.
- Alias indices change, but dealiased adjacent residual jumps are hundreds of Hz, not the approximately 222 kHz whole-alias spacing in that channel. There is no obvious full-cycle alias slip in those two tracks; subtler tracking errors remain possible.
- The longest two tracks still favor satellite 63850 among the tested candidates. The third overlapping track, f34dd5e9, is ambiguous: 63850 gives training/evaluation RMS 121.58/97.39 Hz versus 128.14/105.74 Hz for 53072. Its best identity changes when timing flexibility is expanded.
- Track 7f350671 remains poorly explained. Allowing a large residual slope can make another candidate appear much better: candidate 53076 at the -15 s timing boundary goes from about 1348 Hz evaluation RMS to 140 Hz after a +150.76 Hz/s residual fit. That flexibility is not evidence of a correct association.

## Implications and next bounded checks

The cap reversal remains understandable: the known location explains many tracks well but has a heavier residual tail. These selected-track diagnostics show model mismatch can contribute to that tail; they do not yet explain all nine above-cap reference tracks or establish a better localization objective.

1. Test satellite-shared corrections across simultaneous receiver/channel tracks, and receiver-shared frequency trends across different satellites. This can separate common effects better than unrestricted per-track drift. Confirm identifiability where observations overlap.
2. Cross-fit those corrections between independent receiver/channel or pass groups: learn on one group and predict another. Do not fit each bad track into agreement independently.
3. Inspect all nine zero-timing above-cap reference tracks and matched Reno counterparts before concluding that these five tracks represent the full tail.
4. Validate any resulting correction model on other scans with independently generated Sacramento and Reno candidates. Keep reference coordinates evaluation-only, report capped and uncapped loss, and do not tune nuisance freedom solely to favor the known location.

Artifacts: `diagnose_tracks.py`, `deep_diagnosis.json`, `check_element_age.py`. The orbital-element sensitivity table records the completed six-fit experiment; the script reproduces its full JSON output.

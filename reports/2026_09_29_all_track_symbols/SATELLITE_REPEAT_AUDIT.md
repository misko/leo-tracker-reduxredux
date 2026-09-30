# Satellite-repeat evidence in the current qualified census

The current census contains one conditionally labeled same-satellite pair across
different sessions. Its early-header profile is somewhat more similar than the
matched comparison median, but not exceptional. This does not establish an
identity-bearing signature or decode a satellite-ID field.

## Scope of the labels

There are 146 pilot-qualified tracks with retained conditional NORAD labels,
all from DS7. The census imported exact-track DS7 annotations only when their
status was `likely_conditional`; it did not import DS8/DS9 candidate associations.
These labels are external geometric hypotheses, not decoded RF identities.
Consequently this audit describes the currently bound label set, not the number
of real satellite revisits in all DS7/DS8/DS9 recordings.

Many repeated labels occur only within one session. Exactly one pair spans
different sessions; none also shares a sample rate. Receiver tracks, recording
sessions, encounters, and satellite passes are not interchangeable counts.

## The available cross-session pair

Both tracks are conditionally associated with **STARLINK-31540 / NORAD 59542**:

| Track | Rate | Receiver | Edge / channel | Minimum held-pilot coherence |
|---|---:|---:|---|---:|
| DS7-F006-T0038 | 5 MS/s | 0 | Upper / 2 | 0.519 |
| DS7-F048-T0039 | 10 MS/s | 0 | Upper / 2 | 0.546 |

Track start times differ by 17,849.825 seconds, approximately 4 h 57 min 30 s.
This is a difference between track starts, not a precise selected-excerpt time
or a verified orbital revisit interval. Both recorded RF centers are 11.19 GHz.

Use the existing frozen `upper_early_profiles` features: four common data
carriers (486, 487, 496, 497), six OFDM symbols (2–7), with unit phasors averaged
over the two evaluation frames. Concatenate real and imaginary coordinates,
center that real vector, and normalize. Its dot product is the feature-profile
Pearson correlation; it is not decoded-message or independent-bit agreement.

The pair's correlation is **0.22295**. Comparison pairs must have different
conditional IDs and sessions, the same upper edge and channel 2, and the same
5/10 MS/s rate combination:

| Comparison | Pairs | Median | 5th–95th percentile | Fraction below repeat pair |
|---|---:|---:|---:|---:|
| Rate/edge/channel matched | 89 | 0.109 | −0.088 to 0.342 | 77.5% |
| Also both receiver 0 | 25 | 0.114 | −0.052 to 0.332 | 80.0% |

Pairs share tracks; these ranks are descriptive and are not independent-trial
p-values. Candidate labels can be wrong, and SNR, elapsed time, calibration,
and other conditions are not all matched. The repeated pair lies inside the
ordinary comparison range. Two evaluation frames per track are also a weak
estimate of a visit's persistent profile.

## Implication

The currently imported annotations do not provide a replicated, matched
cross-session identity experiment. The comparison is worth retaining, but it
cannot identify unknown bits or justify grouping message observations by a
verified satellite. Any extension to DS8/DS9 must first bind their candidate
associations to exact census tracks and preserve uncertainty, rather than
joining by approximate names or time alone.

`satellite_repeat_audit.py` records the source and feature hashes, full pair
metadata, and all comparison scores in ignored `local/satellite-repeat-audit/`.
It reuses the existing tested feature geometry; no decoder or clustering
implementation was changed. Ruff checks and the existing 31 research tests pass.
No satellite label, data file, remote branch, or deployed service was modified.

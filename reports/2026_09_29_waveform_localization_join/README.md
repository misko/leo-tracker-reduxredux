# Waveform quality is not a verified satellite-association label

**Do not use the existing symbol-census quality flags as localization priors or
as a track filter.** Exact joining finds no smaller conditional satellite residuals
in the pilot-qualified group, and the current model assigns near-unit signal
responsibility to both waveform-quality groups. In addition, the excerpt-selection
policy uses whole-track pilot margins, including localization-held visits.

This audit joins all 4,328 bank-eligible tracks in the nine eight-scan evaluation
panels. Of these, 3,383 have decoded excerpts: 196 pass both pilot checks and 3,187
do not. The remaining 945 belong to 2.5-MS/s recordings excluded by the original
symbol census; missing waveform evidence is not counted as failed quality.

| Dataset | Pilot-qualified excerpts | Insufficient-pilot excerpts | No census excerpt | Qualified-group held residual median | Insufficient-group held residual median |
|---|---:|---:|---:|---:|---:|
| DS7 | 69 | 946 | 419 | 122.36 Hz (67 cases) | 87.21 Hz (885 cases) |
| DS8 | 46 | 1,104 | 284 | 106.49 Hz (46 cases) | 99.26 Hz (1,009 cases) |
| DS9 | 81 | 1,137 | 242 | 262.30 Hz (73 cases) | 110.84 Hz (1,033 cases) |
| Total | 196 | 3,187 | 945 | 141.29 Hz (186 cases) | 98.79 Hz (2,927 cases) |

Residuals are the earlier conditional strong-candidate cases, centered on each
track's training mean, then summarized by median absolute held residual. Their
denominators differ from track counts because not every track qualified for that
residual export. These are **different populations**, not matched interventions:
track duration, geometry, rate, channel and excerpt selection can confound the
comparison. It does not mean clean waveforms cause worse accuracy or weak ones
are better measurements. It does show that this existing quality label is not
an established predictor of smaller candidate-model residuals.

## Association confidence does not supply the missing identity evidence

Median conditional signal responsibility is effectively one in all three groups.
The stronger joint criterion, signal responsibility times largest conditional
candidate weight at least 0.5, passes 186/196 qualified tracks and 2,966/3,187
insufficient-pilot tracks. Thus model confidence is not independent confirmation
of waveform recovery or satellite identity. The likelihood was already documented
as a conditional retained-candidate model, not calibrated identity confidence.

The [symbol census](../2026_09_29_all_track_symbols/README.md) recovers known pilot
and repeating sequence structure, but no verified satellite identifier or
FEC-validated identity payload. Its four-frame excerpt is only a small part of
each track. Failing its two evaluation-frame coherence checks does not establish
that the full track is noise, a different transmitter, or permanently undecodable.
Passing them confirms waveform structure under that assay, not the selected orbit.

## Selection/holdout audit

| Waveform status | Excerpt visit in localization training | Excerpt visit in localization held |
|---|---:|---:|
| Pilot-qualified | 124 | 72 |
| Insufficient pilots | 1,969 | 1,218 |
| Total with excerpts | 2,093 | 1,290 |

The decoder selects the strongest acquisition-pilot margin over **all** visits
in each track. Consequently, even the 2,093 selected training visits were chosen
using a ranking that consulted held visits. Their within-excerpt waveform
calibration/evaluation split is a different partition from localization's
whole-visit split. Neither should be confused with the other.

This is not a flaw in the exploratory census, which made no held-localization
claim. It is a reason not to reuse its selected quality flags as if they were
leakage-free training covariates. No current localization result was refitted
using these flags in this audit.

## Verification and reproduction

The [protocol](PROTOCOL.md) preceded execution. Join exact session/track IDs,
require the observation digest and capture manifest to agree with the census,
and recompute each decoder receipt's binding from its capture specification,
frame count and decoder source hash. Selected visits must belong to the exact
track with one consistent whole-visit partition. Recompute qualification from
the original evaluation frames and >0.5 pilot-coherence threshold. All joined
rows pass; no unexpected missing-track or decoder-binding failure occurs.

`results.json` binds all input exports, posterior/residual files, decoder receipts,
census and scripts. It retains all 4,328 rows, selected visit/partition, coherence
values, conditional responsibility and residual availability. Two tests pass for
whole-visit joining and explicit rejection of missing/inconsistent visits.
Ruff lint/format pass. No raw IQ read, RF collection, production edit, filtering,
model fitting or geographic scoring occurred.

```bash
.venv/bin/python -m unittest discover -s reports/2026_09_29_waveform_localization_join -p 'test_*.py'
.venv/bin/python reports/2026_09_29_waveform_localization_join/audit.py
```

## Next decision

An independent waveform-conditioned model needs training-only excerpt selection
and a matched frequency-estimator comparison on those same excerpts before any
association prior is learned. Use raw pilot evidence to test measurement quality;
do not substitute a repeating sequence state for satellite identity. The current
audit identifies a concrete validation requirement and rejects an unsupported
shortcut, but supplies no new geographic improvement. Reliable short-window
sub-km accuracy remains unresolved.

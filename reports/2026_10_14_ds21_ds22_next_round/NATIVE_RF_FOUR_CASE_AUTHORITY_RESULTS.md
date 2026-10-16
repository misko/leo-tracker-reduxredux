# Four-case physical RF authority and Doppler scaling audit

The software RF mapping is internally consistent on DS21-081 and DS22-109,
115 and131. **The external LNB frequency/state remains unverified.** This
metadata-only extension found no new units, sign or IF-to-RF arithmetic defect
that explains their position failures. It does not establish that the assumed
physical RF labels are correct.

All27,031 saved acquisition windows and28,496 public tracking probes were checked
against hash-bound recording metadata. Requested IF, applied IF and the saved
retune receipt's frequency agree exactly. Every public tracking RF equals that
applied IF plus the saved LNB reference. All56 segments have
`calibration_id="uncalibrated"`, `rf_mapping_authority="hypothesis"` and
`physical_lnb_control_changed=false`. The radio serial is the same in all cases.

| Case | Recording edge | Recorded windows | Public tracking probes | Segments |
|---|---|---:|---:|---:|
| DS21-081 | upper | 6,763 | 6,738 | 14 |
| DS22-109 | upper | 6,758 | 7,308 | 14 |
| DS22-115 | lower | 6,752 | 7,046 | 14 |
| DS22-131 | lower | 6,758 | 7,404 | 14 |

Probe counts include both receivers after the public fast-score/export rules;
they are not training-window counts. No retained observation, model, candidate
bank, reference or fit was changed.

## Exact recorded mapping

The table gives MHz. Each cell lists applied IF → labelled RF. The two receivers
use the same recorded channel mapping; their physical external LO paths are not
independently attested by these fields.

| CH | Saved LO reference | Upper-edge IF → RF (081/109) | Lower-edge IF → RF (115/131) |
|---|---:|---:|---:|
| 1 | 9,750 | 1,190.3125 → 10,940.3125 | 959.6875 → 10,709.6875 |
| 2 | 9,750 | 1,440.3125 → 11,190.3125 | 1,209.6875 → 10,959.6875 |
| 3 | 9,750 | 1,690.3125 → 11,440.3125 | 1,459.6875 → 11,209.6875 |
| 4 | 9,750 | 1,940.3125 → 11,690.3125 | 1,709.6875 → 11,459.6875 |
| 5 | 10,600 | 1,340.3125 → 11,940.3125 | 1,109.6875 → 11,709.6875 |
| 6 | 10,600 | 1,590.3125 → 12,190.3125 | 1,359.6875 → 11,959.6875 |
| 7 | 10,600 | 1,840.3125 → 12,440.3125 | 1,609.6875 → 12,209.6875 |
| 8 | 10,600 | 2,090.3125 → 12,690.3125 | 1,859.6875 → 12,459.6875 |

## Source path, units and sign

1. `research_fast_scan_tracking.py` checks the saved applied IF and exports
   `actual_rf_hz = actual_if_hz + lnb_reference_hz`. It explicitly preserves the
   hypothesis authority in provenance.
2. `scanner_trajectory.py` copies that RF into each public projected candidate.
   `regional_position_inputs.py` copies the selected candidate RF into
   `PositionObservations.rf_hz`; native branch construction copies the same row
   RF to each available branch while retaining its native observation time.
3. `hard60_score.predict_orbits` passes this RF array unchanged into the compiled
   `_regional_orbits.cpp` predictor. Both the compiled path and the Python oracle
   use `prediction_hz = -rf_hz / 299792.458 * radial_velocity_km_s`.
   The dimensionless line-of-sight direction points from observer to satellite;
   positive radial recession gives negative CFO. Hz divided by km/s multiplied
   by km/s returns Hz. The model uses the labelled **RF**, not the lower Pluto IF,
   and does not use one common carrier frequency for CH1–8.
4. The acquisition scorer reports acquired CFO plus residual CFO. Its correction
   rotates by `exp(-2j*pi*cfo_hz*time)`, consistent with a positive measured
   frequency offset. This is a source-level convention check, not an independent
   physical spectral-orientation calibration.
5. The fitted RF-calibration coefficient uses a different expression:
   `c * (rf_hz - rf_center_hz) / 1e9`. Here the reference is the observation
   contract's mean of unique RF labels, and `c` has units Hz/GHz. That centering
   is for additive calibration; orbital Doppler still uses absolute RF.

Consequently, the same radial velocity produces different Doppler shifts across
the bands. For example CH5 versus CH1 has about9.14% larger magnitude in the
upper-edge plan and9.34% larger magnitude in the lower-edge plan. This existing
frequency scaling is already present; adding it again would double-count it.

## What remains unknown—and what was already tested

The saved IF readback is an internal radio tuning authority. It does not measure
the external LNB's actual LO frequency, make/model, per-receiver topology,
band/polarization state, lock history or spectral orientation. The declaration
that the recorder did not change physical LNB controls does not prove that an
external device was fixed, switched elsewhere, or shared between receivers.
No current metadata resolves those alternatives. Large fitted calibration terms
alone cannot identify the physical LO or justify a replacement RF mapping.

This source-level question was already examined for A035/A053 in
[the RF provenance audit](model_a_rf_mapping_prior_art_results.md). The subsequent
[finite LO qualification](model_a_finite_rf_qualification_results.md) preserved
native additive calibration functions while testing recorded split LO versus
both9.75GHz and both10.6GHz. Both alternatives worsened the conditional likelihood
at those fixed states/banks. Those results neither verify the hardware nor rule
out a different association search under another physically supported mapping.
This audit extends the metadata binding to the four requested recordings; it
does not repeat those numerical experiments or transfer their outcomes to these
cases.

The useful next RF evidence is a recording-bound external LO/topology/state or
independent frequency authority. This report proposes no position-selected
mapping, additional RF collection or new localization fit.

## Reproducibility and limits

Source5de9c70a2 (initial a62ebcdee), two component tests passed. The successful
standard-library metadata audit completed in4.162seconds with500 hash bindings,
0objective calls,0orbit calls,0optimizer calls and0IQ bytes read. It checked
1,016,758,939 metadata bytes, largely the existing whole-dataset authority
manifests, under an explicit1.5GB/600file/120second internal bound and independent
135second TERM/140second KILL bound. Input bytes were rehashed before completion.

The first attempt stopped at its400MB metadata cap before case checks because
the sealed DS21/DS22 manifests alone are392.9MB/495.2MB. The failed receipt remains
at `native-rf-authority-four-cases-v1/failure.json`; v2 increased only the metadata
cap and retained only requested members in memory. It did not repeat any fit.

Authoritative result:
`/srv/bulk/leo-research-ds21-ds22/2026_10_14/native-rf-authority-four-cases-v2/report.json`,
SHA256 `8ec79f45ede233d8da02e2a6b4cc27eb4a64c8335bc9f998e351955031521358`.
[The accompanying exact JSON](NATIVE_RF_FOUR_CASE_AUTHORITY_RESULTS.json) contains
all recording IDs, mapped lanes, acquisition counts and source/metadata hashes.
No reference positions, held results, PostgreSQL writes, QNAP mutations or radio
controls were accessed.

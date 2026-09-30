# Exact DS8 candidate-label binding

All 72 saved conditional DS8 Doppler labels bind to exact census tracks.
Only two of those tracks pass the current four-frame excerpt's pilot gate.
Adding them increases qualified labeled tracks from 146 to 148, without adding
a cross-session same-label pair. The prior satellite-repeat conclusion therefore
does not improve merely by importing the existing DS8 labels.

## Binding checks

Read the four current `*-tracks.json` files under the earlier DS7/DS8
correspondence report's ignored local directory. Archived files ending in
`tracks.invalid-config.json` do not match this pattern and are not imported.
Accept only source status `conditional_doppler_label`, retaining the original
label, fit diagnostics, alternative candidates, and limitation text.

Primary matching requires exact `(session_id, track_id)` equality. Verify DS8
membership and equal receiver, channel, and edge. Track start/end times must
also agree within 1,000 ns, allowing rounding differences from the older
floating-point timestamp calculation. The tolerance does not permit approximate
track matching. Duplicate source identities are rejected by an assertion.

All 72 eligible labels pass these checks; none is rejected or approximately
joined. Hashes of every source and the census are stored. This validates the
association-to-recording binding, not the correctness of the inferred satellite.

| Decode status of bound DS8 tracks | Count |
|---|---:|
| Qualified in the existing four-frame excerpt | 2 |
| Insufficient pilots in that excerpt | 70 |

The two qualified additions are:

| Census track | Conditional candidate |
|---|---|
| DS8-F027-T0002 | STARLINK-34271 |
| DS8-F039-T0005 | STARLINK-30711 |

Neither adds a cross-session repeat among the qualified DS7/DS8 labeled tracks.
The only such pair remains the DS7 STARLINK-31540 candidate described in
[SATELLITE_REPEAT_AUDIT.md](SATELLITE_REPEAT_AUDIT.md). Additionally, none of the
72 bound DS8 labels matches a qualified DS7 candidate label across sessions in
this census snapshot.

## What the quality count means

The census uses one selected excerpt and four recovered frames per receiver
track, including only two calibration frames. A failed pilot gate does not
establish that every visit on that track, or a longer calibration, fails.
The present binding artifact keeps all 72 labels so later recovery attempts can
use the exact provenance without relaxing the quality gate or promoting weaker
geometric candidates to confirmed IDs.

No compatible saved DS9 track-label annotation file was identified in the report
search. The inspected DS9 baseline-transfer response is a location estimate,
not a track-to-satellite label set. It was not converted into identity labels.
This does not preclude a new DS9 geometric association analysis.

## Artifacts and validation

`bind_ds8_labels.py` writes a supplementary binding artifact under ignored
`local/bound-ds8-labels/`; it preserves the previous frozen census and report
outputs. The artifact carries all original uncertainty rather than changing
`conditional_doppler_label` to a decoded identity. Two synthetic tests verify
exact-ID requirements despite timestamp tolerance and rejection of receiver,
channel, and timing mismatches. All 33 research tests and Ruff checks pass.

No new bits or semantic fields were decoded. No RF collection, download, commit,
or deployment was performed, and numerical data remain excluded from Git.

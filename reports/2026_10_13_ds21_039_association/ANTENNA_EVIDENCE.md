# DS21-039 antenna evidence audit

**A capture-supported directional prior is unavailable.** The original DS21-039 records provide receiver indexes and tuner settings, but no attested RF boresight, world-frame mounting orientation, antenna response, field of view or directional uncertainty. Do not infer such a prior from detector occupancy, channel-edge labels or an unrelated nominal fixture.

This source/metadata-only audit selected recording `fast8-auto-20261012-102515-b9e46bba-1-lower`, raw identity `sha256:45fcd8a8be569d1a855f621c88ce0fc281803b98c21ddface0f07a2b83b5ca90`, through the frozen DS21 authority. It verified all **14 sealed segment snapshots and 106 explicitly supplied native index paths**, covering **6,762 original windows**, with no digest discrepancies. The native metadata scan took approximately 1.93 seconds. It inspected metadata schemas and recorded hardware labels only: no IQ payload, numerical orbit prediction, localization fit, reference-coordinate read or held scoring/selection.

| Evidence | Recorded finding | Directional interpretation |
|---|---|---|
| Radio | Serial `1040005e0b100007100010000bf33a5d4d`, provider `ppu-continuous-v5` | Identifies the SDR, not an antenna pointing or RF pattern |
| Native receiver labels | Index 0 → `RX1`; index 1 → `RX2` | Logical path labels; no verified feed/cable/antenna identity |
| Segment configuration | 40 dB declared gain, `calibration_id=uncalibrated` | No measured directional gain response |
| Targets | `band`, `polarization`, `profile_id` are null | No directional or polarization support |
| RF mapping | `hypothesis`; LNB references 9.75/10.60 GHz | Frequency mapping hypotheses, not receiver pointing |
| Geometry/pointing fields | None in segment radio/configuration, native acquisition metadata or decoded tuner receipts | No capture-bound pose, beamwidth, response table or uncertainty |

The `sample_code_geometry` tuner field concerns digital sample representation, not antenna geometry. The existing transfer audit independently documents unverified native gain readbacks and absent physical RF-path provenance; see [transfer-eligibility.md](../2026_10_13_ds21_model_b_shape/transfer-eligibility.md). `physical_lnb_control_changed=false` does not attest a constant physical antenna or LNB state across acquisitions.

Current Model C's native orbit kernel sets visibility solely from the receiver-to-satellite unit vector dotted with the modeled site's local up direction: **`visible = elevation >= 0`**. This is an above-horizon test, with no antenna beam, boresight, obstruction mask, polarization or calibrated response. The recording's lack of antenna support therefore cannot justify tightening that gate.

The repository can represent more geometry, but those capabilities are not DS21-039 evidence. `BeamPointingV1` contains azimuth, elevation, cone half-angle and horizon mask; sky screening applies them when explicitly supplied. The capture/receiver geometry contracts also support RF boresights and phase centers. Neither appears in this recording's persisted metadata or its `TrackingInput` contract.

The existing `gauss-r21-lt3d-001a-20260920-v1.json` fixture is bound to **another radio**, serial `10400056f695001322002d0010ad1719f2`. Both RF boresights and RF phase centers are null, and both receiver-to-slot assignments are provisional. Its nominal ±10° mechanical mount axes are expressed in fixture-local coordinates; there is no captured transform to a world/ENU frame or measured RF pattern. They cannot be substituted for this recording's receiver directions.

No directional test or new fit is proposed from these records. A future narrow test becomes admissible only with existing attested evidence that binds the recorded radio/receiver path and capture interval to RF boresight, world-frame orientation and a response or acceptance model with uncertainty. Validate that binding before calculating any association effect; retain non-directional support for uncertain paths rather than inventing a hard angular cutoff. No new RF collection is requested.

Provenance: DS21 authority SHA256 `b3316e1bad03b902d3c742ef65e5f83c083b832193aaf6566fdd2d89448c6b58`, seal binding SHA256 `92a5a4355e2d277af0cd53bbb82f5cbc1bf17da19d4c1b1a39f09b33794ddfcf`, tracking-input SHA256 `2631e731b3ef0b2ba13ee0ff2e6a689ec1a31c6fbb0f19047121eb214a03ac94`. Source inspection: `src/leo/analysis/_regional_orbits.cpp` SHA256 `19bc1c3d22441bac41e8abb438b11a4784dc6071a298d9a0cc0ea515f733bee8`; nominal fixture JSON SHA256 `758262ecc67044065e2e2facc46f2cc77997883eabf0f7f1a4c5fa761fba65f7`. The original authority supplies every segment snapshot digest and native index path/digest; no IQ storage path was followed.

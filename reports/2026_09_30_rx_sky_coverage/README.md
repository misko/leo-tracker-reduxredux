# DS9 / DS10 / DS11 receiver sky support and LNB roll

Both receivers have conditional signal support across overlapping upper-sky directions, including east and west. Their nominal mount axes are only 20° apart. These data products do **not** establish separate east/west fields of view, a calibrated beam boundary, or an LNB roll angle. No physical roll estimate is reported.

## Recorded installation versus assumed geometry

All **379 recordings** now have verified capture-bound pose evidence: 105 DS9, 187 DS10, 87 DS11. DS10/DS11 membership snapshots did not collect pose companions; this audit read the already-existing companions from the capture-pose store without modifying those snapshots. Every companion matches its session, source manifest digest, capture interval, authority digest and binding digest. All share authority `gauss-r20-roof-20260926-v1`.

The common roof position is **37.849056280893684°, −122.48575489722863°**. This is an operator-supplied position interpreted as WGS84, not a surveyed GPS accuracy claim. It is a common installation position, not two separately surveyed RF phase centers.

| Quantity | Recorded evidence / interpretation |
|---|---|
| Physical RX1 | West, azimuth 270°; provisionally software RX0 |
| Physical RX2 | East, azimuth 90°; provisionally software RX1 |
| Actual elevation | Null in both receiver records |
| Nominal mount | LT3D-001A, 10° outward tilt each, 80 mm mount separation |
| Axes if mount is level and feed axes follow CAD | RX0 az/el 270°/80°; RX1 90°/80° |
| Roll, antenna gain pattern, horizon obstruction mask | Not provided by the bound pose authority |
| Altitude and directed RF baseline | Unknown |

“West” and “east” describe the azimuth of a slight nominal tilt from vertical. They do not imply horizon-facing antennas. The assumed axes are 20° apart, with zenith 10° from each. Actual installation tilt, feed alignment and cable order remain uncertainties. Rotating a feed about its axis does not change that axis; it can change polarization response and any asymmetric beam pattern.

![Nominal angular geometry](nominal-geometry.png)

Contours are angular distance from the assumed axes, **not** beamwidths, gain contours or detection thresholds. For example, a 30° contour is a geometric reference and must not be called a half-power beam edge.

## Analysis of the existing recordings

The audit verifies every archived analysis evidence digest and raw/GLRT binding. It uses the archived candidate groups and their exact original TLE snapshot, recovered through the public `TleArchiveReader`. It propagates each retained group's candidate at nine times across each member track's observed support, then projects it at the roof position. These knots illustrate a candidate trajectory; they are not nine independent RF measurements. No new RF, raw-IQ decode, production job, identity fit or gain fit was run.

Two evidence tiers are kept separate:

1. **Held-out leader:** candidate remains the leader on held-out observations and the archived result does not recommend abstention.
2. **Control-supported:** additionally, the nominal held-out negative log score is strictly smaller than the radio-null score and both ±500-second wrong-time scores. This is a comparative diagnostic, not verified satellite identity or a significance test.

| Dataset | Recordings | Archived RX0 / RX1 tracks | Held-out candidate groups | Also pass all controls | Shared by both RXs among control-supported groups |
|---|---:|---:|---:|---:|---:|
| DS9 | 105 | 3,347 / 3,195 | 344 | 0 | 0 |
| DS10 | 187 | 5,977 / 5,860 | 620 | 67 | 62 |
| DS11 | 87 | 2,783 / 2,758 | 285 | 8 | 7 |

There are **23,920 archived receiver tracks**, of which **5,866** belong to retained held-out candidate groups. The strong subset contains 336 receiver tracks in 75 groups: 291 tracks in DS10 and 45 in DS11. Groups contain dependent receiver/channel tracks and may represent the same encounter; none of these counts is a count of independent verified passes.

![Conditional sky directions](conditional-sky.png)

Gray points use the broader held-out-only tier; colored points pass all three controls. Stars show the nominal mount axes. North is up and east is right; the center is zenith and the outer ring the horizon. Empty sky is **untested**, not demonstrated invisible.

The control-supported track-midpoint elevations are:

| Dataset / RX | 5th percentile | Median | 95th percentile |
|---|---:|---:|---:|
| DS10 RX0 | 50.4° | 74.8° | 86.5° |
| DS10 RX1 | 56.5° | 75.1° | 86.2° |
| DS11 RX0 | 60.6° | 77.3° | 87.8° |
| DS11 RX1 | 64.2° | 70.7° | 87.8° |

These are descriptive distributions of selected candidate tracks, **not confidence intervals or field-of-view limits**. Both receivers have east- and west-side support in both DS10 and DS11. The stronger evidence spans 51 DS10 recordings and seven DS11 recordings; 69/75 groups include both receivers. This supports a broad common upper-sky reception region conditional on those candidate assignments. It does not determine sensitivity throughout that region or exclude reception at lower elevations.

The archived pipeline attempted only four candidate groups per recording: **1,516 of 97,188 eligible groups (1.56%)**. That selection, satellite geometry, transmit beam scheduling, channel hopping, sensitivity thresholds and unknown source power all affect the displayed distribution. A histogram of detections therefore cannot be interpreted as a gain map. Non-selected or non-detected candidates are not known transmitting negative examples.

All 379 archived matches used **37.858988°, −122.478103°, altitude −29 m**, rather than the roof coordinates. Their ECEF displacement from the roof at assumed zero altitude is **1.292 km**. Reprojection changes displayed directions by at most **0.173°** across these knots; it does not repair the original Doppler identity inference. The labels and controls remain conditional on the old-site matching. Roof altitude is set to 0 m solely for plotting; changing it to 100 m changes these directions by at most **0.0082°**. That height interval is a sensitivity scenario, not an altitude measurement. Fitted candidate time offsets are not applied to the plotted physical observation times.

## Can roll be recovered?

**Not defensibly from this audit's evidence. This is not a claim that the stored IQ can never contain roll information.**

An ideal on-axis linear receive probe has polarization coupling `cos²(ψ − ρ)` for a linearly polarized incident wave with angle ψ and probe roll ρ. If ψ is unknown, a common rotation of ψ and ρ changes no measured power. Even with known ψ, power has a 180° ambiguity. For an ideal circular incident wave, coupling into that linear probe is 1/2 at every roll. Circular-to-linear reception's 3 dB mismatch is described in [Rohde & Schwarz, Antenna Basics, §2.5](https://scdn.rohde-schwarz.com/ur/pws/dl_downloads/premiumdownloads/premium_dl_brochures_and_datasheets/premium_dl_whitepaper/Antenna_Basics_8GE01_1e.pdf).

![Roll identifiability and candidate support](roll-identifiability.png)

The left plot is an analytical illustration, **not a measured DS9–11 roll likelihood**. It does not assume that every recorded signal is ideally circular or that the actual feeds are ideal linear probes. Real off-axis patterns, polarization ellipticity and multipath can introduce roll dependence. With a calibrated feed pattern, known or constrained source polarization and trusted directions, that dependence could be fitted. An apparent ellipse in these selected sky points alone would confound those effects with satellite/beam opportunity and analysis selection.

Complex phase does not automatically resolve this: at boresight a circular wave's projection onto a rotating linear probe changes phase, but an unknown per-chain complex phase can absorb that rotation. Unknown inter-LNB oscillator/cable phase, source polarization and unmeasured RF baseline need independent constraints before interpreting phase as physical roll. Known pilot symbols help estimate the channel; they do not by themselves specify incident polarization or an absolute RF phase reference.

Thus no numerical roll optimizer or uncertainty interval is warranted here: the archived support products are not calibrated polarimetric measurements, and even candidate directions do not robustly pass controls throughout all three datasets. Earlier independent receiver-geometry work also failed its signed-geometry prediction gate: [receiver persistence test](../2026_09_30_rx_persistence/README.md). That is supporting caution, not a new result from this audit.

A useful next calibration would establish the physical/software cable map, actual axis elevation and the installed feed model/polarization mode, then either bind a measured E/H-plane pattern to the feed's mechanical roll mark or use a source with a known polarization reference. Existing paired IQ could then test the resulting response model, fitting DS9/DS10 and freezing parameters before evaluating DS11, while treating source power, chain gain and candidate identity as nuisance quantities. Such a result would remain retrospective because these datasets have already been explored. No additional RF collection is authorized or started by this report.

## Reproduction and artifacts

- [analyze.py](analyze.py): read-only evidence audit, projection and plotting.
- [test_analyze.py](test_analyze.py): synthetic cardinal geometry, polarization symmetries, strict control gating and pose tamper/capture rejection.
- [evidence.json](evidence.json): all 379 pose receipts, source file hashes, authority snapshot, counts, candidate identities and 5,866 projected tracks.
- [sky-statistics.json](sky-statistics.json): receiver/dataset descriptive statistics.
- [conditional-sky.svg](conditional-sky.svg): vector sky figure.

From the repository root, collection can be reproduced with the repository interpreter under a 180-second process bound; archive and pose-store reads require an account with read access. Output redirection stays in this new report directory:

```sh
timeout 180 sudo -n .venv/bin/python reports/2026_09_30_rx_sky_coverage/analyze.py collect > reports/2026_09_30_rx_sky_coverage/evidence.json
.venv/bin/python reports/2026_09_30_rx_sky_coverage/analyze.py plot
.venv/bin/python -m pytest -q reports/2026_09_30_rx_sky_coverage/test_analyze.py
```

Only this new report directory is written. Existing manifests, golden fixtures, production settings, raw IQ and QNAP paths remain untouched.

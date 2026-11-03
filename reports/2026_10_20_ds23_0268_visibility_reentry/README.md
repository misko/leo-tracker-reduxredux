# DS23-0268: causal association beyond 70%, 53923 identity and sky geometry

**Result: 2,254/3,165 original GLRT points associated (71.216%) in both c arms.** All 2,111 earlier associations, all original curved/predictive position evidence and every original acceptance threshold are retained. No future TLE or supplied GPS enters fitting or trial selection. Frozen ALGO02 sources remain unchanged.

| Branch | Associated c0 / fitted-c | c0 fraction | Position error c0 / fitted-c km |
|---|---:|---:|---:|
| Receiver-step + reentry | 2111 / 2111 | 66.70% | 5.359 / 5.485 |
| Finer RX basis + CH7 | 2171 / 2171 | 68.59% | 5.216 / 5.273 |
| Re-nominate 63963 | 2209 / 2209 | 69.79% | 4.693 / 4.711 |
| Retain 66797 with stricter gate interior | 2254 / 2254 | 71.22% | 3.867 / 3.636 |

The 63963 and 66797 rows are alternative branches, not cumulative gains. Geographic error is evaluated only in this reporter; higher coverage or a lower RF score is not proof of accurate localization.

![All GLRT associations](final_associated_GLRT.png)

## What prevented recovery

The finer, prior-variance-normalized receiver basis first recovers CH7 T000 as causal 64333. Re-nominating CH7 T003 from 66355 to 63963 plus a frozen extension reaches 69.79%. Independently, recovering both 66797 curves (RX1 CH4 T006, 18 points; CH5 T005, 49 points) initially fails only the retained 53923 CH5 T003 slope check: 3.021 against a limit of 3 in c0. Its independently fitted pieces are not the problem.

The existing unconstrained RF optimizer minimizes a marginal bound; it does not require the residual gates during descent. We refine the same cold RF hypothesis under the original profile, conditional, alias, visibility, support and predictive gates. Five phase-refresh rounds and at most 40 SLSQP position iterations per round preserve the same physical priors, masks and aliases between c arms. The 67 curved points become jointly compatible; frozen extension adds RX1 CH7 T007, 16 points, to 66797.

An initial constrained solution sits close to a gate boundary. The selected follow-up instead requests a stricter 0.01 normalized gate slack inside every original limit. Both original gate replays pass; the source thresholds are unchanged. This is one-scan development, not an independent validation.

## Is 53923 wrong?

**That premise is not established.** Removing 53923 improving GPS error was an influence diagnostic, not an identity test. All ten associated 53923 graph tracks are single polynomial pieces: no multi-piece join is demonstrated here. A single piece can still contain an erroneous GLRT observation.

We re-screen all 1,402 causal catalogue candidates with one shared phase per disputed group over [-15,+15] s at 0.25 s spacing, holding the RF position and receiver calibration fixed. 53923 is the best nominal-orbit candidate for the combined six curved tracks and for the RX2 quartet. 67953 is slightly preferred for the short RX1 pair alone (c0 curve scores 93.9 versus 101.4; fitted-c 95.7 versus 99.1), a weak preference before phase priors and catalogue-search multiplicity. For all six curves the c0 scores are about 567.9 for 53923 and 1005.4 for 67953. These are proposal scores without candidate orbit modes, not posterior identity probabilities or the final joint-fit objective.

![Identity comparison](53923_identity_comparison.png)

All tested RX1→67953 substitutions, including adding the 62-point CH2 T005 curve and conservatively reducing changed-family powers, fail retained 63901 residual gates. Bounded constrained refinements also do not find accepted alternatives; that is not a proof that no feasible alternative exists. The independent catalogue screen still ranks 63901 first for its two curves.

Existing simultaneous winning-frame evidence contains one direct RX1 CH1/RX2 CH1 overlap for the 53923 group at 242.3544 s. Its frame-epoch difference is -5.68 ns, consistent with a common emitter rather than providing positive support for splitting the RXs. It is only one overlap; unknown group delay and epoch ambiguity prevent treating it as a unique satellite fingerprint. No new IQ was collected.

The 53923 fit still needs a comparatively large mean-motion-mode coefficient (roughly four times its engineering prior scale). This flags orbit/radio-model tension; that prior scale is not a calibrated statistical confidence interval. It does not by itself establish a wrong transmitter.

## Sky verification

The scan radio serial matches the station record for LT3D-004B. The record says RX1 west, RX2 east; a level base implies 70° elevation for each axis. Physical connector mapping is provisional, installed elevation and RF beam pattern are unmeasured. The station file location is deliberately excluded from RF inference; azimuth/elevation below uses the fitted RF location.

All 63 associated tracks and all 2,254 associated points are above the horizon. Maximum separation from the assumed receiver axis is 47.98°. There are zero points behind the nominal feed axes. A cone half-angle of 48° would cover all associations under this nominal pose; the actual antenna pattern has not been measured, so horizon visibility is verified and antenna visibility remains conditional. No invented beam-width gate is used to raise association coverage.

This conclusion also holds for the unadjusted causal TLEs: all associated points remain above the horizon, with maximum nominal-axis separation 48.23°. The sky check therefore does not depend on the fitted phase/orbit corrections to make a satellite visible.

An explicit report-only check at the supplied evaluation coordinate gives the same horizon conclusion: minimum elevation 34.12°, maximum nominal off-axis angle 47.74°. Sky direction changes by at most 0.51° relative to the RF estimate. This coordinate is not fed back to fitting, nomination or association selection. Only four associated points exceed a 45° nominal cone half-angle; a measured narrower antenna pattern would require revisiting those cases.

53923 moves southwest → near zenith → northeast during 225–300 s. Earlier detections on the west-facing RX1 and later detections on east-facing RX2 are plausible. The axes are only 40° apart, not opposite horizontal beams. Their near-zenith fields can overlap. 67953 also passes near zenith, so this geometry does not uniquely distinguish the identities.

![All associated tracks on the sky](sky_selected_71percent_c0.png)

| Satellite | Associated points RX1 / RX2 | Minimum elevation | Required nominal cone half-angle |
|---|---:|---:|---:|
| 53923 | 100 / 268 | 59.3° | 34.8° |
| 54873 | 0 / 42 | 61.0° | 14.3° |
| 59328 | 0 / 42 | 61.1° | 14.3° |
| 60415 | 80 / 97 | 59.3° | 36.1° |
| 61977 | 125 / 0 | 48.5° | 35.2° |
| 63901 | 91 / 0 | 45.2° | 48.0° |
| 63913 | 85 / 0 | 50.8° | 46.7° |
| 64333 | 60 / 0 | 51.1° | 27.9° |
| 64908 | 213 / 54 | 39.2° | 42.3° |
| 64923 | 306 / 0 | 42.1° | 28.3° |
| 64925 | 206 / 0 | 42.9° | 27.1° |
| 66797 | 83 / 0 | 34.1° | 36.2° |
| 66812 | 31 / 0 | 41.0° | 29.0° |
| 67935 | 99 / 23 | 37.7° | 37.8° |
| 68343 | 159 / 0 | 43.3° | 37.1° |
| 69445 | 36 / 54 | 45.7° | 42.5° |

## Limits and reproduction

This reaches the requested association target on this scan. It does not resolve all 911 remaining points, certify every satellite identity, establish measured antenna visibility, or demonstrate sub-kilometer localization. Strict-gate constrained fits require cohort testing before promotion.

Sources: `tools/debug_ds23_0268_visibility_reentry.py` stages `trials`, `constrained`, `interior`, `coverage`, `identity`; `tools/audit_ds23_0268_sky_visibility.py`; this report builder. Use `PYTHONPATH=src:tools`, single BLAS threads and the repository venv. Constrained stages also need the existing SciPy installation at `/tmp/algo03-feasible-deps`. Following TLE diagnostics from the previous study are not inputs to these trials.

[Selected result and retention checks](selected_result.json) · [All trial metrics](comparison.csv) · [Sky table](sky_visibility.csv) · [Sky provenance and per-point angles](sky_visibility.json) · [Whole-catalogue identity screen](identity_catalogue_screen.json) · [Protocol](protocol.json) · [Constrained refinement protocol](constrained_protocol.json) · [Interior protocol](interior_protocol.json)

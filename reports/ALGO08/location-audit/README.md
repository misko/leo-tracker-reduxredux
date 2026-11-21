# ALGO08 location audit before the regional release

This audit describes release `0efaf3b88`. The subsequent regional release made both centers explicit and corrected the location binding in the figures. [Regional release and blind validation](../regional-release/README.md)

**The deployed release knows roughly where the receiver is before it reads any Doppler evidence.** It searches a fixed Bay Area square and screens satellites at a second fixed Bay Area coordinate. The numerical fits do use the signal. The center of the square alone would miss the Gauss reference by 8.19 km, while the production fit on the audited recording missed by 0.707 km. This release supports a conditional local fix. Its DS30 results do not establish relocation performance.

Audited on Gauss on November 21, 2026. The active watcher selected `algo08` and launched release `0efaf3b88e9c155c2847a6fa21c354aabf788cb6`. The controls ran in separate processes against the installed code and read-only recording evidence. [Measurements](results.json) · [Replay harness](replay.py)

## Where geography enters

| Stage | Finding | Consequence at a new site |
|---|---|---|
| Acquisition and two-scan cancellation | The recorded targets contain channel, edge and tuning settings. The receiver admits dual-antenna 10 MS/s windows using sample counts, clocks and retune quality. It searches around the recorded RF, LNB and IF settings, subtracts the first detected pilot, and verifies carriers against the original samples. | I found no station coordinate or predicted satellite Doppler in this detection path. Signal strength, hardware compatibility, tuning accuracy and the frequency search range can still affect recall. |
| Pilot assets, continuation and tracks | I regenerated both installed 533,652-byte edge assets exactly from the 10 MHz pilot frame, rolled control frame, 81 filter taps and 30 MHz synthesis frame. Continuation reads earlier measurements on the same antenna and channel. The pinned tracking file contains numerical thresholds and budgets. Noise is estimated from this recording's track residuals. | Neither pilot contains a recorded roof signal. The slope, gap, margin and track-selection rules were qualified on a limited corpus. Measured transfer of raw detector recall needs a field test. |
| Orbit selection | The release supplies **37.5° N, 122.0° W** to the sky builder. Causal Starlink elements are screened by peak elevation of at least −12° at that point, sampled every five seconds. It is also the coordinate origin for part of the geometry. The phase history comes from prior orbit elements. | A wrong screen can change the available satellite IDs before association. The broad elevation margin permits overlap between screens. |
| Association and position | The release constructs a **25 × 25 km** square centered at **37.906° N, 122.545° W**. Hypotheses are discovered and ranked regionally, then east and north are bounded to ±12.5 km. Both calibration arms share the region. The CLI offers no override for either geographic center. | A true site outside the box cannot be returned. The solver can accept the best fit inside an incorrect box. The two orbit retries address temporal support and unusable historical elements; they do not search for a different region. |
| Geometry assumptions | The regional transform uses a local tangent approximation, with longitude scale proportional to the cosine of center latitude. Nominal orbit screening and the default frequency projector assume zero receiver altitude. | Height, high latitude and longitude wrap need explicit coverage before claiming broader geographic support. Their effects were not measured here. |
| Scoring and figures | The Gauss launcher separately supplies **37.84906159° N, 122.48574968° W** as the evaluation reference. The solver receives no such argument. The position PNG and published error use it after the estimate is selected. The map, optimizer-path defaults, path validator and default diagnostic-grid width also assume the Gauss frame or its width. | A copied launcher scores another station against the wrong roof. Changing just the numerical search can also break PNG publication, even if the new square still contains the roof. |
| Run identity and reuse | The localization run ID hashes the model ID and recording inventory. The existing worker reuses completed results under that ID. Geographic priors are absent from the key and the terminal decision. | Adding CLI coordinates alone would allow two offers for the same recording to reuse the first result. Bind the priors to a new versioned localization identity while preserving reusable, site-independent detector output. |

The active route calls `tools.algo08_position.solve` directly. The frozen benchmark wrapper and older job/render validators also contain roof-specific checks, but ALGO08 reaches the numerical core without calling those legacy entry points. The ALGO08 position-path validator, on the other hand, **is** used by the live publication store. [Detector and publication order](../../../tools/algo08_scan.py) · [Position wrapper](../../../tools/algo08_position.py) · [Sky screen](../../../src/leo/analysis/localization_v3/orbits.py) · [Position bounds](../../../src/leo/analysis/localization_v3/marginal.py) · [Launcher](../../../deploy/scripts/run-algo08) · [Path validator](../../../src/leo/contracts/position_path.py) · [PNG renderer](../../../src/leo/presentation/fast_standard_analysis.py)

## Controlled replay on measured I/Q-derived detections

I replayed the sealed November 21 7:24 a.m. Pacific Gauss recording from the detector-output boundary. All five requests used the same detection bytes, 237 tracks, capture time, archive, scientific code, calibration policies and search budgets. Only the two indicated geographic inputs varied. The harness observed the real selected-packet builder and recorded its path-validation outcome separately so a presentation exception could not hide a numerical decision. The stock run reproduced both published coordinates exactly.

| Offered search and sky screen | Sky candidates | Horizontal error, fitted / zero | Solver frequency RMS, fitted / zero | Numerical decision and publication-path check |
|---|---:|---:|---:|---|
| Deployed square and sky screen | 1,646 | 0.707 / 0.726 km | 110.46 / 110.34 Hz | Accepted, path passed |
| Square moved 3.51 km east, still contains roof; stock screen | 1,646 | 0.987 / 0.998 km | 110.97 / 110.84 Hz | Accepted, path rejected |
| Stock square, Denver screen only | 1,624 | 0.707 / 0.726 km | 110.46 / 110.34 Hz | Accepted, path passed |
| Square moved 66.6 km north, roof excluded; stock screen | 1,646 | 61.137 / 61.140 km | 101.49 / 101.43 Hz | Accepted on south edge, path rejected |
| Denver square and Denver screen, roof excluded | 1,624 | 1,540.575 / 1,540.574 km | 91.61 / 91.84 Hz | Accepted on east edge, path rejected |

The numerical solver accepted both omitted-region cases in both calibration arms. The lower conditional frequency RMS in the distant square illustrates why RMS alone cannot certify the region. Each fit can use different satellite associations and observations. The table uses the solver's own RMS field throughout. The published web diagnostic has a different residual calculation. Changing only the sky screen changed the candidate membership digest and count but left this particular endpoint unchanged. The Denver request used the same Gauss recording; it measures wrong-prior behavior, not accuracy at a physical Denver receiver.

All three changed-square queries failed the recorded-path endpoint check against the Gauss frame, including the valid overlapping offer. That check would prevent ordinary web publication of the counterfactual results. It cannot serve as a scientific wrong-region test.

In a separate post-fit test I passed the published manifest through three isolated copies of the release's scoring store. Removing the reference made the reported error unavailable. The real roof yielded 706.6 m fitted error and a Denver reference yielded 1,527.6 km. Both endpoint coordinates and the terminal digest were identical in all three. This test exercises scoring. The evidence that the reference is excluded from inference comes from the actual launcher-to-solver call graph. [Reference and numerical results](results.json)

## What the existing benchmarks establish

DS30 contains 455 recordings at one roof with the same geographic prior. The original protocol locked predictions before joining the evaluation reference. Its 439 fitted ALGO08 fixes measure repeated performance conditional on that region. An earlier **compact-backend** study with four simulated sites and generated native candidates returned four fixes within 5 km on containing tiles and four false fixes on the four near-omitted tiles. That study begins after raw acquisition. A different multi-region prototype forced the correct tile on 11/11 measured StarLoc captures at eight new site groups, but its withholding rule published 0/11 coordinates there. Neither study qualifies the complete deployed ALGO08 receiver on independent physical sites. [DS30 protocol](../../2026_11_21_ds30_full/PROTOCOL.md) · [Compact synthetic transfer study](https://github.com/misko/leo-tracker-reduxredux/blob/15ec65a425984bbfd0a9402730429351425d7d3f/reports/2026_11_19_receiver_screening/receiver-core/compact-blind/README.md) · [Measured multi-region prototype](https://github.com/misko/leo-tracker-reduxredux/blob/15ec65a425984bbfd0a9402730429351425d7d3f/reports/2026_11_18_blind_regional_receiver/README.md)

## Requirements for a portable release

1. Pass a declared search area and its provenance through the launcher, sky builder, solver, result identity, path and PNGs. Derive sky coverage from the offered area, or explicitly declare and validate a separate coverage region. Make evaluation truth optional and site-specific. Introduce compatible versioned contracts for changed path semantics.
2. Specify whether operators supply a coarse area or expect the receiver to discover one. A receiver with no trusted area needs a wider or multi-region search and a validated way to withhold when the true area is absent. A boundary hit is a diagnostic worth testing. Real receivers can also be near a valid boundary.
3. Freeze the receiver and thresholds, hold out entire physical stations, and run raw I/Q from each through to the published fix and PNGs. Offer containing, edge and missing regions without exposing station truth. Score fix coverage, false publications, horizontal error over **all** assigned recordings and runtime by site. Keep fitted and zero calibration paired, and score frequency fit separately. Use the DS30 replay as a compatibility check.

## Reproduce the prior perturbations

Use an installed release with its native assets, the original recording's detector output, its standard-analysis manifest and the capture-era TLE archive. Each process emits one JSON row. The manifest supplies the publication binding for the path check after fitting.

```sh
release=/opt/leo-algo08/0efaf3b88e9c155c2847a6fa21c354aabf788cb6
export PYTHONPATH="$release/src:$release"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
for condition in stock overlap screen_only omit far; do
  "$release/venv/bin/python" -Bs replay.py \
    "$condition" "$DETECTIONS" "$MANIFEST" --assets "$release/assets"
done
```

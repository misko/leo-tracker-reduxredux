# Antenna confirmation gallery

[Browse the studies](index.html) · [Download the offline ZIP](modification-charts.zip) · [Verify exported files](pack-lock.json)

The gallery contains 19 position comparisons in both calibration settings and 9 standalone stage charts, for 47 figures. The [chart inventory](chart-inventory.csv) describes each measurement boundary. The [position table](positions.csv) holds the 1,616 plotted rows, including calibration availability and separately saved diagnostic estimates.

## Rebuild the gallery

```sh
evidence=reports/2026_11_19_receiver_screening/antenna-confirmation
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval.qualification.receiver_core_pack \
  --evidence "$evidence"
.venv/bin/python -m tools.pipeline_eval.qualification.gallery_check "$evidence/charts" \
  --expected-charts 19
```

The eight discovery recordings and the 14 validation recordings partition the established 22-recording roof set. The audit found 22 distinct original requests and 308 distinct authenticated capture-segment manifests across these recordings. The validation set holds out recordings for the antenna comparison at the same site. [Discovery receipt](../pilot-influence/partner-on-hit/prediction-lock.json) · [Complete roof roster](../pilot-influence/one-lane-benchmark/roster.json)

The direct holdout roster uses DS26-0168 and DS29-0174 from the 14-case complement. The additional direct comparisons use DS26-0066 and DS29-0085. Their 28 recorded segment manifests are distinct from each other and from every segment in the 22-case study. The direct IQ receipts bind exact captured inputs, per-visit partner decisions, and terminal position outputs. The additional comparison ran both detector policies from saved IQ and uses four newly measured original v5 references for DS29-0085. [Direct holdout parity](on-hit-waveforms/parity.json) · [Additional recording parity](fresh-full/parity.json) · [New v5 reference binding](fresh-full/reference-binding-audit.json)

Position comparisons retain all scheduled recordings and offered regions in both calibration settings. Withheld, failed, and unavailable outputs stay in the denominator. Diagnostic estimates appear separately when a numerical worker saved one. Direct IQ replay, measured position fits on stored factors, detector-only timing, and offer-coordinate-only controls each report their own measurement boundary.

The paced comparison runs both antenna policies at the original DS29-0174 delivery schedule and fits the packets each branch actually emitted. It accounts separately for 70 hardware-invalid visits per branch and 77 stock versus 92 partner-on-hit queue drops. The quarter-miss study fits stored detector factors and reports logical detector calls. It presents the previously evaluated 14-case set separately from its two prospective recordings. [Paced timing](paced-hit/timing.csv) · [Quarter-miss protocol](quarter-miss/PROTOCOL.md)

The complete capture-era replay covers all 6,772 scheduled DS29-0082 visits, including the 1,904 archived invalid visits. All 9,736 valid physical probes agree with the original capture. Two fresh compact fits on the measured factors and the archived factors returned identical positions and RF residuals in both calibration settings. Detector CPU and parallel host elapsed time are reported separately. [Capture replay report](capture-whole/README.md) · [Capture replay audit](capture-whole/audit.json) · [Position and RF scores](capture-whole/scores.csv)

The asymmetric StarLoc study compares the anonymous RF receiver with a geometry-only policy that publishes the offered centre nearest the common coarse Illinois anchor. Its 48 boards include 24 containing and 24 omitted offers over eight measured locations. The geometry-only rule published on all 48 boards. The held-gain rule published on 11 containing and 5 omitted boards, matching the interior-only rule. The most favorable pair midpoint uses the evaluator's truth and appears only in the geometry table. [Board construction and control](asymmetric-sites/PROTOCOL.md) · [Per-offer scores](asymmetric-sites/scores.csv) · [Geometry table](asymmetric-sites/geometry.csv)

The worldwide geometry and orbit-proposal receivers use the same four recorded samples and two shuffled controls. The offer labels are applied after inference. Both receivers withheld all six queries. The derivative fit makes the constant RF calibration term unidentifiable. [Worldwide decisions](anonymous-geometry/scores.csv) · [Physical proposal decisions](orbit-proposals/scores.csv)

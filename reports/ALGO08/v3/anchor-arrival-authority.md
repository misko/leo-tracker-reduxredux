# Native arrival epoch cannot separate the four disputed 0049 anchors

Three of the four extra full anchors owned by the DS30-0049 mixed solver have **no simultaneous peer measurement**. The remaining anchor agrees in phase with the offset estimated exclusively from other, short visits. Its residual is below **0.16 sample** using either half of those visits as training. Requiring a positive peer would also remove **27 of 71 installed-positive anchors**, including **20 of 43 installed-owned anchors**. No anchor membership rule was produced. [Frozen protocol](anchor-arrival-authority-protocol.md) · [Sealed census](measurements/anchor-arrival-authority.json)

## What the native fields can measure

The observable is `valid_start_counter + integer_epoch_sample + fractional_epoch_offset_samples` modulo the physical pilot period, **40,000/3 samples at 10 MS/s**. The implementation reduces the integer counter on the three-tick lattice before adding a floating fractional epoch. The normal signed detector exports the same input counter for both antennas in a visit, so that term cancels from the stereo phase difference. The receiver uses a 13,333-sample window-relative search circle, and signed CFO has a different ambiguity period of 10 MHz/44. An approximate timing circle, folded CFO and signed fractional epoch each answer different questions. The ordinary Graph labels the observation at the nominal 20 ms visit midpoint. Signal weighting also changes the effective CFO time within the aperture. Neither is a native arrival observation. [Native export](../../../tools/pipeline_eval/qualification/full_v5_check.py) · [Ordinary Graph clock](../../../src/leo/analysis/glrt_frequency_input.py) · [Previous CFO-time audit](sparse8-cfo-epoch.md)

If the antennas measured the same transmitter, emitter phase and the common sample counter cancel. The residual still contains differential propagation, chain delay and fit error. When they measured different transmitters, an unknown transmit phase remains. The three physical documents have null source timing authority and carry no independently calibrated inter-radio group delay or phase-center binding. The earlier North/South simulations deliberately co-locate both synthetic antennas and plant a 0.42-sample lane shift. The previous audit recovered about 0.440 and 0.445 samples there, under known same-emitter conditions. The physical inputs have different authority. In the earlier 80-visit physical pair audit, only 56 of 141 verified factors had a phase partner within two samples, and none agreed also within 1 kHz in absolute signed CFO. The similarly named radio-epoch study selected Doppler time blocks and supplied no stereo delay calibration. [Timing authority](../single-core-2x/absolute-timing-authority.md) · [Previous stereo phase support](../single-core-2x/receiver-lanes.md) · [Radio-epoch scope](radio-epoch.md)

## What the saved rows support

The census used only original paid winners and empty opportunities. At an anchor both radios were scheduled full, so a positive same-visit peer was already a full measurement. The native diaries reproduce the original strongest mixed and full chronological continuation exactly through the first 384 issued 0049 visits and complete 0016. The 0407 original verified pair gives only its published selected detectors and the full opportunity mask. None supplies independent emitter identity for a simultaneous pair.

| Capture | Full-anchor lanes | Mixed positives | Mixed positives with peer | Installed-positive anchors lacking peer | Installed-owned anchors lacking peer | Extra positives with peer |
|---|---:|---:|---:|---:|---:|---:|
| DS30-0049 | 242 | 83 | 50 | 27 / 71 | 20 / 43 | 6 / 12 |
| DS30-0016 | 186 | 74 | 36 | 31 / 58 | 3 / 13 | 9 / 16 |
| Held DS30-0407 | 1,682 | 797 | 650 | 121 / 714 | Unavailable | 57 / 83 |

The figures for peer availability grant every present peer as potentially informative. A real paired check still has to identify a common transmitter and establish differential delay. For a purely descriptive offset check, the candidate center comes from the largest unique circular cluster within the existing ±2-sample tolerance on one half of *other* short visits. The opposite half and all anchors are excluded from fitting. On DS30-0049 the early-half center of **+0.0476** samples matches **17/42** late pairs. The late-half center of **+0.0742** matches **6/37** early pairs. Held 0407 also gives a recurring near-zero mode, matching **223/913** late and **261/891** early pairs. In 0016 the first half has three tied maximum clusters of two pairs, and the only fitted center from its second half transfers to just **1/48** pairs. A common mode in two datasets supplies no independent calibration or a veto on single-lane detection.

| Extra 0049 mixed owner | Simultaneous paid peer | Earlier / later short positives within 2.5 s | Held-fit stereo phase residual |
|---|---|---:|---|
| Visit 4, RX0 | Empty | 0 / 5 | Unavailable |
| Visit 5, RX0 | Empty | 0 / 4 | Unavailable |
| Visit 6, RX0 | Empty | 0 / 3 | Unavailable |
| Visit 461, RX1 | Positive | 0 / 0 | −0.1313 / −0.1579 samples |

At visit 461 the original RX1−RX0 epoch difference is −0.08375 sample. Their signed CFOs differ by +686.320 kHz, which becomes +4.502 kHz after frequency alias folding. That folding supplies no physical calibration or common-emitter assurance. A permissive phase test would retain this extra. For the other three extras, later short neighbors provide opportunities for a retrospective check, while none supplies an earlier two-point secant or a bracket.

## Why there is no calibrated temporal fallback

Previous same-track empirical epoch forecasts often succeeded when given Graph tracks from the full recording. That evidence is conditional on the already identified track. In the causal tracker without such labels, prior native winners supported an epoch forecast within two samples for **95 of 2,877** missed capture families. Directed donor extrapolation on 0016 matched **11 of 135** full factors at the fixed timing and signed-frequency tolerance even when granted previously fitted donors. A separate physically signed code–carrier closure audit measured **52.257 samples RMS** on physical DS30-0016, worse than **25.953** for clock alone. The reflected sign reached **1.748** on that capture, while the physically positive sign won on both simulations. Choosing reflected sign would fit a known outcome without a supported transfer model. [Track timing](../../2026_11_19_receiver_screening/receiver-core/track-timing/README.md) · [Track-free causal proposals](../../2026_11_19_receiver_screening/receiver-core/causal-track-scout/README.md) · [Directed donor transfer](directed-donor.md) · [Signed arrival closure](../single-core-2x/arrival-observability.md)

DS30-0010 had a sealed installed detector only at this audit. The later official pair enabled the preregistered held transfer. No I/Q, catalogue, RF collection, solver run, or Gauss lease was used. [Completed 0010 transfer](anchor-arrival-0010.md)

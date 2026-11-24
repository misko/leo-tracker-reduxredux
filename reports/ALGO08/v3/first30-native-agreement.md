# Signed 20 ms and 8 ms native agreement across the first 30 pairs

The retained mixed receiver changes both which peaks are reported and the measurements on peaks that match. A fixed, causal aperture-centroid CFO correction reduced held squared disagreement by **2.13%**, from **98.735 to 97.677 Hz RMS**. After removing each capture and radio's mean, the same correction reduced squared disagreement by **0.040%**, from **97.480 to 97.460 Hz RMS**. The case-bootstrap interval spans zero. The independently signed timing-rate correction increased centered squared disagreement by **83.8%**, from **0.449 to 0.609 sample RMS**. The experiment identifies a repeatable mean offset on the matched support and little evidence for useful residual prediction after radio nuisance removal. [Frozen protocol](first30-native-agreement-protocol.md) · [All 30 case receipts](measurements/first30-native-agreement.json.gz).

## Common, added and removed support

The comparison uses every positive published factor on each original signed visit and radio. It requires a mutually unique pairing within ±250 signed Hz and ±2 absolute fractional samples, without alias or frame wrapping. The CFO tolerance is 0.56 of the original 443.892 Hz residual spectrum bin. The matched short factors used five 8 ms verifier frames against fourteen full frames on 17,414 matches and fifteen full frames on 65,644. All 30 mixed EOF held selectors chose `unfiltered` and no post-selection 20 ms remeasurement ran. [Source frame-admission arithmetic](within_aperture_chirp.py).

| Original lane or retained factor count | Mixed 8 ms vs installed 20 ms | Both 20 ms at full anchors |
| --- | ---: | ---: |
| Signed lanes | 262,770 | 37,752 |
| Both empty | 121,432 | 19,037 |
| Installed-only positive lanes | 16,826 | 0 |
| Mixed-only positive lanes | 24,076 | 2,012 |
| Both positive, one-to-one peak match | 83,058 | 16,057 |
| Both positive, outside the paired peak cut | 17,378 | 646 |
| Total unmatched installed factors | 34,204 | 646 |
| Total unmatched mixed factors | 41,454 | 2,658 |
| Canonically identical matched native factors | 0 | 16,057 |

There were no multi-edge ambiguities in the retained packets. Both paths published at most one passing factor per lane. The 83,058 short matches cover **70.83% of the installed positive peaks** and **66.71% of the mixed positive peaks**. The wholly one-sided lanes are distinct from the 17,378 dual-positive short lanes with different reported peaks. The latter contribute to both unmatched factor totals. The threshold cannot distinguish a true change of carrier from an otherwise corresponding peak that moved beyond the threshold.

Both paths used the same pinned native binary at the full anchors. The installed wrapper calls the binary, then retains the `selective` output of the chronological `Continuation.select`. That output needs at least three historical votes. With two measured candidates, sufficient vote separation can also promote a candidate above the strongest-margin choice. The mixed receiver keeps the strongest verified native margin at the full anchor, with lower native rank breaking a tie. An unfiltered EOF selector preserves that earlier choice. Those two packet selectors can therefore create mixed-only and different-peak cases even with identical native candidate lists. The archived packets retain only the chosen factors. They omit the upper native candidate list and continuation vote history needed to attribute individual cases. The 2,012 and 646 counts describe selected outputs at the signed packet boundary. The 16,057 identical reciprocal anchors give the exact control on the same retained peak. [Mixed packet selection](mixed_aperture_receiver.py) · [Installed native wrapper](../../../tools/pipeline_eval/qualification/blind_compact_run.py) · [Chronological continuation](../../../tools/pipeline_eval/variants/carrier_continuation.py).

## Signed offsets and held prediction

Across all 82,774 matched short peaks in the later recordings, mixed-minus-installed mean CFO was **+13.734 Hz** on radio 0 and **+15.756 Hz** on radio 1. Both receivers had positive means on each of the 27 recordings with matches. Mean fractional epoch shift was **−0.324 sample (−32.4 ns)** on radio 0 and **+0.178 sample (+17.8 ns)** on radio 1. Those directions also held in every one of the 27 recordings. Radio-specific raw epoch RMS was 0.568 and 0.484 sample. The epoch is measured frame alignment. The centroid used to predict a difference is an elapsed time inside each aperture.

The CFO model predicts the difference in equal-frame centroids multiplied by a signed Doppler slope from the two preceding singleton mixed observations in the same stream. It retains 51,435 of 82,774 held matches, **62.14%**. The epoch model uses the same centroid difference and the mixed CFO divided by the recorded RF as a fractional apparent time rate, times the 10 MS/s sample rate. It is a propagation-only hypothesis and can include oscillator and native alias terms when applied to the actual CFO. It is scored on all 82,774 held matches. For both observables, DS30-0049 selected the physical + sign after within-radio demeaning. No magnitude was fitted and no held installed factor provided a predictor input.

| Held comparison | Matched predictions | Before → after RMS | Squared-loss reduction | 95% recording-bootstrap interval | Improved recordings |
| --- | ---: | ---: | ---: | ---: | ---: |
| CFO, uncentered | 51,435 | 98.735 → 97.677 Hz | +2.132% | +1.726% to +2.525% | 26/27 |
| CFO, recording/radio centered | 51,435 | 97.480 → 97.460 Hz | +0.040% | −0.067% to +0.143% | 16/27 |
| CFO, recording/radio/stream centered | 51,435 | 97.107 → 97.088 Hz | +0.039% | −0.063% to +0.135% | 17/27 |
| Epoch, uncentered | 82,774 | 0.535 → 1.859 sample | −1,108.0% | −1,193.5% to −1,031.4% | 0/27 |
| Epoch, recording/radio centered | 82,774 | 0.449 → 0.609 sample | −83.8% | −147.6% to −32.4% | 9/27 |
| Epoch, recording/radio/stream centered | 82,774 | 0.439 → 0.578 sample | −73.3% | −138.2% to −20.8% | 10/27 |

The denominator of 27 excludes development DS30-0049, earlier smoke DS30-0107, and later DS30-0314, which has no qualifying short peak match. Those three recordings remain in the support census. DS30-0220 is the one held raw CFO loss increase. Each nuisance mean uses the matched held scope and is removed from both observed and predicted values for the diagnostic. Bootstrap intervals resample whole recordings. The readout used signed receiver observations only. The two receiver recipes share samples, and only within-cut common peaks inform agreement. [Prior strongest-peak timestamp result](sparse8-cfo-epoch.md) · [Within-aperture physical bounds](within-aperture-chirp.md).

The protocol was sealed at `0ed97d760` and the readout ran at `eb1f3b410`. All 60 existing native JSON documents were bound to their verified record digests, with 245,382,155 unique local bytes and reconciled per-aperture call counts. An initial metadata readout stopped on an omitted zero-valued short-call counter and was rerun after the parser was corrected. No waveform, physical catalogue or solver ran. Three focused component tests passed. The uncompressed receipt SHA-256 is `096e0dbc8770b7a34d39e82e9739c5f9c70af23f554c5966d92b6a9e49a4e81b`. The [reducer](first30_native_agreement.py) takes the frozen campaign root and sealed first-30 ledger directory.

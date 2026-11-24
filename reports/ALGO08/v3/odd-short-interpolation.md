# Blind interpolation reaches few of the omitted short detections

Skipping odd admitted visits removed about **57% of the original short callbacks** on both recordings. The retained-only Graph nominated a small, precise subset. On held DS30-0086, **183 of 214** proposals matched both signed CFO and physical pilot arrival within 250 Hz and two samples, covering **10.9% of all 1,674 omitted installed positives**. Six strict hits came from lanes the original short receiver measured as empty. With broad-search fallback wherever the rule abstains, at most **214 of 8,372 short callbacks** on that case can avoid the broad search before verification and buffering costs. [Frozen rule](odd-short-interpolation-protocol.md) · [Prediction seal](measurements/odd-short-interpolation-plan.json.gz) · [Score receipt](measurements/odd-short-interpolation-score.json)

| Recording | Omitted lanes | Installed positives among omissions | Nominated | Tight joint | Loose joint | Installed-empty nominations |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DS30-0049, development | 926 | 256 | 45 | 38 / 256 (14.8%) | 42 / 256 (16.4%) | 2 |
| DS30-0086, held | 4,784 | 1,674 | 214 | 183 / 1,674 (10.9%) | 202 / 1,674 (12.1%) | 4 |

The tight counts include all omitted positives in the recall denominator. Tight precision among issued proposals was 84.4% and 85.5%. Seven and 31 nominations failed the tight reference comparison. Of those, five and 27 had an installed positive in the lane but failed the joint window. Tight carrier-only matches were 38 and 189. The physical arrival requirement kept 38 and 183. The quarter-circle arrival control got zero hits at either window. The loose window was 2,250 Hz and six samples. The installed-empty category means the stock detector supplied no passed winner on that opportunity.

| Recording | Strict matches on originally empty short lanes | Strict matches on originally positive lanes, original also matched | Strict matches on originally positive lanes, original disagreed | Strict matches on originally installed-owned omitted lanes, each calibration arm |
| --- | ---: | ---: | ---: | ---: |
| DS30-0049 | 0 | 32 | 6 | 28 / 155 |
| DS30-0086 | 6 | 161 | 16 | 164 / 1,251 |

Original short presence and original agreement were joined only after freezing the prediction. Held DS30-0086's loose window covered 182 of the 1,251 installed-owned omitted lanes. Both installed owner rosters were independently bound to their published arm digests. Pure dropping yielded zero forecasts or omitted matches and retained the same measured Graph. The masked Graph assigned **174 of the original 399** points on 0049 and **912 of 2,434** on 0086. The dominant reason for no forecast was that at least one immediately bracketing retained winner lacked a unique Graph piece. There were also 211 and 1,138 spacing exclusions. Forecasts never entered the Graph as measured factors. Localization was outside this study.

## Callback, age and storage limits

| Recording | All scheduled skipped shorts | Gross wall / CPU at original mean short cost | With broad-search fallback, maximum short calls avoided | Gross fallback ceiling wall / CPU |
| --- | ---: | ---: | ---: | ---: |
| DS30-0049 | 926 / 1,622 | 1.062 / 0.995 s | 45 / 1,622 (2.77%) | 0.052 / 0.048 s |
| DS30-0086 | 4,784 / 8,372 | 6.252 / 5.591 s | 214 / 8,372 (2.56%) | 0.280 / 0.250 s |

All 242 and 1,202 full radio callbacks remain. The fallback ceiling counts individual radio lanes. Only one and 41 omitted stereo visits had proposals on both radios. The estimates multiply the original measured mean short callback by the exact number eligible to omit. They exclude the expense of Graph nominations, delayed narrow verification and retaining samples. Original signed reading, decoding and hashing get zero credit. No new detector or end-to-end speed was measured.

The right donor arrived about 0.354 s after the omitted window for both cases, with maxima of 0.3553 and 0.3556 s. That is the minimum forecast age even with earlier decisions ready. The original Graph fits the complete available session and has no certified online piece finalization rule. Keeping every scheduled omission's original IQ until EOF would require **296 MB and 1.531 GB** at the 8 ms aperture, or **741 MB and 3.827 GB** at 20 ms, before storage overhead. A bounded online variant would need its own chronological Graph and verification evidence.

## Custody and comparison

The prediction process denied reads of original installed outcomes. It dropped every candidate object from the held visits before either winner selection or the pinned released Graph. It kept the signed opportunity clocks, exact RF and separate radio lanes. Both retained donors agree on the native alias branch, so the score compares signed CFO directly. The arrival test uses the original counter-reduced physical sample circle. Earlier half-duty decimation tested a different mask and its saved solver consequences. The already-empty Graph rescue retains all actually measured candidates for its original fit, and the fixed-piece CFO blend uses the original middle detection. Here the target could be positive or empty, and its measurement never entered the fit. [Earlier half-duty mask](balanced-stereo-protocol.md) · [Already-empty compound check](empty-lane-arrival.md) · [Fixed-piece CFO blend](track-cfo-denoise.md)

Predictor and protocol were frozen in `849cf00b4`, and the proposal file was committed in `19cdf5f55` before opening stock references. The original scoring entry expected the older ownership witness schema. The separate offline readout binds 0086's actual saved terminal and both owner digests without modifying the sealed predictor or any proposal. Ten component and adjacent tests passed. Only the two enrolled saved detector pairs and metadata were read, with no lease, solver, waveform, ephemeris or backing reads. [Predictor](odd_short_interpolation.py) · [Post-seal readout](odd_short_interpolation_readout.py) · [Tests](../../../tests/pipeline_eval/test_odd_short_interpolation.py)

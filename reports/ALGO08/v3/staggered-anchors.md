# Staggered full-aperture anchors on saved stereo factors

Moving the second radio's full-aperture anchor four admitted visits later reduced gaps between visits with a full-aperture measurement. It preserved 77 of 101 installed owners on the fully measured DS30-0049 prefix, the same count as coincident anchors, and recovered none of the seven owners that had become empty there. Alternating a single full radio cut full calls in half. It lost two owners on that prefix and could preserve at most 226 of 320 on full DS30-0049, below the coincident schedule's observed 228. The evidence supports neither schedule as a receiver change.

## Coverage and work

The second radio is `receiver_id=1`. Schedules count only admitted visits within each exact `(edge, channel, actual RF)` stream and use no signal measurements in the phase rule. On whole eight-visit cycles, coincident and phase four pay two genuine 20 ms two-scan calls and 14 genuine 8 ms primary calls. The single-radio schedule pays one full and 15 short calls. Every admitted lane still has an aperture. The count difference between coincident and phase four on some full scopes comes from final partial cycles with fewer than five visits.

| Scope | Original admitted visits | Full calls, coincident / phase four / single | Full calls on complete cycles | Worst internal gap with either radio full, coincident / phase four / single |
|---|---:|---:|---:|---:|
| DS30-0049, six members | 362 | 92 / 91 / 46 | 88 / 88 / 44 | 6.035 / 3.545 / 6.035 s |
| DS30-0049, full | 932 | 242 / 236 / 121 | 226 / 226 / 113 | 6.035 / 3.545 / 6.035 s |
| DS30-0016, full | 713 | 186 / 181 / 93 | 170 / 170 / 85 | 6.025 / 3.546 / 6.025 s |
| DS30-0008, first member | 64 | 16 / 16 / 8 | 16 / 16 / 8 | One original anchor per stream |
| DS30-0169, first member | 51 | 16 / 14 / 8 | 8 / 8 / 4 | One original anchor per stream |

Full DS30-0049 changed from 121 simultaneous two-full visits to 236 one-full visits with phase four or 121 one-full visits with alternating single. Phase four reduced the longest run without a full lane on either radio from seven to three admitted visits on all five scopes. It left the longest per-radio run at seven. Alternating single kept the seven-visit either-radio run and extended the per-radio run to 15 on the longer scopes. On 0049 the worst same-radio internal gap rose from 6.035 to 10.640 s. The short prefixes had no internal gaps between separate coincident anchors on the same stream. The replay prices calls and reports no live CPU or raw timing.

## Same-factor retention

A match requires signed CFO within 250 Hz and wrapped fractional epoch within two samples of the installed chronological factor. The strict selected-factor identity and per-radio/channel results are in the evidence. The shared denominator includes lanes with an actual selected-aperture result under all three schedules. The stricter paired count requires both apertures to have been measured on that exact lane. The full-support range treats unknown outcomes as possible failures or successes. Installed positives and owners stay fixed.

| Scope | Lanes with both apertures / shared known / total | Matches on fixed shared installed positives, coincident / phase four / single | Bounds on all installed positives, coincident / phase four / single |
|---|---:|---:|---:|
| DS30-0049, six members | 724 / 724 / 724 | 129 / 129 / 123 of 184 | 129 / 129 / 123 of 184 |
| DS30-0049, full | 724 / 1,682 / 1,864 | 318 / 318 / 312 of 483 | 355 / 335–366 / 323–349 of 531 |
| DS30-0016, full | 1,240 / 1,290 / 1,426 | 262 / 269 / 262 of 400 | 302 / 289–309 / 273–302 of 440 |
| DS30-0008, first member | 112 / 120 / 128 | 15 / 15 / 15 of 19 | 15 / 15 / 15 of 19 |
| DS30-0169, first member | 86 / 94 / 102 | 12 / 13 / 12 of 15 | 12 / 13 / 12 of 15 |

On the fully paired 0049 prefix, phase four traded four matches for four others on radio 1. Channel 1 gained and lost one, channel 4 lost one, and channel 8 gained three and lost two. Strict identity rose from 22 to 23 of 184 installed positives and stayed at 12 of 101 installed owners. On complete cycles with exactly equal full-call budgets, both coincident and phase four matched 125 of 178 installed positives and 73 of 95 owners. The single-radio schedule matched 120 and 72. Neither schedule found a match on the seven previously empty or the two strongly displaced owner lanes in the prefix.

For full 0049, phase four bounded the matched owners at 220–230 of 320 in each arm, versus 228 recorded at coincident anchors. It preserved exactly the same 217 matched owner visits out of 286 even under the upper bound. Across the full capture it could recover at most one of the 44 formerly empty owners and at most one of the 21 displaced owners, with no observed recovery. The half-cost schedule bounded matched owners at 210–226 and matched owner visits at 206–215. In full 0016, the seven shared gains with phase four were all on radio 1, across channels 3, 4, 5 and 7, with none from installed owners. Phase four preserved exactly 100 of 109 installed owners, as did coincident anchors. The half-cost owner interval was 93–100. The independent first members supplied one extra match with phase four in 0169 radio 1/channel 1 and no extra match in 0008. Original anchor short outcomes were unmeasured in those two scopes and 0016. On full 0049, outside the six-member factorial, a full installed Continuation selection never substitutes for an unmeasured strongest full result.

## Held selector

The fully observed 0049 prefix stayed unfiltered under all three schedules. Its radio 0 held log-score gain stayed −7.066 with phase four. Radio 1 changed from −0.166 to +5.085, so the requirement for positive gain on both radios still failed. Phase four reduced complete radio 1 validation examples from 44 to 37. Alternating single reduced complete held examples to 23 on radio 0 and 21 on radio 1 and produced gains of −8.736 and +0.129. The replay masks every actual full anchor before the causal history sees its donors. It compares the seven genuinely short following observations per held anchor, with the original two-radio gate and Jeffreys half-count. The whole-record choice uses these subsequent donor observations. Separately applying Continuation to the unmasked strongest packets retained 110, 111 and 107 installed matches in the prefix. Neither modified whole-record selector is resolved where alternate aperture outcomes are missing.

Earlier balanced stereo, whole-cycle stereo, stereo lane masks, and complete RF streams changed which lanes or visits were paid while preserving the original full-anchor alignment. This audit moves the full aperture across radio slots and retains one measurement for each admitted lane. It used only existing factor products, without waveform access, receiver execution, or position solving. [Frozen protocol](staggered-anchors-protocol.md) · [Sealed coverage, bounds and per-channel evidence](measurements/staggered-anchors.json.gz)

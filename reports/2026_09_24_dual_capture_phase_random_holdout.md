# September 24 dual-capture phase with random holdouts

The full-day September 24 saved-IQ cohort has substantially stronger
shared-waveform phase evidence than the earlier 2.5 MS/s random-group sample.
Across all 44 finalized compatible captures, 272 of 352 phase-blind selected
dwells pass the held-waveform gate. Among the 301 successful extractions,
median residual phase concentration is **R = 0.9659**, median tracked coherence
is **0.1569**, and median wrong-pair coherence is **0.00669**.
This is useful capture-level signal, with the strongest coverage on radio
`5d4d`. It does not establish satellite identity, geometric phase, or improved
position accuracy.

## Cohort and coverage

The cohort freezes every finalized 2.5 MS/s simultaneous dual-RX adaptive
capture started during September 24 UTC: 44 captures and 97,512 complete
stored visits. This adds 23 late-day captures and 50,970 visits after the
earlier report's `15:39:44Z` cutoff. The partial 15 MS/s session
`scan-fw-f3ce5fe73aa40506` remains outside the common-rate cohort: it retained
1,624 of 2,224 emitted visits and its complete sealed sparse-GLRT inventory has
zero paired phase candidates. No capture was started for this study, and every
read of saved IQ and production analysis was read-only.

Forty-one captures use sealed, complete production GLRT inventories. Two
captures from radio `19f2` use receipt schema 6 and have no compatible sealed
metrics product; that receipt contract permits variable 120/240/360 ms visits.
Every retained event in these two immutable manifests is exactly 120 ms. A
report-local adapter therefore validates the V6 receipt,
event endpoint, stored-IQ shape, and manifest digest before applying the same
pure GLRT numerics. The final late-day V4 capture had only 984 of 2,218 sealed
sparse-GLRT rows at the frozen audit, so the same report-local path screens its
complete fixed-duration inventory rather than selecting from a partial product.
Together these three screens cover 6,654 visits with zero numerical errors and
find 132, 101, and 110 phase-blind paired candidates. They write only report
evidence and do not downcast or persist an analysis product.

![Replay coverage by capture](figures/2026_09_24_dual_capture_phase_random/coverage-by-session.png)

For every capture, selection takes the eight visits with the strongest
phase-blind paired-GLRT fractional-margin floor after screening its complete
stored-visit inventory. Phase outcomes never affect selection, and failed
extractions are never replaced. This yields 352 selected dwells, 301 completed
phase extractions, and 51 dwell-level abstentions:

| Abstention reason | Count |
| --- | ---: |
| Local phase increment near pi | 13 |
| Fewer than eight coherent physical-overlap bins | 21 |
| No A-band response-normalization support | 5 |
| No paired training-group carrier seed | 3 |
| No qualified shared response | 6 |
| Insufficient disjoint frequency support | 3 |

All 44 captures have valid-duty fractions between 0.8844 and 0.8896. That
narrow range is below 0.90, so this replay should not be used to infer behavior
at a 90% duty threshold.

## Random-holdout protocol

There are **no time holdouts** in this study. Seed `20260924`, combined with the
session ID and visit index, assigns complete 20 ms groups within each 120 ms
dwell to a deterministic 50/50 random split. The split is stratified over the
dwell, preserves device-relative sample timing, and keeps every receiver and
spectral window in a group on the same side.

Carrier seeding uses only paired phase-blind GLRT probes wholly inside training
groups. Carrier fitting, response normalization, frequency-bin selection, and
inner model selection also use training data. Within each random-held block,
frequency band A supplies the instantaneous relative phase used to predict a
disjoint band B. A one-to-one cross-group pairing supplies the wrong-pair
control with the same flexibility.

The requested phase-correlation statistic is the same circular resultant
metric used in the prior random validation. For each held group it averages
unit phasors of the B-band residual phases; the reported value is the magnitude
of the equal-group complex mean:

\[
R = \left|\frac{1}{G}\sum_{g=1}^{G}
    \left(\frac{1}{N_g}\sum_{k=1}^{N_g}e^{j\epsilon_{gk}}\right)\right|.
\]

Thus `R = 1` indicates concentrated residual phase and `R` near zero indicates
dispersed residual phase. This circular phase concentration is distinct from a
Pearson correlation coefficient. The fixed gate requires tracked held-B
coherence above `max(0.05, 3 × wrong-pair coherence)` and `R > 0.8`.

## Evidence

| Radio | Supported / selected | Replayed | Median R | Median tracked / wrong coherence |
| --- | ---: | ---: | ---: | ---: |
| `19f2` | 17 / 32 | 24 | 0.9201 | 0.1202 / 0.00852 |
| `5d4d` | 255 / 320 | 277 | 0.9677 | 0.1599 / 0.00662 |
| **Combined** | **272 / 352** | **301** | **0.9659** | **0.1569 / 0.00669** |

The combined pass fraction is 77.3% of phase-blind selections and 90.4% of
successful extractions. The 23 newly added captures contribute 141 supported
dwells from 184 selections and 155 successful extractions. Their median
`R = 0.9629`, median tracked coherence is 0.1459, and median wrong-pair
coherence is 0.00681. The radio split still matters: `19f2` passes 53.1% of its
selected dwells, compared with 79.7% for `5d4d`. The broad conclusion remains
driven mainly by `5d4d`, while the full-day coverage also exposes capture-level
variation, including one late capture with only three successful extractions.

![Held R by radio, channel, and edge](figures/2026_09_24_dual_capture_phase_random/r-by-radio-channel.png)

Exact simultaneous pairs separate cleanly from the cross-group control for
most replayed dwells. A few points retain high coherence but fail the `R` gate,
which is why the composite decision retains both conditions.

![Tracked coherence versus wrong-pair control](figures/2026_09_24_dual_capture_phase_random/tracked-vs-control.png)

The September 23 2.5 MS/s random-group reference passed 2 of 8 selected dwells,
with six successful extractions, median `R = 0.6706`, median tracked coherence
0.1060, and median wrong-pair coherence 0.01727. The new cohort shifts all
three descriptive metrics in the favorable direction.

![Descriptive comparison with the prior random validation](figures/2026_09_24_dual_capture_phase_random/historical-r-comparison.png)

That comparison is descriptive rather than a causal hardware or method
estimate. Capture time, radio, RF target, source mixture, and selection pool all
differ. The result supports a better signal in today's captures under the same
random-held waveform test; it does not identify which changed condition caused
the improvement.

## Relationship to the recent phase work

This replay carries forward the strongest safeguards from the recent reports:

- The corrected dual-RX analysis applies relative CFO once; the September 16
  diagnosis showed that double-counting it can manufacture phase drift.
- The September 23 random-group method supplies the present leakage boundary,
  disjoint held-B response, wrong-pair control, abstention rules, and fixed
  composite gate.
- The source-seeded pilot study showed that training-only known-pilot evidence
  can choose a useful local CFO branch. Its phase-rate feedback did not improve
  held results consistently, so no phase-slope feedback is added here.
- The September 24 index audit found no off-by-one rescue for the older
  capture. This replay consequently uses exact persisted visit indices and does
  not shift or borrow them.

The next useful step is source-bound validation: freeze a candidate/source
hypothesis before looking at phase, compare Doppler-only and phase-augmented
scores on the same random groups, and retain different-source controls. The
present broadband result is strong enough to justify that experiment, but it
must remain separate from claims about named satellites or geometry.

## Reproduction and artifacts

The [artifact README](figures/2026_09_24_dual_capture_phase_random/README.md)
contains the replay commands. The
[summary](figures/2026_09_24_dual_capture_phase_random/summary.json),
[per-dwell table](figures/2026_09_24_dual_capture_phase_random/per-dwell.csv),
[frozen cohort](figures/2026_09_24_dual_capture_phase_random/cohort.json),
[report-local screen audit](figures/2026_09_24_dual_capture_phase_random/report-local-screen-summary.json), and
[compressed evidence](figures/2026_09_24_dual_capture_phase_random/comparison.json.gz)
retain the capture-manifest digests, IQ digests, deterministic splits,
analysis-inventory source, training-only carrier probes, source hashes,
outcomes, and abstentions.

The focused random-phase, broadband-alignment, and September 24 replay tests
pass 21 tests. Ruff checks pass for the replay, summarizer, and component-owned
tests. The four generated PNGs were inspected after the complete 44-capture
replay. This change adds research tooling and evidence only; it changes no
production analyzer or persisted contract.

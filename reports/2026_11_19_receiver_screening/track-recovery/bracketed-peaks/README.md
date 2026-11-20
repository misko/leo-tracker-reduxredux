# Can a weak peak recover a missing pilot?

On eight complete roof recordings, the capture-era detector reported 2,375 pilots on probes where the wide detector returned no positive. **Only three of those pilots had a matching measured peak anywhere in the wide detector’s exported candidates.** Two had positive margins. The rule using two surrounding detections recovered both of those two, along with ten other peaks. The half-frame control returned zero. Here a match means that the independently measured pilot times agree within two samples and folded carrier frequency agrees within 1 kHz. [Stage figure](bracketed-peaks.png) · [Scoring by recording](bracketed-peaks.csv) · [Availability audit](availability.csv)

| Of the 2,375 capture-positive, wide-negative probes | Probes |
| --- | ---: |
| Wide exported no complete peak | 19 |
| Wide exported peaks, all more than two samples away | 2,327 |
| An epoch matched, but every such peak had the wrong folded CFO | 26 |
| Epoch and CFO matched, with nonpositive margin | 1 |
| Epoch and CFO matched, with positive margin | 2 |

Widening the epoch tolerance from two samples to twenty still gave three matches at the same 1 kHz frequency tolerance. This count bounds what any choice among those stored wide measurements could recover. The capture-era detector is the comparison instrument. Physical truth for individual received pilots is unavailable on this roof. [Follow-up definition](AVAILABILITY.md) · [Input and measurement seal](availability-lock.json)

The selector examines a negative probe between positive detections on the same receiver, channel, RF and sideband. The two anchors must agree in sample-clock drift and folded Doppler. Their interpolated predictions select a unique family of weak, actually measured candidates. The selected timing, frequency, control score and margin all come from the original probe. Decisions use up to 2.6 seconds of look-ahead. On these recordings the longest delay for a new detection was 1.418 s. [Prospective protocol](PROTOCOL.md) · [Selection code](../../../../tools/pipeline_eval/variants/bracketed_peak.py)

Of 104,162 receiver probes, 70,039 originally had no positive. The rule evaluated 31,574 nonempty negatives between compatible anchors and selected twelve. Seven probes was the largest observed queue for an RF lane, with zero capacity evictions. Selection took 0.030–0.066 host CPU seconds per complete recording once its wide output had been decoded. This clock starts after the native GLRT. [Timing and decision counts](selection.csv) · [Edits sealed before the comparison with capture-era](edits.json) · [Seal](selection-lock.json)

On the four preselected position recordings, the rule added seven measured observations and changed no track counts. All four positions were returned. The largest improvement was 6.60 m. Counts within 10% of original no-repair v5 stayed at 1/4 with zero calibration and 2/4 with fitted calibration. [Matched position distributions and RF scores](../bracketed-position/README.md)

An independent checkout reproduced the selected peaks, per-recording scores, availability census and both plot files byte for byte. All non-timing selection fields matched across the sixteen recording and control rows. [Replay checksums](replay-check.json)

Rebuild the stage figure from the sealed tables at the repository root. The numerical commands require the original detector archive and a fresh directory with copies of `PROTOCOL.md` and `AVAILABILITY.md`.

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.bracketed_peak_figure
.venv/bin/python -m tools.pipeline_eval.qualification.bracketed_peak_trial select --out "$WEAK_PEAK_TRIAL"
.venv/bin/python -m tools.pipeline_eval.qualification.bracketed_peak_trial score --out "$WEAK_PEAK_TRIAL"
.venv/bin/python -m tools.pipeline_eval.qualification.bracketed_peak_ceiling --out "$WEAK_PEAK_TRIAL"
```

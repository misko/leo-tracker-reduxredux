# Saved-IQ acquisition stage evidence

[Read the combined PDF](stage-evidence.pdf) · [Evidence and source hashes](manifest.json)

These charts compare physical acquisition and detector stages on sealed measurements. Each page identifies the timed boundary, matched exposures and relevant detector outcome. Cortex-A9 figures use emulation. A companion page covers fractional interpolation.

- [FFT reuse accelerates the full folded acquisition grid](folded-bank.png) · PDF page 1. Full-grid CPU with score and basin parity. [Source evidence](../folded-bank/receipt.json)
- [Exhaustive FFT scores inside the installed capture detector](capture-fft.png) · PDF page 2. Paired saved-IQ CPU and exact detector output. [Source evidence](../capture-fft/summary.json)
- [Thinning lowers detector CPU and misses original positives](thinned-capture.png) · PDF page 3. Detector CPU, coarse basin loss and positive recall. [Source evidence](../thinned-capture/qualification.json)
- [Signed phase rarely narrows the grid on saved IQ](phase-scout.png) · PDF page 4. Real and synthetic allocation rates with paired recorded detector CPU. [Source evidence](../phase-scout/scores.json)
- [Coherent phase narrows planted cases on a replayed grid](phase-scout-coherent.png) · PDF page 5. Recorded and planted eligibility plus supported work avoided. [Source evidence](../phase-scout/scores.json)
- [Sixteen scout centers increase detector CPU](scout-budget.png) · PDF page 6. Coarse geometric coverage, final matches and detector CPU. [Source evidence](../scout-budget/qualification.json)
- [Wider scout radius covers three more archived positives](scout-radius.png) · PDF page 7. Coarse geometric coverage, final matches and detector CPU. [Source evidence](../scout-radius/qualification.json)
- [Ordered fractional interpolation reduces host work](fractional-runtime.png) · PDF page 8. Paired native and emulated CPU for the fractional-stage companion. [Source evidence](../../streamlined/fractional-runtime/qualification.json)

## Reproduce

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.scout_stage_figures
```

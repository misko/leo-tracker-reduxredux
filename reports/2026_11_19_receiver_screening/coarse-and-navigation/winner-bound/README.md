# Bounding the original fractional GLRT winner

The integer-reference bound certified four of 112 terminal refinements on ten authentic stereo visits. A later bound using the exact fractional score certified 25 control spectra and retained the exact winning rank, margin and Doppler. In the matched spectral benchmark, certification alone saved a median **0.008 ms (2.01%)** per receiver attempt versus the same split scorer with pruning disabled. The combined split and certificate saved **0.155 ms (24.04%)** versus the original paired scorer. These measurements start with both fractional correlation arrays already in memory. [Measured stage](stage.pdf) · [Timing pairs](spectrum-timing.csv) · [Protocol](PROTOCOL.md)

## Bound and retained fields

The original producer evaluates a five-point integer timing grid and selects the bracketed fractional delay. It then forms exact and rolled-control complex symbol correlations, maximizes a normalized GLRT spectrum separately for each reference, and subtracts the control maximum from the exact maximum. The earlier certified-GLRT sweep bounded the tap-prefix contribution to the wide detector's coarse peak selection. This study bounds the capture-era original's **final fractional margin**. [Earlier wide-detector study](../../recovery/certified-glrt/) · [Original winner audit](candidate-audit.csv)

For the pre-fractional bound, place the original nearest-integer reference and the Lanczos-shifted reference on the same sample support. Move the interpolation weights and carrier rotation into the reference. The Cauchy–Schwarz inequality bounds each complex symbol-correlation change by the product of the extended received aperture norm and the norm of the reference difference. Let E denote that product for each frame and symbol. The bound uses the nearest-integer correlation array C0, its coherent denominator D0 and peak normalized spectrum S0.

```text
min(1, ((sqrt(S0 × D0) + ||sum_s E||₂)
         / ||sum_s max(|C0| − E, 0)||₂)²)
```

The numerator follows from the triangle inequality over Doppler phase and frames. The denominator is a lower bound on the fractional coherent amplitude. A zero denominator or unmatched frame support falls back to the unit ceiling. The grid and the interpolation support must agree for this bound. The construction is algebraic in real arithmetic. The replay used a 10⁻⁸ absolute score allowance in its decisions and checked the original double-precision outcomes. This is an engineering margin on the observed arithmetic.

The late bound uses the exact fractional peak with zero as a lower bound on the control peak. Parseval gives a tighter control floor from the mean squared FFT magnitude, normalized by its own coherent denominator. Taking the maximum of that floor and 15 fixed control-bin values tightens it further. The split prototype uses the exact-only bound. It offers a certificate only after a candidate has passed the original 0.025 gate, and keeps possible ties. The incumbent is reset for each primary or retry attempt. Removing a strictly losing candidate after a valid incumbent preserves the any-pass retry rule and the compact track input's maximum-margin winner. The omitted complete candidate would still matter to diagnostic archives and to consumers of alternative candidate rows. [Original input and bounds](input-lock.json) · [Evidence seal](evidence-lock.json)

## Original raw candidates

Five valid visits per recording were selected by manifest and visit hash, one per distinct physical RF, from the first 256 recorded indices. DS26-0237 supplies the lower edge and DS29-0082 the upper edge. All original public and projected native fields matched in the raw audit. The 23 physical attempts include three retries and 184 ranked candidates. Of these, 72 were unbracketed and 112 invoked the terminal fractional scorer. An earlier passing incumbent was available for 28 of the latter, 25 of which actually lost by a strict margin. [Per-visit trace and original factors](receipts/) · [Bound summary](bound-summary.csv)

| Bound | Certified DS26-0237 | Certified DS29-0082 | Median upper-bound slack |
|---|---:|---:|---:|
| Integer-reference energy | 4 / 60 | 0 / 52 | 0.99134 |
| Exact fractional peak | 22 / 60 | 3 / 52 | 0.03649 |
| Exact peak minus control mean | 22 / 60 | 3 / 52 | 0.01665 |
| Exact peak minus sampled control floor | 22 / 60 | 3 / 52 | 0.00852 |

The integer energy estimate saturated at one for 77 fractional candidates. One frame-support change took the unit fallback. The audit's pre-fractional energy bound took 3.61 ms median CPU per terminal candidate, including reconstruction of integer correlations and energy. The separately charged original paired spectral step took 0.42 ms per terminal candidate in the same audit. The late bounds acquired no additional certificates beyond the exact-only bound on this small sample. No bound discarded an incumbent challenger.

## Measured spectrum work

On CPU 5, the original paired FFT, the split FFT with all control spectra, and the split FFT with certificates processed the same resident correlation arrays in alternating order. Each physical attempt ran 15 matched repeats. Surviving exact/control spectral scores and peak Doppler were bit-identical to the original. The certificate omitted 25 control spectra across six physical attempts without changing the observed winners or gate decisions. [Spectrum summary](spectrum-summary.csv) · [Sealed timing receipts](receipts/spectrum-lock.json)

| Comparison | Matched repeats | Median CPU saved | Median CPU saved (%) |
|---|---:|---:|---:|
| Split with certificates versus original paired scoring | 345 | 0.155 ms | 24.04 |
| Split with certificates versus unpruned split, all attempts | 345 | 0.008 ms | 2.01 |
| Split with certificates versus unpruned split, attempts with a skip | 90 | 0.121 ms | 18.45 |

Percentages are medians of paired (baseline − candidate) / baseline values, expressed in percent. The paired comparison includes the split execution change. The unpruned split comparison isolates certificate decisions. Acquisition, integer scoring, fractional interpolation, and orbit position are outside this timing boundary. The experiment preserves the observed compact winner input and measures the spectral stage only.

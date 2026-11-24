# A regional envelope cannot certify cheaper installed carrier scouts

The installed 20 ms scout uses **24 complete carrier FFTs per reached scout**. Its eligible-bin list restricts the later ranking walks. Even with advance knowledge of every selected bin, editing that list would remove **zero FFT calls, zero all-bin power operations and zero original full-rate requests**. The actual signed recordings also lack independently calibrated bounds that would authorize a narrower carrier set while preserving the installed factors. [Frozen audit](regional-carrier-scout-protocol.md) · [Measured request evidence and arithmetic counts](measurements/regional-carrier-scout.json)

## The actual expensive boundary

The released Python callback centers the signed interval on `target RF − nominal LNB LO − actual IF center` and passes **center ±800 kHz** into the native two-scan entry. That center is a mixer setting. It supplies no per-device measured LO error or per-transmitter frequency-offset bound. The native entry independently computes each radio's first scout. It builds the signed residual and runs another complete scout if the first confirms. Changing the primary search can also change the cancellation data before the second search. [Native callback and relink identity](receiver-activation-audit.md)

1. The scout mixes, decimates by four and forms two projected modes from fourteen frame planes. Eight forward/inverse lag FFT pairs supply 3,333 timing scores. The twelve retained epoch rows supply no signed carrier shortlist.
2. At each timing row, the scout computes **two complete 4,096-point transforms**, one per mode from 704 input support slots, then sums two powers at **all 4,096 bins**. At 2.5 MS/s the grid is **610.3515625 Hz**. Each row walks the cached **2,621** signed eligible indices twice to choose separated maxima. The circular second-peak gap is 17 bins. Ties retain the earlier native order.
3. The four highest normalized row winners get original native signed lifts and full-rate refinement. The 1.6 MHz admitted interval is narrower than the quarter-rate 2.5 MHz alias period, so each eligible nominee already gets **one** signed lift. The next stages check the original pilot and the separate fractional residual, including rolled control. The **227.273 kHz** GLRT frequency period used for folded downstream matching is a different quantity. It does not shrink the earlier signed candidate search.

The expensive step uses an FFT call on a shared interpolated spectrum. The ranking walks do enumerate candidates. The compiled full path pays 98,304 power accumulations and 62,904 eligible index visits per reached scout, including indices rejected by the second-peak gap. The binary, two native objects, their archived source and their relink receipt agree by SHA-256. [Original full and sparse arithmetic](../single-core-2x/receiver-sparse-carriers.md) · [Carrier and verifier boundaries](selective-carrier-transform.md)

## Signed evidence from the actual 20 ms bank

The refine-bound trace retains the ordered four coarse requests for every original reached scout. It joins the independent readout by visit, radio and original I/Q digest, with identical signed factor bytes and zero mixer center in these panels. The dense slice has 96 lanes and 80 factors. The weak slice has 36 lanes and 58 factors. Both residual scopes come from genuine signed cancellation. Neither complete spectrum nor a calibrated offered-region interval on those same native rows is retained in these receipts. No approximate region was substituted. [Refinement archive](refine-bound.md) · [Independent signed readout](scout-readout.md)

| Saved 20 ms scope | Scouts | Exact coarse requests | Actual full carrier FFTs | Native rank indices visited | Distinct request bins, hindsight only | Contiguous signed hull, hindsight only |
|---|---:|---:|---:|---:|---:|---:|
| Dense, raw | 96 | 384 | 2,304 | 6,038,784 | 347 | 2,615 / 2,621 |
| Dense, residual | 52 | 208 | 1,248 | 3,271,008 | 196 | 2,561 / 2,621 |
| Weak, raw | 36 | 144 | 864 | 2,264,544 | 141 | 2,439 / 2,621 |
| Weak, residual | 36 | 144 | 864 | 2,264,544 | 140 | 2,532 / 2,621 |

The contiguous signed hull keeping every submitted seed on the combined dense raw and residual panel is **−795.898 to +799.561 kHz**, leaving only six original indices outside. The weak hull is **−753.174 to +797.729 kHz**, leaving 79 outside. These bounds protect every submitted request, including losing candidates. Restricting the question to actually confirmed scout winners still spans **−415.649 to +528.564 kHz** on dense and **−307.617 to +552.979 kHz** on weak. A centre-chart Doppler prediction alone does not account for those observed signed search coordinates.

A noncontiguous answer key would keep 487 combined dense bins and 249 weak bins, or three to four with a separate exact mask supplied for each scout. With the original mixer, powers, peak order, 17-bin exclusion and wide refinement bounds fixed, keeping all four original global nominees preserves them. A row with an original global nominee keeps its first peak and any second global peak exactly. A previously losing row cannot produce a candidate above its original first peak. Stable row order preserves ties. This bounds rank indices only. The installed 3,552 dense and 1,728 weak FFT calls all remain, and the static answer-key masks still touch **125 and 114 of the 128 inner FFT residues**. Real scout masks receive no such answer key. Losing a submitted request can also change which replacement enters refinement, detection on empty lanes, or the signed residual.

## Why the model cannot authorize a cut

The detector has no offered-region or catalogue argument. `tools/algo08_scan.py` keys acquisition by the original inventory and constructs the causal orbit reader only for the solver after detections are sealed. A different offered region on identical acquisition therefore cannot change the installed receiver. The ordinary publication CLI requires an offer. An optional receiver-level proposal with missing, invalid, or out-of-domain authority would retain the full signed bank. An omitted true transmitter still contributes to the ordinary detector and exterior test. [Acquisition and solve handoff](../../../tools/algo08_scan.py)

To restrict signed search, let one modeled orbit's Doppler interval be (D) and the summed independent device/transmitter frequency uncertainty be (B). Exact receiver preservation requires an authoritative signed set of (D+B), all supported branches, and retention of any other pilot that can meet the original signal gates. If one interval of (D+B) contains a full alias period (A), then translating by every possible integer (kA) covers the complete real line. Intersecting with the receiver's 1.6 MHz band leaves all 2,621 bins. Shifting the offered region or the interval center cannot change that result. The source supports neither a hard calibrated LO and emitter bound at acquisition nor a rule requiring an installed winning pilot to agree with a catalogued visible orbit. The archived solve's Gaussian allowances are also distinct from hard native cutoffs. The proof demonstrates a fallback condition. It assigns no invented Doppler interval to the saved lanes.

The earlier regional envelope removed many *association edges* after a track contrast canceled LNB, transmitter and alias constants. That cancellation needs multiple accepted measurements of a track. The nearest receiver-side causal orbital study used already-paid anchors with recorded RF and the offered center. It matched **233/694** physical signed factors even with perfect phase provided and issued zero South proposals under the same rule. The earlier data-dependent Fourier enclosure gave ideal savings of 3.2–5.7% of carrier FFT work. Restricting the all-bin power sweep to existing physical eligibility without touching FFTs has already been measured at approximately **20.3 µs/lane** on weak inputs and belongs to a separate exact change. These results support no new regional mask. [Regional post-detection bounds](../single-core-2x/regional-doppler-envelope.md) · [Orbit proposals](anchor-sky.md) · [Earlier FFT enclosure](carrier-fft-bound.md) · [Measured sparse sweep](../single-core-2x/receiver-sparse-carriers.md)

The prior isolated carrier-search clock was about **143 µs per scout**, including all ranking and FFT work on 432 reached scouts. This audit collected no new clock and cannot credit the entire carrier stage to an eligibility change. No waveform, catalogue read, receiver call, solve, or benchmark lease was used.

```sh
python -B -m reports.ALGO08.v3.regional_carrier_scout \
  --bench /tmp/leo-algo08v2-2x-bench \
  --binary /opt/leo-algo08/algo08v3/payload/receiver.so
```

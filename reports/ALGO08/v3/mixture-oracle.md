# Perfect curved identities do not qualify the cold mixture finish

On dense DS30-0008, giving the cold solver the exact v3 owner and signed alias brought full-data RF RMS from **5.38 kHz to about 129 Hz** and made every retained track compatible. The original acceptance still rejected both oracles. The finishes moved **6.27–6.38 km** from their frozen cold positions, the curved-only input fell short of the coverage requirement, and fitted-calibration error remained **0.298–0.337 km** above v3. The diagnostic fit and actual evidence grid cost **16.68–16.81 CPU seconds** with free labels. Obtaining the labels through the measured stock solve raised that cost to **67.58–67.71 CPU seconds**. The only returned result was the checked v3 baseline. [Prespecified protocol](mixture-oracle-protocol.md) · [Numeric summary](measurements/mixture-oracle-summary.json) · [Full receipts](measurements/mixture-oracle.json.gz)

## Evidence missing from the cold model

The original dense v3 publication used **3,574 conditional curved observations and 898 predictive observations** in each calibration arm. All 3,574 curved IDs joined to the original mixture tracks and their owners remained in the offered causal bank. The frozen endpoint's eight satellite candidates and three nearby aliases supplied the exact owner and alias for 3,502. The remaining 72 points belonged to two whole tracks whose satellites fell outside the eight. Allowing every bank satellite restored both tracks. No exact pair was excluded by the alias triple among tracks whose satellites were present, and the original one-owner, one-alias rule admitted every matched point. [Original blind comparison](mixture-position.md)

On 3,479 conditional observations that the blind mixture retained, **2,971 selected the same owner and alias, and 508 selected a different satellite**. Every matching owner used the exact stock alias. Another 95 stock curved observations were absent from the blind retained support. The oracle removes wrong identities without inheriting the fitted stock state. It holds each blind position, receiver parameters and observation samples fixed, then recomputes the phase tangent and hypothesis weights from those samples. It feeds exact masked full-data rows into the original paired optimizer and gates. The RF change isolates a curved-membership problem in this trial. The remaining geographic error cannot be assigned uniquely to the missing predictive rows, since the oracle also retains the cold one-shot fit and phase policy. [Oracle construction](mixture_oracle.py) · [Full-data finish](mixture_finish.py)

## Both calibration arms

The first three rows are diagnostic comparisons. RF RMS uses each row's retained support. The committed blind fit's positions and error are included for context. Reference coordinates entered only after the diagnostics were saved. [Physical reference](../../2026_11_21_ds30_full/reference-audit.json) · [Southern reference](../regional-release/scoring-key.json)

| DS30-0008 fit | RF RMS Hz, `c = 0` / fitted | Horizontal error km, `c = 0` / fitted | Change vs v3 km | Compatible / attempted tracks per arm |
| --- | ---: | ---: | ---: | ---: |
| Blind one-shot | 5,377.044 / 5,393.904 | 1.886 / 1.815 | +0.247 / +0.303 | 79 / 98 |
| Strict slate oracle | 129.043 / 129.022 | 1.879 / 1.849 | +0.240 / +0.337 | 86 / 86 |
| Complete curved oracle | 129.691 / 129.669 | 1.849 / 1.810 | +0.210 / +0.298 | 88 / 88 |
| Checked v3 terminal | 129.703 / 129.663 | 1.639 / 1.512 | — | — |

The unchanged 80% coverage gate requires 3,618 of the 4,522 original curved observations. Strict and complete oracles fell short by 116 and 44. The full data moved both estimates more than 6 km from the cold endpoint, exceeding the 1 km gate. The complete oracle reduced horizontal error by 0.031 and 0.039 km relative to the strict slate. Both fitted arms still exceed the 0.25 km development tolerance. Fitting `c` lowered error by 0.030 and 0.039 km within the strict and complete oracles and lowered their RF RMS by 0.022 Hz in each. Those are separate outcomes on identical within-oracle support.

South containing supplied the same 266 correct owner and alias pairs to both oracles. All 14 tracks passed, giving **0.297 / 0.594 km** error and **6.470 / 6.372 Hz** RMS. The checked v3 terminal gave 0.817 / 1.101 km, with 6.502 / 6.392 Hz RMS. The 0.315 and 0.241 km face clearances still failed the original 1 km requirement. Optimal identities therefore left this earlier rejection intact.

The southern far offer had no returned labels, so the diagnostic transferred the 266 exact pairs from the identical containing packet and verified the common raw authority and causal archive. Both oracles reached the same rejected positions, **53.883 / 53.540 km** error and **599.312 / 590.646 Hz** RMS. Both remained at a face, moved over 23 km from the frozen proposal, and qualified only 152 points across eight of 14 tracks. Full v3 withheld. Transferred labels supplied a counterfactual and never created a terminal return.

## Numerical evidence and cost

The dense and containing fits completed the actual v3 numerical figure evidence and objective grid despite their outer geometry and coverage rejection. Their reconstructed terminal objective deltas were zero in both arms. The omitted fit failed the usual ownership evidence check. Its separate diagnostic grid paid the same numerical objective for all scheduled positions while preserving the rejection. No oracle path encoded PNGs or changed the actual standard terminal result.

| Offer and oracle | One fit CPU s | Actual grid CPU s / points | Evidence outcome | All work with free labels, CPU s | With same-prep stock inference, CPU s |
| --- | ---: | ---: | --- | ---: | ---: |
| Dense strict slate | 0.327 | 3.037 / 179 | Complete diagnostic packet | 16.683 | 67.578 |
| Dense complete curved | 0.317 | 3.189 / 179 | Complete diagnostic packet | 16.811 | 67.705 |
| South containing strict slate | 0.065 | 0.418 / 137 | Complete diagnostic packet | 3.615 | 6.162 |
| South containing complete curved | 0.067 | 0.410 / 137 | Complete diagnostic packet | 3.606 | 6.153 |
| South omitted strict slate | 0.190 | 0.364 / 124 | Grid after ownership evidence rejection | 3.599 | 7.765 |
| South omitted complete curved | 0.189 | 0.363 / 124 | Grid after ownership evidence rejection | 3.597 | 7.763 |

Free-label totals charge original input preparation, the previously measured cold proposal, reconstructed endpoint slates, label matching, one-shot fitting and all attempted numerical evidence. The same-prep stock column adds the original v3 inference and evidence cost. On the omitted case that cost is for verifying the withholding, and the same-packet label transfer additionally took 0.00069 CPU seconds to open. The dense complete diagnostic, which performed both oracle fits and their grids in the same process as v3, took **62.45 CPU seconds and 62.52 elapsed seconds**. Dense individual grid elapsed times were 3.037 and 3.189 seconds. The free-label paths could fit the 24-second compute target in isolation. The blocker is the lack of a publishable decision even with those labels. [Scoped clocks](measurements/mixture-oracle-summary.json)

Full-data RF compatibility detected the blind route's bad matches. The existing movement and coverage gates still rejected the perfectly matched curved route, and postfit scoring confirmed the fitted-arm geographic regression. Allowing two oracle-labeled satellites recovered 72 points while leaving all 898 stock predictive observations outside this model. The trial gives no basis for tuning the cold mixture weights or relaxing the gates.

## Reproduce

Use the installed v3 stack and the already committed cold mixture receipt. `mixture_oracle_trial.py` verifies its digest, recreates the candidate slate from sealed saved detections and obtains aliases through the ordinary selected numerical packet. It checks the actual v3 outputs against the archived arms, ownership and evidence. The scorer reads the frozen references only after the diagnostic files exist. Fourteen component and adjacent tests passed. [Runner](mixture_oracle_trial.py) · [Scorer](mixture_oracle_score.py) · [Owned tests](../../../tests/pipeline_eval/test_algo08v3_mixture_oracle.py)

```sh
mixture_release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
mixture_payload=/opt/leo-algo08/algo08v3/payload
mixture_code="$PWD/reports/ALGO08/v3"
oracle_output=$(mktemp -d /var/tmp/leo-oracle-new.XXXXXXXX)

oracle_lock() {
  flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
    timeout 120s env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 "$@"
}

for oracle_case in south-containing south-far DS30-0008; do
  oracle_lock env PYTHONPATH="$mixture_code:$mixture_payload:$mixture_release/src:$mixture_release" \
    "$mixture_release/venv/bin/python" -BPs "$mixture_code/mixture_oracle_trial.py" "$oracle_case" "$oracle_output"
done

oracle_lock env PYTHONPATH="$mixture_code:$PWD:$PWD/src" python "$mixture_code/mixture_oracle_score.py" \
  "$oracle_output" "$oracle_output/summary.json" "$oracle_output/complete.json.gz"
```

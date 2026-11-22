# Fractional score consumers and exact repair cost

The compact estimator consumes the continuous fractional margin in its radio uncertainty fit. A fixed (10^{-13}) score-only perturbation changed the fitted uncertainty diagnostics on DS30-0016. Both that recording and the southern simulation selected constant variance, and each kept both fits, the scientific grid and path, and all eight PNGs byte for byte. Recomputing stock scores only for the selected factors recovered the original tuples and left **0.6–0.9% native CPU savings** on the physical prefix. [Receipts](receiver-fractional-score-consumers-results.json)

## Which fields consume the score

The detector publishes exact, rolled-control and their difference. Continuation uses the margin to order the two candidates when the frequency votes do not elect the weaker one. Downstream, `frequency_evidence` uses margins to compute candidate weights and signal probability. A single selected factor has weight one. The compact track adapter keeps the selected CFO, observation identity and margin. Track formation reads the time and measured CFO, and the noise fitter reads the margin to estimate `floor + strength / margin` and select it by BIC. Thus a score perturbation can alter a numerical input even after continuation has chosen the same carrier. [Frequency evidence](/opt/leo-algo08/current/src/leo/analysis/glrt_frequency_input.py) · [Track preparation](/opt/leo-algo08/current/src/leo/analysis/localization_v3/tracks.py) · [Noise fit](/opt/leo-algo08/current/src/leo/analysis/localization_v3/noise.py)

The diagnostic applies alternating (+10^{-13}) and (-10^{-13}) to the exact score of every already selected factor in each of two existing detection documents. It recalculates the margin and analysis digest and checks the original factor and strong-margin gates. It leaves measured timing, CFO, RF, and observation identities fixed. The normal track-moment solver and shared-pixel renderer consume these saved documents without opening either I/Q recording. This isolates score sensitivity from changed receiver search.

| Consumer | DS30-0016 physical | Southern simulation |
| --- | --- | --- |
| Detection digest | Changed | Changed |
| Candidate weights, CFO and RF | Identical | Identical |
| Largest signal-probability change | (9.00\times 10^{-13}) | Zero |
| Observations excluding margin and graph tracks | Identical | Identical |
| Radio uncertainty | BIC remained −3.7034 and constant σ remained 117.770701 Hz. The alternative per-observation σ estimates moved by up to (4.43\times 10^{-6}) Hz. | BIC, 40 Hz constant σ and zero strength remained identical. |
| Both fit arms, grid, path, eight PNGs | Identical | Identical |

These two saved completions both select constant variance. A case that uses the fitted per-observation uncertainty can propagate changed margins into the actual objective. [Frame-relative verifier experiment](receiver-fractional-phase.md)

## Recovering the stock score only on selection

A full stock lane replay would reread timing and cancellation even though the approximate verifier already found the same signed factor. The complete ledgers assign **2.438 of 4.631 native CPU seconds** to the 440 eventually selected physical rows, and **2.415 of 6.357 seconds** to the 456 selected southern rows. This makes full-lane replay much more expensive than the measured verifier savings.

The score-only measurement retains the pre-fractional CFO by scan rank and uses the original I/Q already loaded by the native verifier. Immediately after continuation, it passes the selected integer and fractional epoch back to the original stock fractional correlator. This computes the exact and control scores only. It skips the timing scouts, cancellation, integer stencil and residual-frequency median. The final exported CFO is unsuitable as the oscillator input because it includes the residual estimated by the fractional spectrum. The measurement build lives in scratch and leaves the frozen receiver ABI intact.

On the first 128 scheduled DS30-0016 visits, both balanced repeats selected the same 53 factors and restored each full tuple byte for byte. Exact score recovery cost **33.17–33.34 ms**, or about **0.63 ms per selected factor**. Before repair, the experiment saved 38.8–41.3 ms. The complete native timing plus repair saved 5.4–8.1 ms on that prefix. On the small southern slice, restoring all 12 available positive scores for cost measurement took 0.623–0.639 ms per factor. Applying that unit cost to all 456 selected southern rows would cost **0.284–0.292 s** if each required repair. The southern full recording remains an extrapolation.

## Reproduce

Both scripts use the existing frozen detector and saved named inputs. The physical CPU measurement stops after the first 128 scheduled visits. The southern check takes its available positive factors from the first 40 visits. The saved-factor consumer experiment opens no raw I/Q.

```bash
algo08_repo=/tmp/leo-algo08v2-2x
algo08_work=/tmp/leo-algo08v2-2x-bench
algo08_release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
algo08_python=/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python
algo08_reports="$algo08_repo/reports/ALGO08/single-core-2x"

algo08_lock() {
  flock -x "$algo08_work/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src:. timeout 80s "$@"
}

algo08_lock "$algo08_python" "$algo08_reports/fractional_score_repair_trial.py" build
algo08_lock sudo -n -u leo -- env PYTHONPATH=src:. \
  OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  "$algo08_release/venv/bin/python" "$algo08_reports/fractional_score_repair_trial.py" physical
algo08_lock "$algo08_python" "$algo08_reports/fractional_score_repair_trial.py" south
algo08_lock sudo -n -u leo -- env PYTHONPATH="$algo08_repo:$algo08_release/src:$algo08_release" \
  OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  "$algo08_release/venv/bin/python" -BPs "$algo08_reports/fractional_score_consumers.py"
```

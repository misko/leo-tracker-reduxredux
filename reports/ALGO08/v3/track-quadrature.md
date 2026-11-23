# Track-stratified signed joint solver

The 16-knot proposal cut dense cold-ranking and salvage CPU by **10.747 s**. The restored observations failed the original compatibility gates in both calibration arms. With the required installed fallback, the dense solve took **69.340 CPU s**, versus **60.966 s** for installed v3 and **39.045 s** for the full signed joint route. The small southern containing result matched both full controls, and the displaced offer was correctly withheld. The candidate took longer than the full signed route on both southern offers. The frozen proposal failed dense feasibility, so the experiment stopped with the three saved offers. [Numerical summary](measurements/track-quadrature-summary.json) · [Sealed receipts and owner rows](measurements/track-quadrature.json.gz)

## Exact fit and returned results

| Offer and route | Returned decision | CPU (s) | Elapsed (s) | \(c=0\) error (km) | Fitted \(c\) error (km) | \(c=0\) RF RMS (Hz) | Fitted \(c\) RF RMS (Hz) |
|---|---|---:|---:|---:|---:|---:|---:|
| Dense, installed v3 | Complete | 60.966 | 61.015 | 1.639 | 1.512 | 129.703 | 129.663 |
| Dense, full signed | Complete | 39.045 | 39.065 | 1.086 | 1.080 | 128.821 | 128.753 |
| Dense, quadrature | Installed fallback | 69.340 | 69.388 | 1.639 | 1.512 | 129.703 | 129.663 |
| South containing, installed v3 | Complete | 4.620 | 4.620 | 0.817 | 1.101 | 6.502 | 6.392 |
| South containing, full signed | Complete | 3.878 | 3.878 | 0.817 | 1.101 | 6.502 | 6.392 |
| South containing, quadrature | Complete | 4.561 | 4.562 | 0.817 | 1.101 | 6.502 | 6.392 |
| South displaced, installed v3 | Withheld | 6.400 | 6.400 | — | — | — | — |
| South displaced, full signed | Withheld | 6.794 | 6.795 | — | — | — | — |
| South displaced, quadrature | Withheld | 8.151 | 8.187 | — | — | — | — |

Dense retained all 236 Graph tracks and 111 curved tracks in the proposal. Thinning reduced the total Graph track rows from 6,456 to 3,490 and the curved rows from 4,522 to 1,769. The winning compact proposal selected 1,443 curved and 854 predictive rows. Its original-observation fit used 3,667 curved and 960 predictive rows. Both arms failed on the same six curved and three predictive tracks. The bounded repair also would have had to remove a predictive track whose curved calibration support failed. That would remove 10 of 153 tracks, 252 of 3,667 curved observations and 78 of 960 predictive observations. All three rejection shares exceed the frozen 5% ceiling. The route invoked installed v3 before signed qualification or candidate evidence construction.

The rejected dense ordinary fit measured **0.924/0.768 km** in the two arms and **132.163/132.205 Hz** RF RMS. Those coordinates are diagnostics from the exact full-observation attempt. They had 0.163/0.311 km lower position error than the full signed control and 3.342/3.451 Hz higher RF RMS. The returned dense owner maps and both fits matched installed v3 through fallback. The southern containing restoration recovered all 266 owners, including their roles, and completed the same 137-point grid. Each dense return, including fallback, completed the 179-point grid. Returned endpoint objectives replayed exactly. All three displaced routes withheld for `both_receivers_support_far_exterior`; the signed-enabled paths cleared signed qualification before withholding.

| Charged stage CPU (s) | Dense full signed | Dense quadrature | South containing full signed | South containing quadrature | South displaced full signed | South displaced quadrature |
|---|---:|---:|---:|---:|---:|---:|
| Cold ranking and fits | 13.962 | 6.619 | 0.502 | 0.507 | 0.628 | 0.668 |
| Curved salvage | 5.053 | 1.649 | — | — | 0.320 | 0.261 |
| Restore original masks and confidence | — | 2.121 | — | 0.625 | — | 0.641 |
| Signed qualification and fit | 2.345 | — | 0.180 | 0.187 | 0.168 | 0.168 |
| Exterior check | <0.001 | — | <0.001 | <0.001 | 2.911 | 3.324 |
| Standard numerical evidence | 6.511 | — | 0.436 | 0.442 | — | — |
| Installed fallback | — | 51.330 | — | — | — | — |

Dense used 18.010 CPU s through the failed ordinary finish, repair decision and shared preparation. That left 5.990 s under the 24 s screen, less than the matched full-signed numerical evidence alone. Charging the measured full-signed refit and evidence rates to that prefix would total approximately 26.867 CPU s before further exterior work. This counterfactual prices the remaining stages using the matched full route. The direct path rejected its fit, and the installed fallback returned a result. On the southern controls, re-expanding the original tracks took roughly 0.63 s while the compact timings changed little. The displaced offer also spent 0.413 s more probing the exterior.

## Measurement boundary

The trial used the full archived receiver packet and all Graph track identities, with the original curved eligibility, causal sky and search offers. Only the proposal representation changed. Each track contributed its two original endpoints and the farthest remaining interior measurements until it reached 16 distinct knots. Short tracks kept every point. Each knot retained its original measurement and noise scale. Repeating knots or shrinking their noise to mimic multiplicity would change the robust group's likelihood and could allow the alias and trim gates to treat an unmeasured residual as observed. The compressed evidence therefore carries the original per-observation model on fewer rows and serves only as a proposal. [Prespecified protocol](track-quadrature-protocol.md)

The signed joint route ran cold ranking, curved acceptance and salvage, and predictive nomination on the compact tracks. It then restored every original point between the first and last selected knots of each retained curved interval. For a retained predictive track it restored the full track. Discrete satellite owners and aliases survived that transfer. The rebuilt full context recomputed family confidence, phase priors and family weights. The exact two-arm ordinary finish and bounded repair qualified those full-data assignments before the signed refit, standard exterior check and numerical evidence. The installed full solver handled all rejected candidates with the original receiver packet and charged fallback. Neither the original receiver observation set nor the published objective was thinned.

The previous sampled-initial solver also used up to 16 time-spread knots but restored observations during the initial stage and left the entire later v3 schedule unchanged. Local time moments kept full observed residual energy in broad discovery through a polynomial Doppler interpolation. In this trial the reduced representation extends through salvage and predictive nomination, where it can alter the admitted interval or membership before exact evaluation. The contiguous acquisition prefix instead removed all late measurements before Graph. [Sampled-initial results](../single-core-2x/solver-sampled-initial.md) · [Time-moment results](../single-core-2x/solver-track-moments.md) · [Acquisition-prefix results](contiguous-third.md)

Each of the nine timed runs used one pinned low-priority CPU 2 slot and the full installed numerical evidence path from saved detections. Both calibration arms used matched offers and fit budgets. The stock controls were checked against archived arm results, owners, orbit policy, and scientific grid and path digests. The clock includes preparation, phase work, checked fallback, and the original numerical grid when applicable. Waveform acquisition, figure encoding, and positional scoring are outside that boundary. The physical and simulation references were read after the run receipts sealed.

## Reproduce

From this checkout with read access to the released runtime and archived inputs, create a new output directory. The scorer reads the references only after the nine saved runs have completed.

```bash
runner=reports/ALGO08/v3/track_quadrature_trial.py
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
out=$(mktemp -d /var/tmp/track-quadrature.XXXXXXXX)
gauss() {
  flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
    ionice -c2 -n7 nice -n15 taskset -c 2 timeout 110s \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 "$@"
}
for case in DS30-0008 south-containing south-far; do
  for mode in stock signed-full quadrature; do
    gauss env PYTHONPATH="$PWD/reports/ALGO08/v3:$payload:$release/src:$release" \
      "$release/venv/bin/python" -BPs "$runner" run "$case" "$mode" "$out/$case-$mode.json" || exit
  done
done
gauss env PYTHONPATH="$PWD/reports/ALGO08/v3:$PWD:$PWD/src" \
  "$release/venv/bin/python" -BPs "$runner" score "$out" "$out/summary.json" "$out/full.json.gz"
```

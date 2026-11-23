# What the one-third quadratic schedule loses

On the southern containing offer, keeping the complete solver's original labels on the **90 exactly available paid measurements** worsened horizontal error from **0.817 / 1.101 km** to **2.255 / 2.207 km** at zero and fitted `c`. The actual quadratic solver recovered to **1.266 / 1.109 km** by changing membership. Its 64 exactly shared observations kept the same satellite, role and total alias, and both original graph assignments gave the same cold fit on that intersection. The matched physical save improved under thinning, so the geographic effect does not transfer across the two recordings. [Frozen protocol](quadratic-support-protocol.md) · [Numeric results](measurements/quadratic-support.json)

## Measurements, ownership and fixed fits

The reconstructed full and quadratic joint routes reproduce the archived terminals, numerical evidence digests and published owner digests. A matched observation has the same original receiver and counter, integer and fractional epoch, and signed CFO. Total alias combines the graph's original wrap and the solver's discrete track alias. The two replays use the same original supplied offers and causal archives. Geographic references enter only after the saved inference receipts seal. The exact owner and alias assignments used in the controlled refits are available only retrospectively. [Signed witness and binding](quadratic_support_trial.py) · [Original paid results](paid-graph.md)

| Save | Complete owned | Unpaid | Same measured carrier on paid lane | Still owned with exactly same measurement | Lost from paid ownership | New quadratic ownership | Shared satellite / role / alias changes |
|---|---:|---:|---:|---:|---:|---:|---:|
| DS30-0016 | 109 | 75 | 34 | 33 | 1 | 3 | 0 / 0 / 0 |
| South containing | 266 | 176 | 90 | 64 | 26 | 54 | 0 / 0 / 0 |

Every paid complete owner in these two saves still has the same measured carrier on its original lane. The unrecovered paid rows arise after waveform selection. On the south, the 54 additional quadratic owners partly offset the loss of 26 exactly available original owners, but the 176 unpaid observations remain unavailable. The physical replay has 33 shared rows over three arcs. The southern replay has 64 shared rows over ten arcs. [Owner, role and effective alias accounting](measurements/quadratic-support.json)

| Save and cold fixed support | Horizontal error km, zero / fitted `c` | RF RMS Hz, zero / fitted `c` |
|---|---:|---:|
| DS30-0016, all 109 complete owners | 1.619 / 1.644 | 109.345 / 109.454 |
| DS30-0016, 34 paid complete owners | 1.140 / 1.109 | 105.745 / 105.689 |
| DS30-0016, 33 exact shared with complete assignments | 0.550 / 0.541 | 105.885 / 105.892 |
| DS30-0016, same 33 with quadratic assignments | 0.548 / 0.540 | 105.885 / 105.892 |
| DS30-0016, all 36 quadratic owners | 0.226 / 0.181 | 121.437 / 121.336 |
| South, all 266 complete owners | 0.817 / 1.101 | 6.502 / 6.392 |
| South, 90 paid complete owners | 2.255 / 2.207 | 8.202 / 7.382 |
| South, 64 exact shared with either assignment | 2.027 / 0.897 | 7.887 / 7.923 |
| South, all 118 quadratic owners | 1.266 / 1.109 | 6.388 / 6.322 |

Each cold fit starts at the original offered center and zero phase. It re-estimates the original production noise and family confidence on its retained support and uses the same ordinary qualification, signed qualification and numerical checks. The southern fixed fits on all full and all quadratic owners match the corresponding archived blind endpoints and RF exactly. The physical fixed versions move slightly after the rebuild. Its published blind errors are 1.644 / 1.661 km for complete and 0.247 / 0.182 km for quadratic. The 33-row physical intersection moves by about 1–2 m between original graph assignments. The southern intersection is identical. These controlled results attribute changes to observation availability and which measured arcs reach the final solve, with little or zero contribution from a switch of satellite, role or effective alias on shared rows. [Paired control fits](measurements/quadratic-support.json)

## Geometry, clock and calibration

The nominal tangent uses the offered center, zero phase, original hardware times and 150 Hz independent measurement noise. It profiles the original receiver, family, arc and RF nuisance columns in both calibration arms. Freeing a common timestamp derivative measures how much nominal horizontal information depends on the recorded clock. Freeing the causal family phase and orbital-shape coefficients gives a separate conditioning diagnostic. These matrices describe the local design under a nominal likelihood, and supply no calibrated absolute error bars. [Nominal geometry code](quadratic_support.py)

| Save and support | Soft-direction information, fixed clock, zero / fitted `c`, km⁻² | Soft-direction information, free clock, zero / fitted `c`, km⁻² |
|---|---:|---:|
| DS30-0016 complete | 0.01750 / 0.01709 | 0.002405 / 0.002403 |
| DS30-0016 quadratic | 0.01698 / 0.01653 | 0.001488 / 0.001487 |
| South complete | 0.12118 / 0.11844 | 0.11823 / 0.11483 |
| South paid complete owners | 0.10094 / 0.09996 | 0.09814 / 0.09670 |
| South quadratic | 0.09329 / 0.08576 | 0.07779 / 0.06999 |
| South exact intersection | 0.03387 / 0.02404 | 0.03268 / 0.02343 |

At zero `c`, the southern quadratic support has 77% of full soft-direction information with the recorded clock, and 66% if a common timing shift is free. Both full and paid nominal position designs become nearly singular when all family orbit coefficients float without priors. This shows dependence on causal orbit regularization. The region-center tangent predicts that applying the southern quadratic fitted coefficient would move position 0.533 km east and 0.087 km south. The actual paired nonlinear endpoint moves 0.185 km east and 0.111 km north. The local calibration tradeoff is substantial, but it does not account for the observed displacement. [Conditioning and calibration slopes](measurements/quadratic-support.json)

The conditional validation used only genuinely paid observations. It excluded each chosen held observation from the objective, weighting and training gates, with a common nominal noise scale. The topology and exact aliases came from the fixed published support. The south supplied six curved fragments with six training points and two held points each, leaving three quadratic residual degrees of freedom per training fragment. Training RMS changed from 6.679 to 6.649 Hz when `c` floated. Held RMS changed from **7.375 to 7.402 Hz**. Physical validation used two fragments, 20 training and nine held points, and gave **105.995 versus 108.113 Hz** on held data. These small conditional folds provide no improvement to justify a new calibration or orbit/clock penalty. No such penalty was tuned or served as a candidate. [Held RF by track](measurements/quadratic-support.json)

## Additional lanes available to a paid-only proposal

A deterministic metadata-only nomination groups original antenna opportunities by receiver, channel and exact RF. It can propose an unpaid lane after two strictly preceding solved paid observations of one satellite on that lane within eight seconds. It uses the actual blind quadratic terminal's paid owner labels. The complete owners and unpurchased waveforms enter only after proposal construction for the coverage census. The exported slots include original visit, receiver and exact counter, channel, RF, proposed satellite and the two witness anchor IDs. They are suitable inputs for a separate saved-waveform test. [Proposal rule](quadratic_support.py) · [Complete slot receipt and hashes](measurements/quadratic-support-slots.json)

| Save | Proposed antenna lanes | Stereo visits | Unpaid complete owners with correct family proposed | Unpaid complete owners in a family absent from sparse fit | Archived original native CPU on proposed lanes |
|---|---:|---:|---:|---:|---:|
| DS30-0016 | 129 | 129 | 69 / 75 | 0 | 0.512 s |
| South | 102 | 51 | 60 / 176 | 50 | 0.518 s |

On the physical save, NORAD 63510 on channel 3 from 24–32 s and NORAD 64015 on channel 1 from 8–16 s each have nine reachable missing points at the first antenna. Southern examples include NORAD 56395 on channel 6 at 264–272 and 288–296 s, NORAD 65444 on channel 3 at 72–80 s, and NORAD 66147 on channel 1 at 224–232 s, all with anchors on both antennas. Two southern full-support families, NORAD 65235 and 69658, never appear in the paid quadratic solve. They contribute 24 and 26 unpaid owners and need an independent discovery mechanism to enter this proposal set. The clocks charge only the original archived native callbacks on those lanes. Signed waveform recovery, reads or retention of earlier I/Q, and another solver invocation remain unmeasured. [Exact epoch census and archived callback charges](measurements/quadratic-support.json)

## Reproduction

Run `quadratic_support_trial.py` with case `south-containing` or `DS30-0016` and a fresh case JSON path. Use the pinned ALGO08v3 payload with the enclosing checkout on `PYTHONPATH` for archived ledger bindings. Then run `quadratic_support_score.py "$out" "$out/score.json" --slots-out "$out/slots.json"` under the same lock with the checkout and its `src` on `PYTHONPATH`. This experiment uses saved data from two containing offers. The archived far outcome is reported in the original quadratic experiment. [Owned tests](../../../tests/pipeline_eval/test_quadratic_support.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
code="$PWD/reports/ALGO08/v3"
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$code:$payload:$release/src:$release:$PWD" \
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs "$code/quadratic_support_trial.py" \
  "$case" "$out/$case.json"
```

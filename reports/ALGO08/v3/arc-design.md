# Complete Doppler arcs under a one-third acquisition budget

On dense DS30-0008, a one-third antenna-lane budget cannot preserve 90% of full nominal horizontal information under the frozen complete-family and original donor-history rules. The cost-aware design retains **68.62%** in its weaker direction and calibration arm. An optimistic fractional relaxation caps every complete-family design at **85.42%** under the same budget. On the smaller southern containing offer, the cheapest design to clear 90% buys all seven families for **322 of 2,400 lanes** and reproduces the two installed-v3 positions. The same frozen observations on the omitted offer stopped at the ordinary fit gate before exterior qualification. [Frozen protocol](arc-design-protocol.md) · [Saved evidence](measurements/arc-design.json)

## What the selector knows

The sealed v3 owner and role maps agree across calibration arms in both containing cases. Each experimental block keeps every owned Doppler arc of one NORAD, including all its original receivers, RFs, and accepted intervals. Its price is the union of the retained antenna opportunities and each retained point's original 12 preceding same-receiver/channel/RF opportunities within eight seconds. The current waveform was read from saved admitted factors. The cost assumes the original continuation opportunities need full processing and counts each overlapping lane once. A real detector would need to supply the same signals and ranks before the fixed-owner diagnostic could use them. [Stable owner and history reconstruction](arc_design_trial.py) · [Full donor-window check](owner-union.md)

The geometry uses only causal TLEs, original observation times and RFs, and zero phase at the offered region center. Measured CFO values are zeroed for design. Under independent nominal 150 Hz noise, the selector profiles the v3 receiver-band baselines, receiver drift and smooth terms, orbital phase and shape terms, arc constants, and one unrestricted shared clock. The fitted-`c` arm also profiles its RF-dependent column using the v3 scale. It compares the smaller of the two arms' worst-direction information fractions relative to each arm's complete-set information matrix. Coverage requires both receivers, both RF halves, and all occupied recording thirds. This is a local Gaussian calculation. In particular, the dense tangent treats predictive arcs as Gaussian curves, and leaves robust effects, orbit bias, nonlinear admission and misassignment outside the nominal metric. [Geometry and search implementation](arc_design.py) · [Earlier position-information study](../../2026_09_20_track_position_information.md) · [Full-track quadrature study](track-quadrature.md)

The southern selector enumerates all subsets of its seven blocks. Dense uses a deterministic gain-per-marginal-lane search. To upper-bound the latter independently of the search, the relaxation apportions overlapping lanes fractionally among blocks. Any set's apportioned price is at most its actual union cost. The bound then permits fractional purchases and fixes each shared nuisance fit to its full-data optimum for each of 16 whitened directions per arm. The resulting one-dimensional fractional optimization is an upper bound for that direction, and the minimum across directions and arms upper-bounds the design criterion. It grants exact satellite and alias labels and ignores the mandatory strata. [Fractional relaxation](arc_design.py) · [Exact-search and relaxation tests](../../../tests/pipeline_eval/test_arc_design.py)

## Geometry and cost frontier

| Recording | Antenna-lane cap | Best feasible paid lanes | Worst-direction information, zero / fitted `c` | Optimistic upper bound on weaker arm |
|---|---:|---:|---:|---:|
| DS30-0008 | 1,127 of 13,530 | 1,092 | 6.79% / 6.64% | 55.07% |
| DS30-0008 | 2,255 of 13,530 | 2,186 | 20.08% / 20.15% | 71.71% |
| DS30-0008 | 4,510 of 13,530 | 4,489 | 68.62% / 68.84% | **85.42%** |
| South containing | 200 of 2,400 | 184 | 49.45% / 44.22% | 89.28% |
| South containing | 400 of 2,400 | 322 | 100% / 100% | 100% |
| South containing | 800 of 2,400 | 322 | 100% / 100% | 100% |

The 15-family dense design keeps 1,931 of 4,472 owned observations, with 2,558 additional lanes paid for original history. Its 4,489 antenna lanes span 3,123 of 6,765 stereo visits, or 46.2%, so the lane result gives a favorable budget for any receiver that also pays a shared cost per visit. All 26 original families would require 10,218 lanes. The 200-lane southern design reaches 44.22% in its weaker arm from four blocks. The seven-family southern design is the exact cheapest way to reach 90% and buys 161 stereo visits. Its savings come from paying only the owners and their history. Dropping any complete southern family misses the frozen information target. [Frontiers, RF and receiver costs](measurements/arc-design.json)

The dense archive has 59 predictive arcs without exact discrete aliases. The one-third design includes 17 of them across nine families, covering 270 of its 1,931 observations. Under complete-family selection, the entire witness-complete pool is six families and 877 paid lanes. That pool satisfies all strata and fits under the cap, so its **2.785%** weaker-arm fraction is the exact ceiling within the available witnesses. Both the all-label information bound and the omitted southern fit gate end the dense branch before a nonlinear fit. The result leaves other block definitions, cheaper continuation witnesses, new calibrated receiver designs, and dense position accuracy untested. [Selected aliases and source pins](measurements/arc-design.json) · [Prior predictive-alias limitation](survey-owner-diagnostic.md)

## Cold southern check

| Offer and solver | Horizontal error km, zero / fitted `c` | RF RMS Hz, zero / fitted `c` | Decision |
|---|---:|---:|---|
| Containing, installed v3 | 0.817 / 1.101 | 6.502 / 6.392 | Returned |
| Containing, cold fixed owners | 0.817 / 1.101 | 6.502 / 6.392 | Returned |
| Omitted, installed v3 | — | — | Withheld after exterior evidence |
| Omitted, cold fixed owners | — | — | Rejected at ordinary track gate |

The cold containing fit initialized the endpoint at the offered center and phase at zero. It rebuilt noise, used the original conditional and signed checks, returned both installed owner digests, and completed 137 numerical grid points with zero objective replay difference. Enabling fitted `c` on the same 266 observations lowered RF RMS by 0.110 Hz and increased horizontal error by 285 m. The diagnostic fit through evidence took 1.336 CPU seconds after geometry and original membership reconstruction, and 3.427 seconds including that work. [Paired fits and evidence](measurements/arc-design.json)

The omitted fit reused the same 266 observations and 322 paid lanes. With the displaced offer's own center and causal evidence, both ordinary fits stopped at the ((-12.5,-12.5)) km corner and failed four curved-track gates per arm. RF RMS was 904.4 and 906.1 Hz at that rejected diagnostic point. The original gate stopped both fits before signed update and exterior evidence. Earlier work on the same owner-only waveform observed positive exterior withholding from a fresh installed-v3 search. This fixed-owner route therefore cannot establish the omitted offer's original terminal decision. [Ordinary gate and offer binding](measurements/arc-design.json) · [Original owner-only search](owner-union.md)

Three saved invocations ran under the exclusive low-priority Gauss lock. Dense took 3.899 CPU seconds through the donor and nominal geometry frontier. These clocks establish the diagnostic cost. No raw receiver acquisition or deployment speed was measured.

## Reproduction

Use the pinned release below. Run `south-containing` first. Run `south-far` with `--selection-path "$out/south-containing.json"`, then run `DS30-0008` in frontier-only mode. Score the three receipts under the same lock with the repository and its `src` on `PYTHONPATH` using `arc_design_score.py "$out" "$out/score.json"`. Seven focused tests passed, including the installed donor-opportunity logic tests. [Owned tests](../../../tests/pipeline_eval/test_arc_design.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
code="$PWD/reports/ALGO08/v3"
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$code:$payload:$release/src:$release" \
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs "$code/arc_design_trial.py" \
  "$case" "$out/$case.json"
```

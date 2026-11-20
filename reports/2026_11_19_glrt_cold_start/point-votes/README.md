# GLRT carrier and frame-phase pair votes

The receiver reads the full archived GLRT candidate output, acquisition clock and causal TLE. It pairs strong peaks from the same receiver and RF channel from 0.9 to 2.4 seconds apart. Initial pairs come from nearby probe times and physical slope bounds. The global arm starts at 3,600 Earth-wide sample points and refines eight spatially separated basins. The supplied-tile comparison searches within 12.5 km of the original center. Position truth is read only by the scorer after both submissions are sealed. [Protocol](PROTOCOL.md)

## Recorded results

Both modes withheld all six attempts. Worldwide forced guesses were 3,986 to 17,982 km from the independent reference. Giving the original tile center reduced forced error to 8.29 to 20.34 km. The center alone was about 8.19 km from the reference on every recording. Reported seconds start with reading and verifying the archived GLRT and TLE bytes and end at the position decision. Historical v5 seconds are stored reference times with their original processing boundary.

| Recording | Global forced km | Global wall s | Supplied-tile forced km | Supplied-tile wall s | Original v5 zero-c km | Historical v5 wall s |
|---|---:|---:|---:|---:|---:|---:|
| DS26-0036 | 17,982 | 118.8 | 8.29 | 18.8 | 1.28 | 297.8 |
| DS26-0122 | 3,986 | 113.5 | 18.89 | 13.7 | 0.75 | 730.4 |
| DS26-0237 | 11,117 | 101.7 | 20.34 | 13.9 | 0.36 | 237.2 |
| DS29-0082 | 11,069 | 94.5 | 14.49 | 15.1 | 0.57 | 162.4 |
| DS29-0174 | 7,424 | 93.6 | 20.03 | 11.5 | 0.89 | 211.7 |
| DS29-0247 | 10,014 | 89.0 | 8.38 | 16.6 | 1.32 | 331.7 |

The receiver read 9,736 to 13,542 probe rows per recording and selected 150 pairs, with 113 for training and 37 for validation. Global held-out votes reached 0.76 to 0.84 on the favored basins. Their leads over the best separated alternative ranged from −0.055 to +0.005, below the 0.07 gate across all six cases. Independent per-pair satellite assignments let geographically distant sites explain many of the same measurements. The sample-clock nuisance was zero in each worldwide best guess, which gives no evidence for a well identified clock correction.

Before opening position truth, the prediction audit found that all refined DS26-0237 tile finalists had converged within the required 6 km separation. The initial gate assigned a zero vote to the absent alternative and published the coordinate. The corrected gate requires a measured spatial alternative and withholds that case. It reuses the saved finalist locations and validation votes. The scores, search, forced coordinates and recorded timings are unchanged. The audit preserves the initial seal and identifies the single changed decision. [Before-guard lock](before-spatial-guard/prediction-lock.json) · [Eligibility audit](spatial-guard-audit.json) · [Final lock](prediction-lock.json)

[Worldwide predictions](global.jsonl.gz) · [Supplied-tile predictions](matched-tile.jsonl.gz) · [Official scores](scores.json)

## Physical scoring

For a candidate site and satellite, let range be \(\rho(t)\) and range rate be \(\dot\rho(t)\). The model compares the observed two-peak differences with

\[
s_f = -\frac{f_\mathrm{RF}}{c_\mathrm{light}}\frac{\dot\rho(t_1)-\dot\rho(t_0)}{t_1-t_0},
\qquad
s_\mathrm{epoch} = \frac{F_s}{c_\mathrm{light}}\frac{\rho(t_1)-\rho(t_0)}{t_1-t_0} + b.
\]

Absolute sample counters and fractional epoch estimates supply the frame-phase change. Carrier and frame-phase differences wrap at their respective periods. The receiver scores a Gaussian kernel in the two slope errors, with widths of 450 Hz/s and 18 samples/s. It takes each pair's strongest visible-satellite vote and searches a common sample-clock slope \(b\) in 16 samples/s increments. It assigns satellites independently to each pair. Every fourth interval is reserved for validation. Adjacent training and validation pairs can still observe the same ongoing signal.

The calibration terms from the earlier receiver are additive carrier offsets at fixed RF. Each pair is formed at a single recorded RF, so subtraction removes the learned RF coefficient exactly from the equations. The `c0` and `fitted_c` rows therefore share the same calculation, selection budget and result. The vote is dimensionless. The scorer measures distance error separately.

The planted geometry test recovered an arbitrary location to within 15 km from global seeds and recovered the planted sample-clock drift. The empty control withheld with no forced fix. The tests also verify the carrier difference under added lane and RF-dependent offsets and the required spatial alternative. The planted test uses exact supplied satellite states to check geometry and the decision boundary.

## Reproduce

```sh
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  taskset -c 8-11 .venv/bin/python -B -m tools.pipeline_eval.qualification.point_votes_replay \
  --out reports/2026_11_19_glrt_cold_start/point-votes
.venv/bin/python -m tools.pipeline_eval.qualification.point_votes_replay --score-sealed \
  --out reports/2026_11_19_glrt_cold_start/point-votes
```

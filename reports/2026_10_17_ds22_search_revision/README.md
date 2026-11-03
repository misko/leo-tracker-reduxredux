# Per-scan receiver/band offsets and small LNB drift

All five DSX01 scans completed a matched zero / tight / baseline drift sweep,
each with c=0 and fitted c. These are fixed-site candidate compatibility fits
at the supplied GPS (37.849061591561885, -122.48574968092912), not independent
satellite identities or geographic estimates. Original Graph memberships,
trimmed merged groups, causal orbit candidates and gates remain fixed.

## Physical model and conventions

For original observation i in scan s and receiver/band group g:

`y_i + k_fragment * P = (RF_i / 11.5 GHz) * Doppler_sat(t_i, site) + a_sg + d_sg * (t_i - 150 s) + c_s * (RF_i/GHz - 11.5) + b_component + noise_i`.

There are four scan-local offsets a and four scan-local linear drifts d: RX1
low, RX1 high, RX2 low, RX2 high. This includes different drift for each band.
P=227272.727... native Hz. Aliases are integers per original fragment;
b is one Gaussian constant (sigma=1000 native Hz) per whole merged component,
with no component slope. It represents a declared carrier-bias hypothesis.
The c=0 and fitted-c arms have identical points, candidates, other priors and
160-seed calibration budgets. c has units Hz/GHz here.

Only individually measured-curved fragments calibrate hardware: duration at
least 20 s and RMS departure from their best affine fit at least 250 Hz.
Linear fragments can be associated after calibration. Passing residual tests
is a compatibility condition; it cannot authenticate a satellite identity.
The tests check mean, slope, quadratic improvement, steps and lag-one structure.

Offsets below are modeled **measured differences** at t=150 s, with the RF
coefficient referenced to 11.5 GHz, modulo P. To correct RX2 into RX1's frame,
subtract the RX2-minus-RX1 contrast and its time-dependent drift difference.
At actual RF, also apply the declared RF-dependent term. Cross-band physical
Doppler must be RF-scaled; an additive shift alone is insufficient.

## Small-drift sensitivity

Zero fixes all four drifts to 0. Tight uses a Gaussian prior sigma=0.5 Hz/s
and hard bounds +/-1 Hz/s. Baseline uses sigma=2 Hz/s and bounds +/-5 Hz/s.
These are sensitivity hypotheses, not measured hardware specifications.

![Drift sensitivity](receiver-band-drift.png)

The c=0 drift estimates below are in Hz/s. Asterisks indicate active hard
bounds. “Unsupported” means no curved component passed the calibration gate
for that group at the final fit; its stored numeric value is not a measurement.

| Scan | Policy | RX1 low | RX1 high | RX2 low | RX2 high |
| --- | --- | --- | --- | --- | --- |
| DSX01-S01 | zero | -0.000 | 0.000 | -0.000 | -0.000 |
| DSX01-S01 | tight | 0.763 | 1.000* | -1.000* | -0.936 |
| DSX01-S01 | baseline | 3.650 | 4.104 | 1.184 | -5.000* |
| DSX01-S02 | zero | 0.000 | -0.000 | -0.000 | unsupported |
| DSX01-S02 | tight | 1.000* | -0.973 | -1.000* | unsupported |
| DSX01-S02 | baseline | 5.000* | 2.103 | -0.964 | unsupported |
| DSX01-S03 | zero | -0.000 | 0.000 | 0.000 | 0.000 |
| DSX01-S03 | tight | 0.136 | 1.000* | 1.000* | -0.295 |
| DSX01-S03 | baseline | 2.110 | 4.042 | -0.853 | -4.152 |
| DSX01-S04 | zero | 0.000 | -0.000 | -0.000 | 0.000 |
| DSX01-S04 | tight | 0.661 | 0.829 | -1.000* | 1.000* |
| DSX01-S04 | baseline | 4.723 | 4.489 | 0.143 | 5.000* |
| DSX01-S05 | zero | 0.000 | -0.000 | -0.000 | -0.000 |
| DSX01-S05 | tight | 0.770 | 0.776 | -1.000* | -1.000* |
| DSX01-S05 | baseline | 0.802 | 0.627 | -5.000* | -5.000* |

## Receiver and band offsets

The tight, c=0 contrasts below are native Hz at 150 s. Policy stability is not a confidence interval.

| Scan | RX2−RX1 low | RX2−RX1 high | RX1 high−low | RX2 high−low |
| --- | --- | --- | --- | --- |
| DSX01-S01 | -7403.0 | 49357.0 | -18133.9 | 38626.2 |
| DSX01-S02 | -29829.8 | unsupported | -16372.2 | unsupported |
| DSX01-S03 | -31333.3 | -15373.0 | -15983.1 | -22.7 |
| DSX01-S04 | -27380.8 | -56964.1 | -16778.7 | -46362.0 |
| DSX01-S05 | -25259.0 | 31721.2 | -16844.7 | 40135.5 |

![Offset sensitivity](receiver-band-offsets.png)

## Candidate association coverage

The denominator is the 18,338 original points assigned to Graph tracks. The earlier all-winning-GLRT denominator is 20,084. These hard-merged candidate results do not replace the safer fragment/consolidation results in the preceding report.

| Policy | Graph points | Points c=0 | Points fitted c | Components c=0 | Components fitted c |
| --- | --- | --- | --- | --- | --- |
| zero | 18338 | 1615 | 1992 | 76 | 85 |
| tight | 18338 | 1787 | 2079 | 80 | 85 |
| baseline | 18338 | 1658 | 2081 | 74 | 80 |

![Association sensitivity](drift-association.png)

| Scan | Policy | Graph points | Points c=0 | Points fitted c | Components c=0 | Components fitted c |
| --- | --- | --- | --- | --- | --- | --- |
| DSX01-S01 | zero | 4487 | 158 | 158 | 7 | 7 |
| DSX01-S01 | tight | 4487 | 180 | 158 | 8 | 7 |
| DSX01-S01 | baseline | 4487 | 266 | 266 | 11 | 11 |
| DSX01-S02 | zero | 3185 | 408 | 475 | 19 | 21 |
| DSX01-S02 | tight | 3185 | 406 | 539 | 19 | 22 |
| DSX01-S02 | baseline | 3185 | 381 | 458 | 16 | 18 |
| DSX01-S03 | zero | 3609 | 99 | 310 | 7 | 11 |
| DSX01-S03 | tight | 3609 | 271 | 281 | 11 | 9 |
| DSX01-S03 | baseline | 3609 | 124 | 192 | 5 | 7 |
| DSX01-S04 | zero | 3348 | 161 | 282 | 9 | 12 |
| DSX01-S04 | tight | 3348 | 141 | 282 | 8 | 12 |
| DSX01-S04 | baseline | 3348 | 61 | 172 | 5 | 7 |
| DSX01-S05 | zero | 3709 | 789 | 767 | 34 | 34 |
| DSX01-S05 | tight | 3709 | 789 | 819 | 34 | 35 |
| DSX01-S05 | baseline | 3709 | 826 | 993 | 37 | 37 |

## Confidence and geographic evidence

The drift estimates depend on the prior and frequently reach bounds. Scan 2 RX2 high has no qualified curved support. Scan 4 RX2 high has only one qualified curved component in the c=0 fits. Neither should calibrate cross-receiver/band joins without more evidence. Stable offsets across drift policies are encouraging, but identity/alias ambiguity and prior dependence remain. No bootstrap confidence interval or authenticated identity probability is claimed.

The earlier failed DS22 endpoint scored worse than the supplied site when both were evaluated on identical full observations: 1,330,415,647 versus 748,858,313 (c=0, 1000-Hz component bias). Both compressed observations and a four-seed calibration retain that correct-site preference. The supplied site was used only for diagnosis; no state from that diagnostic seeds the new uniform regional search.

The revised search uses an 81-point, 50-km regional grid, three separated basins and all original Graph observations throughout. Eight finalists use the full 160-seed calibration. Cached prepared orbital geometry agrees with the old implementation to about 1e-8 Hz and speeds up the measured geometry queries by about 4–5 times. This is a bounded regional experiment, not a global optimum certificate.

| Case | Search | Arm | Position error km | Geographic queries | Frequency score |
| --- | --- | --- | --- | --- | --- |
| DS22-001 | fragments | c=0 | 11.987 | 216 | 586484235 |
| DS22-001 | fragments | fitted c | 11.987 | 216 | 586503484 |
| DS22-001 | pilots | c=0 | 11.919 | 219 | 590210073 |
| DS22-001 | pilots | fitted c | 11.919 | 221 | 589508482 |
| DSX01-S01 | pilots_resumed | c=0 | 5.780 | 219 | 717352795 |
| DSX01-S01 | pilots_resumed | fitted c | 6.085 | 223 | 716953319 |

![Position search diagnostics](position-search.png)



Frequency-score improvement and association coverage do not demonstrate better localization. Position errors are computed only after each fit is frozen. The 0.5-km goal remains active and unachieved. Any incomplete or timed-out runs remain in their original directories; a resumed run replays verified cached objective scores with unchanged search policy and budgets.

## Reproducibility

`drift_sensitivity/*/protocol.json` binds causal banks, observations, source hashes, policies and seed budgets. Each arm retains component candidates, residual RMS and qualified curved support. `drift-association.csv` is the machine-readable comparison. `diagnosis/` retains all controlled search diagnostics; `geometry_parity.json` retains numerical parity and timing. Search traces, frozen endpoints and separate evaluation receipts are under `pilots/`, `fragments/` and any `pilots_resumed/`. The earlier sealed report remains unchanged.

The calibration budget requests 160 generated seeds plus the initial state (four plus the initial state during geographic discovery); feasible seed counts can be smaller. Both initial DSX01 position processes exceeded eight-minute limits. Both resumed fits sealed successfully; a post-fit distance-call argument error was repaired from unchanged frozen fits. `execution-history.json` records the failures and recovery. The archived original footer reproduces its recorded digest. `CHECKPOINT.md` records remaining work and the new read-only adaptive-input availability probe.

# Frozen-model comparison

Each joint entry is ONE group estimate, not three independent observations. Errors are km; no model is selected using these errors.

| Group | Role | Independent λ=0 mean / max | Joint λ=0 | Joint λ=100 | Joint λ=1000 | Joint λ=10000 | Hard shared |
|---|---|---:|---:|---:|---:|---:|---:|
| D0850 | diagnostic | 49.58 / 123.53 | 5.00 | 5.00 | 6.72 | 6.72 | 6.72 |
| D1250 | diagnostic | 239.16 / 706.76 | 3.99 | 3.99 | 3.99 | 3.99 | 13.54 |
| G0200 | validation | 6.40 / 9.41 | 5.79 | 5.79 | 5.79 | 5.79 | 5.79 |
| G0300 | test | 7.72 / 10.85 | 6.53 | 6.53 | 6.53 | 10.85 | 10.85 |

## Clock-only control: independent scan locations

Same group-wide candidate inventory; each scan selects its own site on that model's penalized training objective. Entries are mean / maximum error km, not joint group estimates.

| Group | λ=0 | λ=100 | λ=1000 | λ=10000 | Hard shared |
|---|---:|---:|---:|---:|---:|
| D0850 | 49.58 / 123.53 | 49.58 / 123.53 | 49.58 / 123.53 | 49.58 / 123.53 | 51.38 / 128.93 |
| D1250 | 239.16 / 706.76 | 239.16 / 706.76 | 239.16 / 706.76 | 241.43 / 706.76 | 11.27 / 13.54 |
| G0200 | 6.40 / 9.41 | 6.40 / 9.41 | 6.40 / 9.41 | 5.79 / 5.79 | 7.00 / 9.41 |
| G0300 | 7.72 / 10.85 | 7.72 / 10.85 | 7.72 / 10.85 | 7.72 / 10.85 | 7.48 / 10.85 |

## Competing hypotheses and weighting sensitivity

Objective gaps below compare only hypotheses within one fixed model; they are not calibrated probabilities or confidence thresholds.

| Group | Model | Best objective | Runner-up gap | Runner-up separation km | Duration-pooled winner error km |
|---|---|---:|---:|---:|---:|
| D0850 | lambda_0 | 292.081 | 0.768 | 5.48 | 5.00 |
| D0850 | lambda_100 | 292.665 | 0.664 | 5.48 | 5.00 |
| D0850 | lambda_1000 | 296.735 | 0.322 | 5.48 | 6.72 |
| D0850 | lambda_10000 | 315.034 | 2.865 | 5.48 | 6.72 |
| D0850 | hard_shared | 344.795 | 12.025 | 5.48 | 6.72 |
| D1250 | lambda_0 | 173.960 | 2.502 | 9.50 | 13.44 |
| D1250 | lambda_100 | 175.057 | 2.717 | 9.50 | 13.44 |
| D1250 | lambda_1000 | 183.810 | 4.288 | 9.50 | 3.99 |
| D1250 | lambda_10000 | 235.169 | 11.207 | 9.50 | 3.99 |
| D1250 | hard_shared | 348.610 | 5.747 | 10.30 | 13.54 |
| G0200 | lambda_0 | 184.443 | 0.940 | 3.52 | 3.99 |
| G0200 | lambda_100 | 186.064 | 1.169 | 3.52 | 3.99 |
| G0200 | lambda_1000 | 198.082 | 1.486 | 3.52 | 3.99 |
| G0200 | lambda_10000 | 245.776 | 6.221 | 3.52 | 5.79 |
| G0200 | hard_shared | 321.979 | 15.786 | 3.52 | 5.79 |
| G0300 | lambda_0 | 107.934 | 1.562 | 5.48 | 6.53 |
| G0300 | lambda_100 | 109.791 | 1.628 | 5.48 | 6.53 |
| G0300 | lambda_1000 | 122.024 | 2.227 | 5.48 | 6.53 |
| G0300 | lambda_10000 | 179.523 | 1.764 | 5.48 | 6.53 |
| G0300 | hard_shared | 277.806 | 4.343 | 5.48 | 5.79 |

Production parity: 24 published-site checks; maximum absolute difference 5.51e-12 Hz.

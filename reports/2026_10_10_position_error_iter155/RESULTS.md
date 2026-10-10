# Original B7 conditional-mode parity and cost

All twelve consumed members and both original final c arms are retained. This measures numerical callback parity and cost, not position accuracy, integration accuracy or a c-effect.

![Callback cost and normalized numerical discrepancies](parity_cost.png)

| Dataset | Members | Matched models | Fitted passed / failed | Zero passed / failed |
|---|---:|---:|---:|---:|
| DS16 | 4 | 4 | 4 / 0 | 4 / 0 |
| DS17 | 4 | 4 | 4 / 0 | 4 / 0 |
| DS18 | 4 | 4 | 4 / 0 | 4 / 0 |
| all12 | 12 | 12 | 12 / 0 | 12 / 0 |

| Member | Arm | Status | Called / attempts | Anchor Δ NLL | Gradient / tolerance | Additivity / tolerance | KKT | Objective / guarded / diagnostic / reconstruction seconds | Failure |
|---|---|---|---:|---:|---:|---:|---:|---|---|
| DS16-020 | fitted-c | passed | 6 / 6 | 0 | 2.72586e-05 | 0 | 0.000128978 | 0.0354019 / 0.104125 / 0.110808 / 0.0055528 |  |
| DS16-020 | zero-c | passed | 6 / 6 | 0 | 0.00120784 | 0 | 7.76647e-05 | 0.0355776 / 0.103633 / 0.10979 / 0.00501078 |  |
| DS16-024 | fitted-c | passed | 6 / 6 | 0 | 9.72432e-05 | 0 | 0.00012391 | 0.0303341 / 0.0922906 / 0.0982573 / 0.0049856 |  |
| DS16-024 | zero-c | passed | 6 / 6 | 0 | 5.43442e-05 | 0 | 0.000556893 | 0.0300798 / 0.0919858 / 0.097583 / 0.00448027 |  |
| DS16-054 | fitted-c | passed | 6 / 6 | 0 | 7.31703e-05 | 1.45519e-05 | 0.000137379 | 0.0256383 / 0.0799257 / 0.0860335 / 0.00612032 |  |
| DS16-054 | zero-c | passed | 6 / 6 | 0 | 3.95837e-05 | 0 | 4.92939e-05 | 0.0266638 / 0.0817217 / 0.086822 / 0.00425359 |  |
| DS16-058 | fitted-c | passed | 6 / 6 | 0 | 3.41032e-05 | 7.27596e-06 | 1.37892e-05 | 0.0215711 / 0.0712454 / 0.0761659 / 0.00433335 |  |
| DS16-058 | zero-c | passed | 6 / 6 | 0 | 0.000305069 | 3.63798e-06 | 0.000328183 | 0.0215814 / 0.0709612 / 0.0757706 / 0.00409395 |  |
| DS17-006 | fitted-c | passed | 6 / 6 | 0 | 0.00025433 | 3.63798e-06 | 2.48106e-05 | 0.0150886 / 0.0537177 / 0.0576631 / 0.00372055 |  |
| DS17-006 | zero-c | passed | 6 / 6 | 0 | 0.000553961 | 0 | 0.000125026 | 0.0152396 / 0.0541381 / 0.0579666 / 0.00321217 |  |
| DS17-015 | fitted-c | passed | 6 / 6 | 0 | 1.30228e-05 | 7.27596e-06 | 1.57918e-05 | 0.0355211 / 0.100532 / 0.106796 / 0.00550072 |  |
| DS17-015 | zero-c | passed | 6 / 6 | 0 | 0.00110725 | 1.45519e-05 | 0.000781938 | 0.0349894 / 0.0998012 / 0.105672 / 0.00481931 |  |
| DS17-027 | fitted-c | passed | 6 / 6 | 0 | 7.90692e-05 | 0 | 0.000100943 | 0.0179747 / 0.0610881 / 0.0653792 / 0.00396853 |  |
| DS17-027 | zero-c | passed | 6 / 6 | 0 | 0.000799625 | 7.27596e-06 | 0.000186411 | 0.0175873 / 0.0596623 / 0.0637819 / 0.00345142 |  |
| DS17-031 | fitted-c | passed | 6 / 6 | 0 | 0.000336353 | 0 | 0.000212131 | 0.0233981 / 0.0759242 / 0.0810139 / 0.00459341 |  |
| DS17-031 | zero-c | passed | 6 / 6 | 0 | 0.000561822 | 0 | 0.000146698 | 0.0237739 / 0.077849 / 0.0838948 / 0.00461354 |  |
| DS18-013 | fitted-c | passed | 6 / 6 | 0 | 0.000303702 | 3.63798e-06 | 0.000135395 | 0.0229451 / 0.0712743 / 0.0766407 / 0.00467084 |  |
| DS18-013 | zero-c | passed | 6 / 6 | 0 | 0.000249071 | 3.63798e-06 | 5.77647e-05 | 0.0236886 / 0.072791 / 0.0774944 / 0.00386626 |  |
| DS18-023 | fitted-c | passed | 6 / 6 | 0 | 8.71323e-05 | 0 | 0.000176554 | 0.0230835 / 0.0713615 / 0.07598 / 0.00419997 |  |
| DS18-023 | zero-c | passed | 6 / 6 | 0 | 0.000172208 | 7.27596e-06 | 2.16691e-05 | 0.0227485 / 0.0702792 / 0.0750622 / 0.00410376 |  |
| DS18-024 | fitted-c | passed | 6 / 6 | 0 | 0.000133703 | 7.27596e-06 | 8.00485e-05 | 0.0245963 / 0.075632 / 0.0805687 / 0.00445752 |  |
| DS18-024 | zero-c | passed | 6 / 6 | 0 | 9.64853e-05 | 3.63798e-06 | 2.4496e-05 | 0.0240439 / 0.0752068 / 0.0800833 / 0.00414666 |  |
| DS18-029 | fitted-c | passed | 6 / 6 | 0 | 0.000103239 | 0 | 2.07179e-05 | 0.0220397 / 0.0701668 / 0.074773 / 0.00425233 |  |
| DS18-029 | zero-c | passed | 6 / 6 | 0 | 0.00012222 | 7.27596e-06 | 4.64055e-05 | 0.0221842 / 0.0704398 / 0.0749475 / 0.00371902 |  |

| Member | Matched model | Input reconstruction seconds | Total member seconds |
|---|---|---:|---:|
| DS16-020 | True | 15.2557 | 15.4973 |
| DS16-024 | True | 14.8888 | 15.1043 |
| DS16-054 | True | 12.475 | 12.6675 |
| DS16-058 | True | 11.8322 | 12.0014 |
| DS17-006 | True | 10.801 | 10.931 |
| DS17-015 | True | 12.9785 | 13.2116 |
| DS17-027 | True | 10.7 | 10.8449 |
| DS17-031 | True | 11.5502 | 11.7338 |
| DS18-013 | True | 10.7584 | 10.9292 |
| DS18-023 | True | 11.2948 | 11.4622 |
| DS18-024 | True | 11.1938 | 11.372 |
| DS18-029 | True | 11.1644 | 11.3305 |

A normalized discrepancy of one is the declared tolerance. Missing checks are unavailable, not zero. Failed calls retain measured costs. Objective time is inside guarded-call time, which is inside diagnostic time; do not add these nested costs. Reconstruction is reported separately. Totals are observed invocation times, not embedded-speed claims.

Exact model matching includes inference-array fingerprints, original local center and input binding; it does not imply equal c-arm endpoints. No spatial fit, quadrature or reference port was used. All failures and full-member denominators remain visible.

[SUMMARY.json](SUMMARY.json) records per-call evidence, discrepancies, costs and receipt/claim hashes. Protocol file SHA256 and canonical receipt digest are distinct. Raw receipt size is 95928354 bytes; hashes alone are not a standalone replay bundle.

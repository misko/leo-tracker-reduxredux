# DS22-071: the combined B failure is not an acceptance failure

All six original full-view B endpoints were stationary. The selected full endpoint is 324.778 km from the unconfirmed configured reference, versus 10.222 and 3.124 km for the shared-discovery half winners. A training-only audit shows the selected full endpoint beats every alternative full endpoint in both band likelihoods, despite a larger prior penalty. Simple positive band reweighting cannot reverse that ordering among these fixed full states.

The selected full start 2 has objective 40235.503084, low-band NLL 22651.368113, high-band NLL 16643.848097, and prior 940.286875. Its local position is (92.430754, 189.699770) km. All six full KKT residuals are between 0.000187 and 0.000427.

| Alternative full start | Objective difference | Low NLL difference | High NLL difference | Prior difference |
|---|---:|---:|---:|---:|
| 0 | +2815.053381 | +2189.871842 | +1031.790871 | −406.609332 |
| 1 | +1387.450739 | +1424.356843 | +140.445607 | −177.351711 |
| 3 | +2012.424989 | +1798.020508 | +704.395844 | −489.991363 |
| 4 | +1319.253604 | +1316.230327 | +446.896902 | −443.873626 |
| 5 | +2990.540860 | +2344.784405 | +1043.250520 | −397.494066 |

Both half selectors instead choose start 3. Their own NLLs are 21779.800848 low and 15639.578013 high, below the corresponding full-winner NLL by 871.567264 and 1004.270084. Effective signal masses rise from full 973.847/535.840 to own-half 1156.613/766.064. These are separately optimized calibration/association states; the table does not claim that their nuisance vectors can simply be combined or that total objectives across different views are interchangeable.

This motivates testing coupled nuisance/association basin reachability rather than relaxing acceptance. It differs from DS22-059, where every original final disk excludes the configured station. No new fit or reference-selected seed was used by this audit.

Source `fa34d9290`; eight objective evaluations, zero optimizer fits, 28.639 seconds. Namespace `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-071-band-inventory-v1`; report SHA256 `f905f05177ef62b50f81f679fa2cfcae434f41f63487943ed20242a24563bb65`. Exact full NLL and objective accounting closes to 1e-7. Position distances are post-seal configured-unconfirmed comparisons, not verified accuracy claims.

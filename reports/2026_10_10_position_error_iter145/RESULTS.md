# Fixed correlated-emission pilot

Globally frozen geometry: timestamp.

All twelve consumed development members remain in coverage. The globally fixed rho=0.25 hypothesis is compared with a fresh rho=0 control; no objective-based model winner is selected. Archived B7 is a separate historical comparator. Both c arms use matched observations, pairs, bank, priors and fitted-derived starts; c=0 locks RF terms.

Frequency RMS uses updated conditional marginal responsibilities and is descriptive. Improved likelihood or RMS does not establish improved localization, covariance calibration or independent validation. Full accuracy metrics are withheld for incomplete qualification; no failed member is imputed or silently replaced by archive.

![Position errors](comparison.png)

| Dataset | Arm | Model | Qualified | Mean km | Median km | p95 km | Worst km |
|---|---|---|---|---|---|---|---|
| full | fitted-c | archive | 12/12 | 1.117359 | 0.905836 | 2.501273 | 3.389263 |
| full | fitted-c | control | 12/12 | 1.117359 | 0.905836 | 2.501273 | 3.389263 |
| full | fitted-c | rho25 | 12/12 | 1.114049 | 0.890257 | 2.543971 | 3.459085 |
| full | zero-c | archive | 12/12 | 1.255968 | 0.826722 | 2.782485 | 3.897895 |
| full | zero-c | control | 12/12 | 1.280581 | 0.826722 | 2.915394 | 4.193248 |
| full | zero-c | rho25 | 12/12 | 1.322881 | 1.038222 | 2.823465 | 4.193941 |
| DS16 | fitted-c | archive | 4/4 | 1.026534 | 1.054130 | 1.677589 | 1.774735 |
| DS16 | fitted-c | control | 4/4 | 1.026534 | 1.054130 | 1.677589 | 1.774735 |
| DS16 | fitted-c | rho25 | 4/4 | 1.027871 | 1.053794 | 1.692429 | 1.795241 |
| DS16 | zero-c | archive | 4/4 | 0.963645 | 0.826722 | 1.479465 | 1.592919 |
| DS16 | zero-c | control | 4/4 | 0.963645 | 0.826722 | 1.479465 | 1.592919 |
| DS16 | zero-c | rho25 | 4/4 | 1.154907 | 1.038222 | 1.568402 | 1.651262 |
| DS17 | fitted-c | archive | 4/4 | 0.867977 | 0.804945 | 1.343881 | 1.434476 |
| DS17 | fitted-c | control | 4/4 | 0.867977 | 0.804945 | 1.343881 | 1.434476 |
| DS17 | fitted-c | rho25 | 4/4 | 0.850480 | 0.775621 | 1.338963 | 1.437118 |
| DS17 | zero-c | archive | 4/4 | 1.184515 | 1.221124 | 1.841141 | 1.869877 |
| DS17 | zero-c | control | 4/4 | 1.184515 | 1.221124 | 1.841141 | 1.869877 |
| DS17 | zero-c | rho25 | 4/4 | 1.124344 | 1.182528 | 1.695695 | 1.702166 |
| DS18 | fitted-c | archive | 4/4 | 1.457567 | 1.009240 | 3.071035 | 3.389263 |
| DS18 | fitted-c | control | 4/4 | 1.457567 | 1.009240 | 3.071035 | 3.389263 |
| DS18 | fitted-c | rho25 | 4/4 | 1.463795 | 0.979080 | 3.134272 | 3.459085 |
| DS18 | zero-c | archive | 4/4 | 1.619744 | 1.075528 | 3.527085 | 3.897895 |
| DS18 | zero-c | control | 4/4 | 1.693582 | 1.075528 | 3.778135 | 4.193248 |
| DS18 | zero-c | rho25 | 4/4 | 1.689393 | 1.069494 | 3.783779 | 4.193941 |

| Dataset | Arm | Comparison | Qualified pairs | Better | Worse | >1 km worse | Max regression km |
|---|---|---|---|---|---|---|---|
| full | fitted-c | archive_to_control | 12/12 | 0 | 0 | 0 | 0.000000 |
| full | fitted-c | control_to_correlated | 12/12 | 5 | 7 | 0 | 0.069821 |
| full | zero-c | archive_to_control | 12/12 | 4 | 8 | 0 | 0.295352 |
| full | zero-c | control_to_correlated | 12/12 | 4 | 8 | 0 | 0.490651 |
| DS16 | fitted-c | archive_to_control | 4/4 | 0 | 0 | 0 | 0.000000 |
| DS16 | fitted-c | control_to_correlated | 4/4 | 2 | 2 | 0 | 0.020506 |
| DS16 | zero-c | archive_to_control | 4/4 | 2 | 2 | 0 | 0.000000 |
| DS16 | zero-c | control_to_correlated | 4/4 | 0 | 4 | 0 | 0.490651 |
| DS17 | fitted-c | archive_to_control | 4/4 | 0 | 0 | 0 | 0.000000 |
| DS17 | fitted-c | control_to_correlated | 4/4 | 2 | 2 | 0 | 0.003370 |
| DS17 | zero-c | archive_to_control | 4/4 | 1 | 3 | 0 | 0.000000 |
| DS17 | zero-c | control_to_correlated | 4/4 | 2 | 2 | 0 | 0.023861 |
| DS18 | fitted-c | archive_to_control | 4/4 | 0 | 0 | 0 | 0.000000 |
| DS18 | fitted-c | control_to_correlated | 4/4 | 1 | 3 | 0 | 0.069821 |
| DS18 | zero-c | archive_to_control | 4/4 | 1 | 3 | 0 | 0.295352 |
| DS18 | zero-c | control_to_correlated | 4/4 | 2 | 2 | 0 | 0.033705 |

| Member | Terminal status | Pair/support coverage | Attempt failures |
|---|---|---|---|
| DS16-020 | complete | {"available": true, "observations": 3515, "pairs": 1722, "paired_rows": 3444, "unpaired_rows": 71, "unpaired_reasons": {"no-close-neighbour": 71}} | {} |
| DS16-024 | complete | {"available": true, "observations": 3406, "pairs": 1659, "paired_rows": 3318, "unpaired_rows": 88, "unpaired_reasons": {"no-close-neighbour": 88}} | {} |
| DS16-054 | complete | {"available": true, "observations": 3073, "pairs": 1491, "paired_rows": 2982, "unpaired_rows": 91, "unpaired_reasons": {"no-close-neighbour": 91}} | {} |
| DS16-058 | complete | {"available": true, "observations": 2921, "pairs": 1414, "paired_rows": 2828, "unpaired_rows": 93, "unpaired_reasons": {"no-close-neighbour": 93}} | {} |
| DS17-006 | complete | {"available": true, "observations": 2389, "pairs": 1152, "paired_rows": 2304, "unpaired_rows": 85, "unpaired_reasons": {"no-close-neighbour": 85}} | {} |
| DS17-015 | complete | {"available": true, "observations": 3378, "pairs": 1648, "paired_rows": 3296, "unpaired_rows": 82, "unpaired_reasons": {"no-close-neighbour": 82}} | {} |
| DS17-027 | complete | {"available": true, "observations": 2648, "pairs": 1285, "paired_rows": 2570, "unpaired_rows": 78, "unpaired_reasons": {"no-close-neighbour": 78}} | {} |
| DS17-031 | complete | {"available": true, "observations": 3011, "pairs": 1463, "paired_rows": 2926, "unpaired_rows": 85, "unpaired_reasons": {"no-close-neighbour": 85}} | {} |
| DS18-013 | complete | {"available": true, "observations": 2609, "pairs": 1256, "paired_rows": 2512, "unpaired_rows": 97, "unpaired_reasons": {"no-close-neighbour": 97}} | {} |
| DS18-023 | complete | {"available": true, "observations": 2549, "pairs": 1229, "paired_rows": 2458, "unpaired_rows": 91, "unpaired_reasons": {"no-close-neighbour": 91}} | {} |
| DS18-024 | complete | {"available": true, "observations": 2936, "pairs": 1427, "paired_rows": 2854, "unpaired_rows": 82, "unpaired_reasons": {"no-close-neighbour": 82}} | {} |
| DS18-029 | complete | {"available": true, "observations": 2771, "pairs": 1337, "paired_rows": 2674, "unpaired_rows": 97, "unpaired_reasons": {"no-close-neighbour": 97}} | {} |

| Member | Arm | Model | Qualified | Objective | Updated-marginal RMS Hz | Fit seconds |
|---|---|---|---|---|---|---|
| DS16-020 | fitted-c | archive | True | 40484.109 | None | None |
| DS16-020 | fitted-c | control | True | 40484.109 | 74.20245326503074 | 0.0709121348336339 |
| DS16-020 | fitted-c | rho25 | True | 40436.851 | 74.52866689438399 | 2.351698338985443 |
| DS16-020 | zero-c | archive | True | 41963.755 | None | None |
| DS16-020 | zero-c | control | True | 41963.755 | 139.38636253438176 | 1.6027317619882524 |
| DS16-020 | zero-c | rho25 | True | 41727.228 | 144.5754008941576 | 2.507846648339182 |
| DS16-024 | fitted-c | archive | True | 37430.593 | None | None |
| DS16-024 | fitted-c | control | True | 37430.593 | 59.33543404989565 | 0.06785242399200797 |
| DS16-024 | fitted-c | rho25 | True | 37369.859 | 59.50801404663928 | 2.525471888948232 |
| DS16-024 | zero-c | archive | True | 38676.835 | None | None |
| DS16-024 | zero-c | control | True | 38676.835 | 114.00995344254619 | 1.7656781887635589 |
| DS16-024 | zero-c | rho25 | True | 38464 | 123.28834066290105 | 2.628603321965784 |
| DS16-054 | fitted-c | archive | True | 32884.37 | None | None |
| DS16-054 | fitted-c | control | True | 32884.37 | 55.16001438147082 | 0.053578915540128946 |
| DS16-054 | fitted-c | rho25 | True | 32830.842 | 55.15951011510113 | 1.572383007965982 |
| DS16-054 | zero-c | archive | True | 32897.906 | None | None |
| DS16-054 | zero-c | control | True | 32897.906 | 56.600239352456896 | 1.0099486229009926 |
| DS16-054 | zero-c | rho25 | True | 32842.029 | 56.61313800836304 | 1.5102293891832232 |
| DS16-058 | fitted-c | archive | True | 30923.604 | None | None |
| DS16-058 | fitted-c | control | True | 30923.604 | 55.30362470820226 | 0.022895171772688627 |
| DS16-058 | fitted-c | rho25 | True | 30873.952 | 55.25103142423893 | 1.1943101370707154 |
| DS16-058 | zero-c | archive | True | 31893.015 | None | None |
| DS16-058 | zero-c | control | True | 31893.015 | 113.25354157705932 | 0.8316234019584954 |
| DS16-058 | zero-c | rho25 | True | 31700.518 | 115.89452533848177 | 1.2448196890763938 |
| DS17-006 | fitted-c | archive | True | 25156.996 | None | None |
| DS17-006 | fitted-c | control | True | 25156.996 | 61.831263620823364 | 0.03718812996521592 |
| DS17-006 | fitted-c | rho25 | True | 25107.909 | 61.43389827557075 | 0.8142736032605171 |
| DS17-006 | zero-c | archive | True | 26269.548 | None | None |
| DS17-006 | zero-c | control | True | 26269.548 | 134.02713887446419 | 0.5350288404151797 |
| DS17-006 | zero-c | rho25 | True | 26063.746 | 136.66514163698875 | 0.8600502931512892 |
| DS17-015 | fitted-c | archive | True | 36944.373 | None | None |
| DS17-015 | fitted-c | control | True | 36944.373 | 50.90855013670594 | 0.043270007241517305 |
| DS17-015 | fitted-c | rho25 | True | 36892.779 | 50.76899373779917 | 2.7312948359176517 |
| DS17-015 | zero-c | archive | True | 38116.248 | None | None |
| DS17-015 | zero-c | control | True | 38116.248 | 102.02879474437786 | 1.8949304982088506 |
| DS17-015 | zero-c | rho25 | True | 37947.312 | 111.84878938829836 | 2.8871162701398134 |
| DS17-027 | fitted-c | archive | True | 28045.71 | None | None |
| DS17-027 | fitted-c | control | True | 28045.71 | 75.89985465036354 | 0.04136674106121063 |
| DS17-027 | fitted-c | rho25 | True | 28017.514 | 75.60133622400153 | 1.038053269032389 |
| DS17-027 | zero-c | archive | True | 28767.764 | None | None |
| DS17-027 | zero-c | control | True | 28767.764 | 116.06817105448401 | 0.7446140893734992 |
| DS17-027 | zero-c | rho25 | True | 28636.937 | 117.33510019688818 | 1.171570718754083 |
| DS17-031 | fitted-c | archive | True | 31981.023 | None | None |
| DS17-031 | fitted-c | control | True | 31981.023 | 60.54448537482561 | 0.055580444633960724 |
| DS17-031 | fitted-c | rho25 | True | 31917.023 | 60.40387625547572 | 1.4923230889253318 |
| DS17-031 | zero-c | archive | True | 33151.281 | None | None |
| DS17-031 | zero-c | control | True | 33151.281 | 117.23444537903953 | 1.080864826682955 |
| DS17-031 | zero-c | rho25 | True | 32939.428 | 121.50410347107292 | 1.5843304209411144 |
| DS18-013 | fitted-c | archive | True | 29787.585 | None | None |
| DS18-013 | fitted-c | control | True | 29787.585 | 91.15245468674497 | 0.0524827023036778 |
| DS18-013 | fitted-c | rho25 | True | 29747.346 | 91.83962379803211 | 1.4351150281727314 |
| DS18-013 | zero-c | archive | True | 29819.147 | None | None |
| DS18-013 | zero-c | control | True | 29819.147 | 93.68182671331127 | 0.9628129419870675 |
| DS18-013 | zero-c | rho25 | True | 29773.699 | 94.73217323272151 | 1.4803597978316247 |
| DS18-023 | fitted-c | archive | True | 27910.657 | None | None |
| DS18-023 | fitted-c | control | True | 27910.657 | 88.40433921680646 | 0.051775050815194845 |
| DS18-023 | fitted-c | rho25 | True | 27876.947 | 88.5972750205755 | 1.5219393349252641 |
| DS18-023 | zero-c | archive | True | 28116.93 | None | None |
| DS18-023 | zero-c | control | True | 28117.394 | 99.91098135242405 | 0.975963463075459 |
| DS18-023 | zero-c | rho25 | True | 28055.364 | 100.61022589645951 | 1.4773395317606628 |
| DS18-024 | fitted-c | archive | True | 31522.415 | None | None |
| DS18-024 | fitted-c | control | True | 31522.415 | 56.22519927889708 | 0.05424845824018121 |
| DS18-024 | fitted-c | rho25 | True | 31469.083 | 57.244982766266254 | 1.5835835332982242 |
| DS18-024 | zero-c | archive | True | 31986.148 | None | None |
| DS18-024 | zero-c | control | True | 31986.148 | 88.02802123795037 | 1.1072479565627873 |
| DS18-024 | zero-c | rho25 | True | 31867.124 | 89.39837733152675 | 1.7639377149753273 |
| DS18-029 | fitted-c | archive | True | 29701.254 | None | None |
| DS18-029 | fitted-c | control | True | 29701.254 | 58.628400448928005 | 0.07303725881502032 |
| DS18-029 | fitted-c | rho25 | True | 29654.043 | 59.02006447506719 | 1.5578004932031035 |
| DS18-029 | zero-c | archive | True | 29716.842 | None | None |
| DS18-029 | zero-c | control | True | 29716.842 | 60.091032402518856 | 0.9213863601908088 |
| DS18-029 | zero-c | rho25 | True | 29667.476 | 60.35586389114611 | 1.4403930050320923 |

Objective values belong to different emission models and are not an operational selection rule. All raw qualification/score/support fields and per-member paired changes are retained in [evaluation.json](evaluation.json). Archive qualification is historical provenance, not a newly fitted control. No full-cohort or deployment gain is inferred from this conditional pilot.

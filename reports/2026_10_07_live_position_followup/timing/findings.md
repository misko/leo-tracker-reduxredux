# Controlled timing-prior refits

Read-only archived-snapshot experiment, two catastrophic scans. All archived basins are retained. The two published V16 fitted-c final vectors (associated and zero-timing) form the identical fixed, score-independent seed pool for every timing variant and RF arm. Seeds depend on the original full-data fitted-c fit; this is a bounded warm-start sensitivity experiment, not an independent localization validation.

Only relative timing sigma changes (.15 to 1 s); common sigma stays 3 s, sigma_hz=125, detection budget=1.6, clutter=.5. Original observations, satellite bank, receiver correction, prior, calibration penalties and local basin disks stay fixed. Each fit has 5 s and 300 iteration caps; score winners include unconverged fits, matching the published selection rule.

| Scan | Relative sigma | c arm | Winner basin | Error km | Total score | Data NLL | Timing penalty | RMS Hz | KKT | Converged |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| 559a822227a6a71b | 0.15 | fitted-c | point:31.25:-231.25 | 189.436 | 36156.671 | 36090.457 | 60.114 | 153.37 | 0.000263 | True |
| 559a822227a6a71b | 0.15 | zero-c | point:31.25:-231.25 | 187.700 | 36273.463 | 36203.601 | 63.761 | 173.92 | 2.9e-05 | True |
| 559a822227a6a71b | 1.0 | fitted-c | point:-68.75:-81.25 | 5.813 | 28859.432 | 28591.655 | 249.439 | 116.99 | 0.00148 | False |
| 559a822227a6a71b | 1.0 | zero-c | point:-68.75:-81.25 | 7.288 | 29353.567 | 29084.974 | 250.255 | 131.62 | 6.71e-05 | True |
| 6bf407cfe8158445 | 0.15 | fitted-c | point:-37.5:212.5 | 296.818 | 44170.238 | 43960.592 | 200.867 | 121.39 | 0.000265 | True |
| 6bf407cfe8158445 | 0.15 | zero-c | point:-37.5:212.5 | 296.812 | 44170.299 | 43960.687 | 200.833 | 121.40 | 29.6 | False |
| 6bf407cfe8158445 | 1.0 | fitted-c | point:-87.5:-87.5 | 4.447 | 38697.766 | 38508.407 | 179.763 | 106.21 | 1.32e+03 | False |
| 6bf407cfe8158445 | 1.0 | zero-c | point:-87.5:-87.5 | 4.581 | 38705.320 | 38513.461 | 182.262 | 106.55 | 1.18e+03 | False |

Validation: 40 archived objective values reproduced to 1e-6; analytic timing-only objective/gradient differences checked on every fitting seed before optimization. Receipt checks verify identical basin/start/bank pools across all arms, exact c=0, fixed common timing sigma, and additive score decomposition. 80 fits; elapsed 339.7 s including source reconstruction.

Accuracy is evaluated only after fitting, separately from frequency NLL and posterior RMS. A lower penalized score or in-sample RMS does not establish improved localization. Time-limited, nonstationary winners are provisional. No services, deployments, RF collection, QNAP data, or golden scientific fixtures changed.

The first scan published zero-c result was near (~5.20 km), whereas the primary zero-c control selects the far basin (~296.81 km). This discrepancy exposes dependence on the fitted-c-only warm-start pool; the primary zero-c result does not reproduce the published zero-c optimization. All-arm archived fixed-state repricing below isolates the omitted seed-state sensitivity without additional optimization.

Fixed-state repricing uses all archived V16 final vectors from both RF arms, projecting c exactly to zero for the zero-c arm. Same full pool across all four variants; no optimizer, so these are alternative-state score comparisons, not refits.

| Scan | Relative sigma | c arm | Winning source arm | Basin | Error km | Score |
|---|---:|---|---|---|---:|---:|
| 6bf407cfe8158445 | 0.15 | zero-c | zero-c | point:-87.5:-87.5 | 5.195 | 44111.833 |
| 6bf407cfe8158445 | 0.15 | fitted-c | zero-c | point:-87.5:-87.5 | 5.195 | 44111.833 |
| 6bf407cfe8158445 | 1.0 | zero-c | fitted-c | point:-87.5:-87.5 | 5.941 | 38871.540 |
| 6bf407cfe8158445 | 1.0 | fitted-c | fitted-c | point:-87.5:-87.5 | 5.941 | 38863.114 |
| 559a822227a6a71b | 0.15 | zero-c | zero-c | point:-68.75:-81.25 | 9.230 | 36190.125 |
| 559a822227a6a71b | 0.15 | fitted-c | fitted-c | point:31.25:-231.25 | 189.436 | 36156.671 |
| 559a822227a6a71b | 1.0 | zero-c | zero-c | point:-68.75:-81.25 | 5.795 | 29422.411 |
| 559a822227a6a71b | 1.0 | fitted-c | fitted-c | point:-68.75:-81.25 | 5.819 | 28918.606 |

For the first scan, the archived zero-c near state is feasible for fitted-c as well and scores 44111.833 under the original .15 s V16 objective, beating the published far fitted-c state (44170.238). This directly identifies a start/optimization selection limitation even without loosening timing. For the second scan, original fitted-c fixed-state repricing still favors the far basin; relaxing timing shifts both RF arms to the near basin. The timing sensitivity and first-case seed sensitivity are distinct observations.

Repricing also executes the strengthened input/analysis manifest and composite window/snapshot/candidate evidence assertions added after primary imports. Exact executed helper snapshot and current verification source hashes are distinguished in provenance.json.

Exact executed helper bytes: source_snapshots/inputs_executed.py.txt. Publication formatting hashes are separate from historical hashes in provenance.json.

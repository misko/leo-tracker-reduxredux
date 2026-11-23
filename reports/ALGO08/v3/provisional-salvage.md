# Joint refit before discarding independently salvaged tracks

One bounded position fit recovered 65 named-v3 observations on DS30-0160. The cumulative error fell from **1.915 to 0.823 km** at `c=0` and **2.022 to 1.337 km** with fitted `c`. The fitted fix remains **248.5 m** worse than named v3. The zero-calibration fix remains **24.7 m** worse. Both RF RMS values worsened. DS30-0160 motivated the policy and the fitted result sits only 1.5 m inside the earlier 250 m development screen. On the triggering DS30-0316 control, the trial found no newly compatible track and reverted to the exact prior scientific output. [Frozen protocol](provisional-salvage-protocol.md) · [Complete saved evidence](measurements/provisional-salvage.json.gz)

| Saved case and route | `c=0` error | Fitted `c` error | `c=0` RF RMS | Fitted `c` RF RMS | Owners per arm |
|---|---:|---:|---:|---:|---:|
| DS30-0160 named v3 | 0.798 km | 1.089 km | 126.335 Hz | 126.093 Hz | 1,037 |
| DS30-0160 historical cumulative | 1.915 km | 2.022 km | 127.012 Hz | 126.950 Hz | 923 |
| DS30-0160 provisional refit | 0.823 km | 1.337 km | 127.816 Hz | 127.548 Hz | 988 |
| DS30-0316 named v3 | 1.945 km | 1.863 km | 99.232 Hz | 99.054 Hz | 1,976 |
| DS30-0316 historical cumulative | 1.888 km | 1.819 km | 99.592 Hz | 99.434 Hz | 2,002 |
| DS30-0316 provisional refit, reverted | 1.888 km | 1.819 km | 99.592 Hz | 99.434 Hz | 2,002 |

The opt-in trial runs after the original independent salvage and unchanged same-seed gate. Every offered fragment must match the nominated observation interval, satellite and signed alias. A single bounded `c=0` fit on those rows and existing curved support must strictly improve the same normalized objective with fixed nuisance design. The unchanged original gate must recover new observations and preserve every original survivor. If some proposed rows still fail, the survivors must pass the same gate again on their rebuilt support at the new seed. The ordinary predictive selection and matched final pair then require both arms to pass. Any failed check resumes the original predictive and paired finish. [Policy](provisional_salvage.py) · [Opt-in integration](blind_joint_finish.py)

On DS30-0160, the expanded 979-point objective decreased from 8,040.085 to 8,032.807 as the provisional seed moved 3.074 km. The 65-point receiver-1 channel-1 signed-alias fragment qualified. The 21- and 32-point fragments still failed. The new paired finish used 926 compatible curved and 62 compatible predictive observations. Both arms kept all 923 prior cumulative observations and added the same 65 observation IDs with the NORAD and role originally published by named v3. The other 49 named observations remain absent. On DS30-0316, the 1,668-point objective decreased from 14,273.408 to 14,269.258, but the same four salvaged fragments still failed. A lower objective alone was insufficient. Both cases verified the original grid/path bindings, 179 grid points and all eight encoded and decoded PNGs. The reverted case reproduced the historical cumulative terminal, owner rows, grid/path science, and eight figure files byte-for-byte. [Prior DS30-0160 comparison](prospective-0160-solver.md) · [Prior DS30-0316 comparison](prospective-0316-solver.md)

| Saved case | Historical cumulative solve CPU | Provisional solve CPU | Trial fit and gate CPU | Whole candidate wall / CPU |
|---|---:|---:|---:|---:|
| DS30-0160 | 11.584 s | 11.608 s | 0.088 s | 14.901 / 14.896 s |
| DS30-0316 | 8.659 s | 9.410 s | 0.076 s | 12.733 / 12.724 s |

The adopted 0160 route paid 0.114 additional CPU s for predictive selection and the usual paired finish at the trial point. The measured trial gate and resulting final finish appear within total solve CPU. The larger 0316 total difference comes from comparisons to historical jobs, so use 0.076 s as the directly observed provisional work on the reverted case. Both workers ran in one shared Gauss slot on CPU2, nice 15, I/O priority 7 and one numerical thread. Each exited 0 with zero kernel input blocks and used only previously authenticated tmpfs detections, causal archives and original inventory documents. The worker disabled the optional phase forecast and kept the ordinary solver, exact graph reuse and one-pass web layout otherwise intact. [Runner](provisional_salvage_trial.py)

Earlier collapsed-solver work tested all-fragment add-back and later paired repair on DS30-0374. The present trial acts before predictive support is formed and screens added points at a newly fitted position without weakening the paired publication gates. Its one improvement is on the recording used to design the change. [Earlier salvage add-back](../single-core-2x/solver-salvage-addback.md) · [Earlier paired repair](../single-core-2x/solver-bounded-salvage-repair.md)

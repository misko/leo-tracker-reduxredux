# C053 union endpoints disagree across satellites and clutter

This fixed-state audit compares the two accepted, sealed union-bank endpoints from `MODEL_C_053_WINNER_UNION_RESULTS.md`. Positive differences below are earlier/closer minus later/distant negative log likelihood. No new fit, selection, or reference-coordinate access occurs in this audit.

| Channel | NLL difference |
|---|---:|
| CH1 | −0.755 |
| CH2 | −11.430 |
| CH3 | −431.990 |
| CH4 | +494.181 |
| CH5 | +102.359 |
| CH6 | +14.165 |
| CH7 | −60.377 |
| CH8 | +130.351 |

Both bands favor the distant endpoint in aggregate: CH1–4 contributes +50.006 and CH5–8 +186.497, closing to the +236.503 NLL gap. The low-band total conceals opposing CH3 and CH4 preferences. CH4 receiver 1 contributes +361.493, with posterior signal mass 12.680 at the closer endpoint versus 79.380 at the distant endpoint. CH3 favors the closer endpoint on both receivers (−187.846 and −244.144). These are diagnostics of model preferences, not verified satellite labels.

Only 10 low-band and 7 high-band windows retain the same dominant non-clutter satellite. There are 609 low-band and 331 high-band satellite switches. Mean satellite/clutter posterior overlap is only 0.249 and 0.213, respectively. The two positions therefore correspond to substantially different association solutions.

In the low band, windows treated as clutter only at the closer endpoint contribute +982.042 NLL; the reverse transition contributes −822.309. Satellite-switch windows favor the closer endpoint by 105.340. In the high band, the corresponding clutter transitions contribute +442.189 and −260.890; satellite switches contribute +8.474. These large opposing contributions caution against attributing the aggregate score gap to a single bad observation or merely counting fitted signal windows.

The result rules out neither channel calibration mismatch nor incorrect candidate association. It does show that a simple low-versus-high disagreement is insufficient: both bands prefer the distant endpoint after summation, while strong disagreement remains within the low band. A controlled channel/receiver offset profile at these fixed endpoints can test calibration sensitivity without selecting channels using reference error. Any profile improvement would still need matched fitted-model and localization evaluation before promotion.

Validation: exact native per-window likelihood and satellite/clutter posterior reconstruction; saved objective and NLL replay within 1e-7; transition partitions and channel/receiver/time partitions close. The plain-model view supplies a zero-column clock design without changing the underlying objective or mutating its state. Its component test and Ruff passed. Research source commit `7585e0cd2`.

Runtime: 8.918 seconds, two objective evaluations, two explicit orbit calls, zero optimizer calls. All receiver and prespecified 30-second time groups are retained in the artifact. Output: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-c-winner-overlap-053-v1/`. Result SHA256 `28082f7154037efbf6ad33ec64d9412612059481df32ae2c664c8bbc53bd393d`; seal SHA256 `4179fd42d93565c0b651df5e200ddb7e91ba1045ac10a1436733c38f1b6f12d1`.

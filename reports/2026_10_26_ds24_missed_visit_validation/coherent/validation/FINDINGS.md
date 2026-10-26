# Coherent application of the sealed R01 method

The fixed four-block application adds51 native owners,46 in the original RF graph and32 on actively curved tracks. Fresh causal inference accepts24 additions:13 curved-likelihood and11 predictive-likelihood owners. All extend satellite families already present in the matched baseline. No new satellite-family direction was accepted.

The two development cases and24second blocks were frozen using earlier RF/graph evidence. All263 paired public-source windows completed, with526 target packets independently reconstructed exactly from corrected v2 forecasts. Original GLRT measurements and margins remain exact. Four additions overlap the earlier sparse panel;47 are beyond it. The position inputs contain original public winners plus these expansion additions only. They exclude sparse-only additions. Detector parity reuses the recording/runtime evidence; no fresh per-window blind candidate replay is claimed.

| Case | Original GLRT | Added | Added in graph | Added curved | Added in causal likelihood |
|---|---:|---:|---:|---:|---:|
| DS24-0011 |3754|25|25|22|3 curved|
| DS24-0097 |4226|26|21|10|10 curved +11 predictive|

The0011 additions accepted in likelihood extend NORAD61630. The0097 additions extend NORAD67349 (11 predictive),68234 (2 curved), and68710 (8 curved). Exact native IDs, source counters, donor identities, frequency innovations and weights are in `position_evaluation_native.json`; per-block figure sidecars include all51 additions and their RF graph membership. Fourteen of51 new owners return the zero FFT bin. Disjoint target support and nonzero innovations do not establish calibrated independent fine-frequency covariance.

In0011,19of the22new curved RF owners lie on `DS24-0011-RX1-CH7-T002-RF12440312500.000000`. This39point RF polynomial spans38.63seconds and passes the graph's active-curvature gate, but its component appears in the saved ALGO02 epoch0 paired-c gate failures for both proxy and floor. The unchanged policy removes that entire component from position likelihood. The other3new curved owners are on CH5 and survive; the remaining3CH5 additions are on a noncurved RF track and do not enter the final likelihood. The saved gate history records component rejection, not which individual residual/elevation subgate caused it; no retrospective fit was run to assign a finer cause.

| Case / input | Position error c=0 / fitted-c (m) | Frequency RMS c=0 / fitted-c (Hz) |
|---|---:|---:|
|0011 baseline|1727.734 /1567.031|82.142 /81.991|
|0011 proxy|1739.047 /1575.602|82.312 /82.162|
|0011 full-bin floor|1732.357 /1569.273|82.202 /82.047|
|0097 baseline|888.345 /833.121|71.501 /71.518|
|0097 proxy|726.144 /674.758|73.481 /73.496|
|0097 full-bin floor|712.349 /660.219|73.476 /73.494|

The0097 geographic gain survives the conservative full-bin scale:175.996m with c=0 and172.902m with fitted-c (19.81%/20.75%). Proxy gains are162.201m/158.363m. The0011 errors increase by11.312m/8.572m with proxy weights and4.623m/2.242m with the floor. Frequency RMS increases in both cases; improved in-sample frequency fit is not the explanation for improved0097 position accuracy. These are two previously exposed development recordings, not a held or generalization result.

Overall GLRT association includes postfit compatible points as well as likelihood points, with every original-plus-added observation in the denominator:

| Case / input | Associated c=0 | Associated fitted-c |
|---|---:|---:|
|0011 baseline|2671/3754 (71.15%)|2642/3754 (70.38%)|
|0011 proxy|2675/3779 (70.79%)|2646/3779 (70.02%)|
|0011 floor|2674/3779 (70.76%)|2645/3779 (69.99%)|
|0097 baseline|3304/4226 (78.18%)|3304/4226 (78.18%)|
|0097 proxy or floor|3314/4252 (77.94%)|3314/4252 (77.94%)|

The0097 additions change the selected likelihood structure:12 old likelihood IDs leave,62 incumbent IDs enter, and15 retained IDs change predictive/curved role while preserving their satellite and total native alias. Baseline-to-additions also relearns all4226 incumbent noise scales, with changes−0.864 to+16.702Hz. Proxy and floor have identical likelihood IDs, satellite labels, native aliases and incumbent scales; their14m position difference reflects new-owner weight sensitivity. The full baseline-to-expansion gain cannot be attributed solely to51 independent new measurements. No extra counterfactual sweep was run. For0011 the proxy adds one incumbent likelihood ID that the floor excludes.

Four fresh ALGO02 initializations were executed; two unchanged sealed fresh baselines were reused after exact input/source/prior/candidate/configuration/budget equality checks, including1172 prior scientific source hashes. The elevated launcher initially failed to import SciPy before any cavity inference because Linux protected the user-owned `/tmp` dependency symlink. All failed attempts and successful ALGO02 outputs remain intact. Root authorized restoring UID1000 and starting each untouched cavity stage once with only its remaining budget. Total numerical times were121.7–178.3seconds per job, below240seconds; interrupted elapsed time is reported separately in `execution_timing.json`. No ALGO02 rerun, new seed, gate change or budget reset occurred.

All four continuations completed with zero readguard denials. Input/first-attempt integrity and all12 c-arm endpoints, including the reused controls, replayed before reference-error reporting. Both c arms use matched observations, aliases, candidate sets, other priors and search budgets. Figures project Legendre RF curves back to native CFO with exact owner alias mapping. The full-bin floor remains an engineering sensitivity, not calibrated covariance or deployment qualification.

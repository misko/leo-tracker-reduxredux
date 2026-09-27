# DS6 host-bracket timing sensitivity

Restricting scan timing to the recorded host bracket does not achieve sub-kilometre accuracy on the four frozen development scans. All 12 starts converge, all four selected fits hit a timing boundary, and all four have worse held-out prediction. The constraint is not adopted.

| MS/s | Session suffix | Unrestricted error (m) | Bracket-constrained error (m) | Held log-score change |
|---|---|---:|---:|---:|
| 10 | 3221795d82a1c7ec | 4925 | 4611 | -2.310 |
| 2.5 | 5eaaa2a8f8c995b3 | 3643 | 3853 | -21.944 |
| 5 | c78fb2dba2465361 | 8502 | 4826 | -18.838 |
| 7.5 | c7e37f65ae9e08b0 | 465 | 4913 | -64.439 |

Across all 43 corrected independent fits, 36 timing shifts lie outside their recorded first-sample host brackets. The positive half-widths range from 0.181252 to 0.184290 seconds, while the median fitted shift is -0.596998 seconds. These figures are descriptive and are not direct clock-bias measurements.

The brackets come from the first-sample timing authority exported in each frozen numerical plan. Integer-nanosecond subtraction preserves their exact relative bounds. The authority brackets device sampling between host clock observations and checks realtime/monotonic consistency; it does not independently establish the host's absolute UTC accuracy. Orbit errors, identity errors, and other trajectory mismatches may also be absorbed by fitted time shifts. Thus this experiment tests a conditional model assumption, not a proven physical clock limit.

The treatment retains the corrected stationary offset profiler, fixed Student-t4 scale, candidate shortlists, causal elements, randomized whole-visit masks, local position bounds, and training-only winner selection. Only tau bounds change to each scan's recorded bracket. Three starts use the corrected independent horizontal position at lower bracket, zero, and upper bracket timing. The four scans are the pre-existing development set, not selected anew by error. Exact propagation audits every winner. The roof reference is read only by the post-fit summarizer.

Two errors improve and two worsen; no selected fit is below 1 km. Notably, the 7.5 MS/s control degrades from 465 m to 4913 m. The common timing freedom matters materially to geometry, but constraining it alone is not a reliable correction. Do not interpret mixed geographic improvements as evidence to impose the bracket selectively by scan.

Three tests pass: nanosecond bracket arithmetic and qualification, frozen inputs and all four completed bounded fits, and summary/reference bindings. All selected fits remain inside horizontal bounds, stationary offset checks pass, and exact propagation deviations remain below 0.05 Hz. The initial test import collided with a legacy module named run; loading this report's script under a distinct module name fixed the test harness before real fitting. No fitted-model code or protocol was changed after freezing.

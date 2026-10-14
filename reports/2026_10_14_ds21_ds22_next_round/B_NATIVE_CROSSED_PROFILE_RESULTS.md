# Crossed geography and nuisance-state control

A better stationary native-C state exists at the original B geography than at the previously selected moved native endpoint. The earlier free refinement therefore missed a better feasible basin; it does not establish that native C intrinsically prefers the moved geography.

The completed 2×2 diagnostic uses two training-selected geographies and two complete calibration/timing states. The first pair (`7f0530da9`) starts from the accepted native-C endpoint; the separately frozen extension (`153b4f44f`) starts from the audited lifted original B state. Within each pair only geography changes. All profiles enforce fixed position, the original B disk and priors, fitted c, 20 seconds/600 actual objective evaluations, and unchanged independent KKT acceptance. There are four actual calls total. Failed crossed profiles are preserved and were not retried.

| Initial calibration/timing state | Fixed geography | Accepted | Objective | Independent KKT |
|---|---|---|---:|---:|
| Native endpoint | Original B | No: deadline | 47390.827474 | 14291.796005 |
| Native endpoint | Native endpoint | Yes | 40240.278465 | 0.000125911 |
| Lifted original B | Original B | Yes | 40153.718553 | 0.000101310 |
| Lifted original B | Native endpoint | No: deadline | 45738.932320 | 3160.189770 |

The diagonal profiles converge while the crossed initializations do not. The better B-geography profile is available only when initialized with its own consistent calibration/timing state. This demonstrates substantial basin dependence and makes the incomplete crossed profiles unsuitable for declaring one fully profiled geography preferable globally.

| Accepted state | CH1–4 NLL, 1811 windows | CH5–8 NLL, 1418 windows | Total NLL | Total prior |
|---|---:|---:|---:|---:|
| Native-geography repeat | 22258.772111 | 17595.816158 | 39854.588269 | 385.690196 |
| B-geography profile | 22235.158723 | 17492.027842 | 39727.186565 | 426.531988 |

Both bands' likelihoods favor the stationary B-geography profile. Its larger prior penalty partly offsets the likelihood improvement, but the penalized objective still improves by 86.559912. Signal mass rises from 1225.156 to 1234.805 in the lower band and from 942.824 to 965.917 in the upper band. Exact low/high likelihood and timing/common-clock/group prior decomposition closes to the full objective using the full training frame and nonzero native-time clocks; the component-owned real-model test verifies this identity.

At fixed native calibration, simply moving geography to B's position increases NLL from 39854.588 to 50499.908 while leaving priors identical. That poor transplanted state is not a valid representative of the best available B-geography solution. Neither failed profile supports an uncertainty or global-optimality claim.

No reference or held data were read by these experiments. The two geographies come from frozen training winners, not truth coordinates. Historical original-C half results lack the new common receiver clocks and do not form matched half controls for this experiment. A separate exact full-frame likelihood-mask component is being qualified for a conditional channel ablation; genuine independent discovery remains a separate comparison.

Local evidence: `local/ds22-b-fixed-geography-v1` and `local/ds22-b-crossed-geography-v1`. A new profile-then-release policy from the accepted B-geography profile is a distinct bounded experiment, not a continuation of either failed crossed profile.

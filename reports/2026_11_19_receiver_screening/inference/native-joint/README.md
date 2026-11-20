# Joint orbit positioning from complete stored native GLRT

The 512 MiB streaming receiver completed all nine attempts in 27.20 s on
CPU cores 12 and 13. The joint solver and archived exact robust solver
published the same four of five primary recordings in both calibration
arms. Joint had higher median error and a lower upper tail on those four.
It published one of three additional recordings. Both receivers withheld
the matched wrong-tile query. [Per-recording scores](scores.csv)

## Matched position results

The table gives published fixes and median, P95 and maximum geodesic error
in kilometers. The primary joint and native-lean controls matched the
complete input packet, native and causal catalogue digests, supplied tile
and rebuilt Graph digest. The four original v5 options were verified against
their frozen input and execution receipts. [Position distributions](summary.json)

| Primary method | Fixes per arm | `c0` median / P95 / max | Fitted `c` median / P95 / max |
|---|---:|---:|---:|
| Streaming GLRT with joint orbit fit | 4/5 | 1.692 / 1.887 / 1.897 | 1.323 / 1.641 / 1.643 |
| Archived native-lean exact robust fit | 4/5 | 1.424 / 3.462 / 3.779 | 1.030 / 2.924 / 3.250 |
| Original no-repair v5 | 5/5 | 0.567 / 2.070 / 2.267 | 0.689 / 2.153 / 2.389 |
| Original selective-gap | 5/5 | 0.567 / 2.070 / 2.267 | 0.689 / 2.153 / 2.389 |
| Original omitted-track-one | 5/5 | 0.528 / 2.070 / 2.267 | 0.689 / 2.153 / 2.389 |
| Original omitted-tracks | 5/5 | 0.528 / 2.070 / 2.267 | 0.689 / 2.153 / 2.389 |

DS29-0082 had the largest improvement versus native-lean, from 3.779 to
1.550 km with `c0` and 3.250 to 1.643 km with fitted `c`. The joint solver
withheld DS26-0197 on weak position geometry, as did native-lean. Its
forced joint errors were 1.884 and 1.189 km, kept as diagnostics.

The new confirmation published DS26-0231 at 0.940 and 1.008 km error.
It withheld DS26-0223 and DS29-0316 on weak position geometry. Their
forced errors were 1.635/1.832 km and 2.620/2.494 km. All four original v5
options published 3/3 on those inputs. Their case errors are in the CSV.
The separately matched DS26-0036 `r0` control had a forced error of
23.314/23.377 km for joint and 22.560/22.560 km for native-lean. Neither
published. [Locked figures](figures.json) · [Frozen requests](plan.json)

## Held decisions and resources

The primary median conditional RMS across the joint fits, including the
withheld diagnostic fit, was 179.97 Hz with `c0` and 144.64 Hz with fitted
`c`. The archived native-lean medians were 178.62 and 137.00 Hz. Primary
joint median held score was 0.570 and 0.604
in the two arms. The exact robust archive supplies its original zero-
calibration held score. Both joint arms published the same four primary
positions. Fitting `c` reduced geographic error on two and increased it
on two. Objective scores, conditional RMS and original v5 publication RMS
are distinct columns. The wrong tile's zero-calibration held score was
0.282 for joint and 0.221 for the archived receiver. Joint withheld that
case on geometry and the archived receiver withheld on held-track support.

Total per-attempt supervisor wall time ranged from 3.04 to 6.08 s. Primary
median wall and worker CPU were 5.25 and 4.94 s, including the full native
archive and Graph path. Graph and joint fit took median 2.20 and 2.02 s of
wall time on the primary roster. The maximum observed RSS and VM peak were
153,784 and 394,900 KiB. The 512 MiB address-space limit was in force before
the numerical imports. The archived native-lean primary median wall was
3.57 s from its separate earlier campaign.
[Raw worker telemetry](positions.jsonl.gz) · [Archived controls](stock-positions.jsonl.gz)

## Reproduction and boundary

The sandbox uses the exact verified native-lean deployed source inventory
and mounts the single pinned joint solver plus a qualification-only selector.
It starts from complete stored native factors and rebuilds the anonymous
tracks. Candidate imports and mount lists contain no v5 localization stack.
Both frozen implementations are byte-identical to their earlier locks.
[Source lock](source-lock.json) · [Prediction seal](prediction-lock.json) · [Native-lean source inventory](../native-lean/deployment.json)

Use the `deployed-source` bundle from the native-lean qualification.

```sh
native_joint_work=$(mktemp -d /tmp/leo-native-joint.XXXXXX)
taskset -c 12,13 .venv/bin/python -m tools.pipeline_eval.qualification.native_joint_trial \
  --work "$native_joint_work/run" --bundle /path/to/deployed-source
.venv/bin/python -m tools.pipeline_eval.qualification.native_joint_results \
  --work "$native_joint_work/run" --bundle /path/to/deployed-source
```

# What the signed orbital phase finish resolves

On DS30-0049 the optional signed phase-prior finish moved the two estimates **1.377 and 1.370 km** and increased survey error by **1,223 and 1,282 m**. The stage took **0.158 s wall / 0.158 s CPU** of the **13.600 s** raw successor process. Only **0.069 s** was the paired numerical refit. The original causal phase qualification took **0.089 s**. A free bypass would save at most **1.16%** on this worker if later stages carried the same cost. [Frozen protocol](signed-phase-identifiability-protocol.md) · [Survey-blind prediction](measurements/signed-phase-identifiability-prediction.json.gz)

| DS30-0049 arm | Ordinary east / north km | Signed east / north km | Ordinary → signed RF RMS | Ordinary → signed horizontal error |
|---|---:|---:|---:|---:|
| Fixed `c = 0` | 1.964900 / −6.586307 | 0.745999 / −5.945026 | 168.632 → 168.634 Hz | 3,249 → 4,472 m |
| Fitted `c` | 2.449091 / −6.169900 | 1.241581 / −5.523737 | 168.809 → 168.814 Hz | 2,758 → 4,040 m |

The two fits held the same node, curved mask, weights and predictive roster. Each arm had **268 conditional points across two active satellite families**, with zero predictive points. Both ordinary and signed positions were interior. The objective moved **2910.047 → 2909.958** and **2921.103 → 2921.005**. Those differences compare distinct phase-prior means. On the *same signed objective* the interpolated increase at the ordinary endpoint was **0.304 / 0.302**. Nearest axial and diagonal samples at a 0.5 km spacing gave quadratic increases of **0.293 / 0.291**. The respective two principal curvatures were **0.227 / 0.678** and **0.212 / 0.587 score units per km²**. This describes a shallow position direction. The robust variational score and grid interpolation leave the statistical coverage of that direction uncalibrated. [Endpoint and grid receipt](measurements/signed-phase-identifiability-prediction.json.gz) · [Survey join](measurements/signed-phase-identifiability-scored.json.gz)

## Fixed-support results

Deleting the optional stage would retain the ordinary accepted endpoint. The control keeps the original phase refresh, both `c` arms, inputs and support. Negative changes in the table favor the signed endpoint. RF RMS and surveyed error are distinct outcomes.

| Recording and measured route | Signed stage wall / CPU | Signed refit wall | Signed minus ordinary error, fixed / fitted | Signed minus ordinary RF RMS, fixed / fitted |
|---|---:|---:|---:|---:|
| DS30-0008 original blind saved | 2.266 / 2.266 s | 2.181 s | −26 / +9 m | −0.014 / −0.008 Hz |
| DS30-0016 integrated original | 0.119 / 0.119 s | 0.052 s | −319 / +411 m | −0.031 / −0.073 Hz |
| DS30-0049 original successor | 0.158 / 0.158 s | 0.069 s | +1,223 / +1,282 m | +0.002 / +0.005 Hz |
| DS30-0169 held saved | 0.582 / 0.578 s | 0.499 s | −128 / −87 m | −0.011 / −0.005 Hz |
| DS30-0173 blind composed saved | 0.778 / 0.775 s | 0.693 s | −123 / −111 m | +0.037 / +0.019 Hz |
| DS30-0255 conditional-refit development | 1.420 / 1.418 s | 1.338 s | −34 / −41 m | +0.002 / +0.003 Hz |
| DS30-0316 prospective saved | 0.217 / 0.217 s | 0.132 s | +222 / +214 m | −0.004 / −0.001 Hz |
| DS30-0359 composed saved | 1.179 / 1.179 s | 1.089 s | +11 / +0.5 m | +0.007 / +0.006 Hz |
| DS30-0402 prospective saved | 0.539 / 0.539 s | 0.486 s | −117 / −117 m | −0.020 / −0.016 Hz |
| DS30-0419 blinded saved | 1.018 / 1.007 s | 0.932 s | −72 / −77 m | −0.017 / −0.019 Hz |

The scan examined **914 compact repository receipts and 43 resident route files**, plus the sealed DS30-0049 publication. It found **104** scorable physical traces over ten recordings. Deduplicating identical before and after coordinates with the same support counts left **48** geometries. The signed endpoint improved both arms on 23, worsened both on 20, and split or tied on five. These geometries include repeated receiver and solver variants on the same recordings. They describe the archive and cannot estimate a population success rate. The audit keeps ordinary repair separate from the optional signed update. In the composed DS30-0163 and revised DS30-0289 examples, qualification declined and consumed **40 and 66 ms** respectively. There was no signed paired refit in those runs. [Raw checkpoint census and clock scopes](measurements/signed-phase-identifiability-prediction.json.gz)

Six physical recordings had matched, verified signed grids. Both interpolated ordinary-point penalties were below **0.50 score units** in every one, much smaller than the nominal two-parameter likelihood scale of **5.991**. That group contains DS30-0049 and DS30-0359, where dropping the stage helps both coordinates, and DS30-0169, DS30-0173, DS30-0255 and DS30-0419, where it hurts both. The geometry measure cannot safely choose a branch. The north-containing simulation also shows a distinct route effect. Its signed update moved both ordinary interior points to the search face and triggered a **2.029 CPU s** exterior check. Far-offer simulations were withheld by their recorded exterior checks. Counterfactual endpoint scores alone cannot establish the substitute geographic decision. [Archived boundary control](blind-joint-signed.md) · [Same-profile estimates and geographic flags](measurements/signed-phase-identifiability-prediction.json.gz)

## A narrower optimization to test

The released named finish starts at zero and runs five phase refreshes per arm. In six recorded witnesses the final location was already reached by the second or third refresh. The remaining refreshes still changed phase, even when their position stopped moving. They performed three objective evaluations each, including two finite-difference locations. These side evaluations account for **12/57** calls on DS30-0049, **8/77** on 0169, **8/71** on 0173, **10/61** on 0255, **8/64** on 0359 and **8/72** on 0419. This is a count of calls with an unchanged endpoint. No measurement prices their removal. [Five-refresh witnesses](measurements/signed-phase-identifiability-refreshes.json.gz)

The next saved test should keep all phase updates and shadow only the last position refreshes with a fixed-position step. Check the exact released bounded step at every proposed skipped refresh and compare the paired terminal, final phase state, objective replay, owners, geography and standard evidence. An activation guard would need to certify the existing **20 m** bounded-step test under the newly changed phase reference without paying for both side evaluations. No observed phase reference reached an exact fixed point in these refresh tails. A guard based only on repeating coordinates would therefore discard real nuisance work. The first target is DS30-0359, where the published signed refit cost **1.089 s** and the unchanged endpoint provides a measured target for numerical reuse. [Released finish witness](named_survivor_fit.py) · [Refit route](blind_joint_signed.py)

The assessment launched zero solves and read no waveforms or TLE bodies. Four component tests passed.

# Independent continuation verification

All32 expected stage receipts exist and match the frozen protocol: one injected
qualified calibration, one association, six regional final starts and24 joint
arm/stage fits across separate ordinary-baseline and candidate namespaces.
No stage reason, unexpected failure or joint fallback is recorded. All24 joint
fits independently qualify under the unchanged0.001 threshold.

The injected calibration vector equals the qualified iteration100 vector.
Original ordinary candidate checkpoints are preserved as an exact byte-for-byte
copy of iteration95's input. The original baseline regions remain present before
the recovered region is added. Both ordinary-only B7 endpoint vectors and
objectives reproduce the archived published B7 results exactly.

| Regional selection, objective plus calibration penalty | fitted-c | c0 |
|---|---:|---:|
| Original ordinary winner | 40278.537193 | 41114.976923 |
| Recovered region | 39978.255801 | 40679.871793 |
| Strict model-score improvement | 300.281392 | 435.105130 |

The recovered calibration penalty is17.975098 versus5.059426 originally. The
recovered region wins even after including this larger penalty; reference error
is absent from the ranking. Its winning regional final is independently qualified
and matches the minimum among the saved recovered starts. The unchanged
`regional_winners` policy retains the original region on ties. Regional banks
differ between old and recovered hypotheses, as allowed by the existing policy;
these margins are operational selection evidence, not a claim that all candidate
banks define an ideal common likelihood. Joint model stages are not ranked by
comparing their raw objectives with different preceding models.

Both recovered c arms share the same fitted-derived calibration, observations,
association bank, priors and search budgets. All saved c0 joint stages keep static
c and RF-time coefficients exactly zero. This remains a conditional matched-c
ablation; it is not an independently c-specific association/calibration pipeline.

The verified final errors are1.030621km fitted-c and1.927094km c0, versus the
archived55.685054km and53.945451km baseline. Both final states qualify. Reference
coordinates are used only after inference to calculate these errors. This is one
consumed diagnostic recording, not a cohort mean or independent-validation result.
Production and reserved outcomes remain untouched.

[verification.json](verification.json) records all frozen closure checks, every
original stage hash, baseline parity and score margins. The audit performs no
objective evaluation or new fit and preserves the existing report and visualization.

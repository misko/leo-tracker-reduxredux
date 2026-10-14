# Original native C: retained starts help 035, not 029

All 24 prescribed fits completed and were sealed before reference evaluation. Retaining the six original-discovery starts alongside the six broader-discovery starts improves DS21-035 substantially, but neither case reaches sub-kilometre accuracy. The same fixed union bank is used within each row below.

| Case | Six broader-discovery starts | Twelve retained starts | Selected twelve-start origin |
|---|---:|---:|---|
| DS21-035 | 181.831509 km | 48.701964 km | Original discovery, start 0 |
| DS21-029 | 83.390154 km | 83.390154 km | Broader discovery, start 0 |

The twelve-start selector shares the six newly fitted broader-discovery outcomes with the six-start selector. It has twice the total optimizer budget, not a matched-total-cost advantage. Historical original-bank fits are initializers only; their objectives are not compared against union-bank objectives. All fits retain the original native likelihood, fitted c, priors, receiver alias lifts, original 25 km per-start disks, and 20 s / 600-iteration budgets. No additional receiver clocks, reference-derived starts, or retries were introduced.

## Convergence limits the interpretation

Only 13/24 calls passed the unchanged independent stationarity rule (threshold 0.001): 035 accepted 3/6 broader-discovery and 2/6 original-discovery starts; 029 accepted 6/6 and 2/6 respectively. Process completion does not imply scientific acceptance.

On 035, the accepted twelve-start winner has objective 37175.311163 and NLL 36754.801319. Rejected original starts 4 and 5 have lower objectives 33748.738864 and 34659.580608, but stationarity residuals 100.208 and 3587.626. They remain ineligible. A separate, strictly retrospective evaluation after the complete seal places them at 9.776774 and 10.857261 km. This identifies a consequential optimization limitation; it does not establish a valid lower-error estimator. Rejected broader starts also score below the accepted six-start winner.

On 029, broader-discovery start 1 is stationary and retrospectively 5.202842 km from the configured reference. It loses training selection to the 83.390154 km winner: its objective/NLL are 38357.757934/38116.291616 versus 33034.867925/32763.644261. Thus this case is not explained solely by missing near-position starts, convergence failure, or the prior penalty. The native likelihood itself strongly favors the inaccurate fitted state. No candidate was selected or restarted using reference error.

## Historical context, not matched union half controls

On the historical broader-discovery bank, C-all errors were 177.317260 km (035) and 100.198781 km (029). Their CH1–4 / CH5–8 errors were 172.393269 / 101.895985 km and 85.926334 / 74.417039 km respectively. The original-discovery 035 full result was unavailable, while its half errors were 3.675677 / 10.737019 km. These use different candidate banks and are contextual comparisons, not controlled union half-view experiments. Preservation alone does not satisfy the combined-band performance requirement.

## Evidence and validation

Output namespace: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-c-union-control-v1`.

- Global 24-call terminal SHA256: `b418c5483861d572b5e4e71777e611daa3874668b335f865f828556192689316`.
- Final seal SHA256: `703963cd406ea7889dca731ab093e413de5ffe5953dfc7047f5153c99826d535`.
- Selected development evaluation SHA256: `464af9deb1d22722cfe8dea9bc456e4b877c966f27adba04f1bf41be06211569`.
- `call-errors-postseal.json` retains all 24 outcomes, including rejected fits, with explicit diagnostic-only interpretation.
- Wrapper source `bd014cfe2`, shared immutable control through `1d7cb8657`, postseal evaluator wrapper `090b633cf` and shared evaluator `6c68fc4ef`.

All four six-call units returned successfully. The first unit took 141.17 s; the remaining three-unit sequential wave took 414.09 s including process overhead. Numerical execution used one research worker with one BLAS thread. Native transport and adapter tests passed; postseal selection and retrospective-report guards are tested. The configured-reference comparison followed semantic replay of the complete seal. Locked cases and held observations were not used.

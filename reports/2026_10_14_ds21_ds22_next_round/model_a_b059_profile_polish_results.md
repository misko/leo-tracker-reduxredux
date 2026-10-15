# B059 fixed-profile numerical repair and complete-state release

The new strict training-selected full estimate is **1.086405 km**, versus the retained earlier free-release incumbent at **1.210448 km**. Both numerical methods repair the previously rejected high-position fixed profile. All four accepted profiles were then continued freely; three continuations pass strict acceptance. The numerical repair helps eligibility and finds a lower training score, but the full estimate remains above 1 km.

| Source endpoint | Fixed numerical method | Fixed J | Fixed KKT | Actual objective calls | Numerical seconds |
| --- | --- | ---: | ---: | ---: | ---: |
| Accepted low profile | SLSQP repeat | 28046.655844 | 0.000148104 | 13 | 0.133 |
| Accepted low profile | Positive-Hessian finish | 28046.655844 | 0.000148104 | 268 | 2.321 |
| Rejected high profile | SLSQP repeat | 27757.972556 | 0.000738037 | 33 | 0.350 |
| Rejected high profile | Positive-Hessian finish | 27757.972556 | 5.72e−9 | 269 | 2.262 |

The high source originally reported KKT 0.008014186 and solver success. The independent zero-fit replay preserves that rejection. Both fresh methods restore eligibility, so this is not an exclusive Newton benefit. The positive-Hessian certificates have minimum tangent eigenvalues 0.404258 (low) and 0.323491 (high), positive unregularized Cholesky pivots, explicit active affine constraints, and no tolerance relaxation.

All four fixed outcomes sealed before any free call. Every accepted fixed endpoint supplied its complete vector and clock/group/q nuisance state to the same SLSQP continuation port, preserving the original 25 km disk and fitted-c model:

| Fixed source/method | Free J | Free KKT | Accepted | Configured distance km |
| --- | ---: | ---: | --- | ---: |
| Low / repeat | 28046.376437 | 0.000052666 | yes | 1.210447 |
| Low / positive-Hessian | 28046.376437 | 0.000052840 | yes | 1.210448 |
| High / repeat | 27740.428782 | 0.576300 | no | 1.089632, diagnostic only |
| High / positive-Hessian | 27740.435446 | 0.000724742 | yes | 1.086405 |

Selection retains both historical accepted free incumbents and all accepted new free outcomes. Fixed-position acceptance excludes geographic coordinates and therefore does not by itself qualify a profile as a full-position optimum. The fixed high geography is 0.468524 km from the configured reference; allowing geography to move 1.492564 km lowers its objective by 17.537110 while worsening configured distance. Better in-sample score is not evidence of improved localization. The failed free-high-repeat outcome has slightly lower J than the selected endpoint but remains unavailable; its large KKT does not justify calling it a roundoff-only failure.

Separately, the training frequency likelihood NLL improves from 27707.170952 at the earlier free-release incumbent to 27434.250734 at the new selector; its prior penalty falls from 339.205485 to 306.184712. Those score changes are distinct from the modest configured-position improvement above.

There were eight new numerical calls (2170 actual objective evaluations total), eight independent returned-endpoint objective audits and eight zero-fit qualification objective evaluations. Each numerical call retained 20 seconds and a **600 actual objective-call** cap including Hessian finite differences; this is explicitly stricter than the historical source's 600 optimizer-iteration cap. All source endpoints, the original full incumbent and the earlier free-release incumbent were replayed before fitting. Search cost is additional endpoint work, with no equal-total-budget or cohort-wide promotion claim. Original failures remain unchanged.

Source `e240258d5`; four driver tests plus numerical-port regression tests and Ruff passed. Genuine parent: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-b-half-xy-profiles-059-v1`. New namespace: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-b059-profile-numerical-control-v1`. Global scientific seal `d54b161d43bccedee6b9b88982b0fec414f6f0e4baa8deadb6b4ba3cc87433e8` preceded configured-reference access. No held observations or new RF data were used.

# DS21-007 complete fitted-only initialization

DS21-007 now has six shared physical proposals for each of CH1–8, CH1–4 and
CH5–8. The complete discovery → fitted shape → fresh bootstrap → absolute
hybrid → cold bootstrap → physical export chain has passed cached validation.
This is initialization readiness, not a final model or position-accuracy result.
Neither held observations nor reference coordinates were used.

| Stage after shape | Prescribed calls | Outcome | Elapsed seconds |
| --- | ---: | --- | ---: |
| Fresh shape bootstrap | 9 | All complete; candidate union grows 28 → 32 | 21.101 |
| Absolute hybrid | 9 | All stationary, fitted c | 27.105 |
| Cold bootstrap | 9 | All complete; fixed 32-satellite pool | 17.668 |
| Six physical proposals | 0 optimizer calls | Six exports for each of three views | 16.842 |

The earlier [discovery](DISCOVERY_007_RESULTS.md) used the causal 970-satellite
bank; the [shape stage](SHAPE_007_RESULTS.md) supplied the three fitted-only shape
parents. The new adapter preserves the original fresh candidate union and donor
order, cold bootstrap mapping and nearest fresh all-view timing fallback.
Coincident sources retain their identities. Hybrid fitted coefficients are
required parent evidence but do not replace the original physical seed exports.

All nine hybrid fits were stationary. Selected training objectives were
34,755.747768 for CH1–8, 21,117.195749 for CH1–4 and 14,300.647652 for CH5–8;
these different-evidence scores are not comparable position errors. Physical
frequency-correction closure was at most 1.4552e-11 Hz for all-band exports
and exactly zero at reported precision for both half-band exports.

The adapter's 13 owned tests passed in the worker (88.06 seconds) and integration
(84.29 seconds) runs. They cover the original numerical ports, full synthetic
chain parity, an actual tiny fitted-c hybrid optimizer, physical export closure,
checkpoint reuse, failed/orphan calls and source/ancestor tampering. Every stage
archived 317 source files and preserved the successful discovery/shape sources.
Bootstrap/export slices had 90-second internal limits; hybrid had 240 seconds.
No slice required continuation or retry.

Implementation commit: `50e0b852d`. Local namespaces are under this report
directory's `local/`:

| Namespace | Protocol SHA-256 | Terminal SHA-256 |
| --- | --- | --- |
| shape-bootstrap-007-v1 | a852fcaff37b21747c9a7ed32d39303f33fa98c334bd55f4a61c7b6f43b3a90d | 4a11ede9e1a184788ba76e7a15468d2fa22e0a517a71ac3ee6b28268642ecc96 |
| hybrid-007-v1 | a509cd0c13b8e96ef1df2c37c5e772fd9c566e25e0d697f903f6181caec3c6d4 | c1c9223a8962fc1e3cfa614542bc895811d99ac50c60582fba808cfae58e907a |
| cold-bootstrap-007-v1 | cfbe6ec99b9dd7a4fd7770e75e7ddf9ce93f6559dfcc0dd921e1ae0f82af52f9 | c35722c90fb3c2d75cc58e874b96bd15c3884d22aa3683af35a27518495fc5a7 |
| six-proposals-007-v1 | c8ee4041d3bac83f59533af369ea262d60c8a4cd1efafa727bc34c5fd816f5e5 | 3f795bd7c224320f885f3a36c875db3bb689f48c18031a0623b24ff9dfff7cee |

Six of the 34 fast development recordings now have complete proposal artifacts;
28 still need initialization. DS21-007 still needs the final shared-proposal
model comparison. The five-case fixed-alpha transfer is a separate experiment
using the five historical recordings; its results remain pending. No full-DS21
accuracy or release claim follows from this milestone.

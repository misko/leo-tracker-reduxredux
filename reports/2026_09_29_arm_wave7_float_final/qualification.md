# Qualification decision

V1 is rejected for speed on Cortex-A9. It retained all 119/119 hits in the
measured ARM panel but increased total time from 863.029 ms to 893.340 ms and
GLRT time from 88.78 ms to 119.40 ms.

V2 is scientifically and physically qualified as a marginal improvement. It removes
V1's per-sample trigonometry, passes the strengthened FP64 oracle tests, retains
834/843 on host32 and 19,217/19,581 on host704, and has zero full-cohort hit
identity losses or gains. The matched Cortex-A9 ARM4 run retained 119/119 hits
and all 182 emitted objects. Total time was 856.661454 ms versus 863.029 ms
(0.74% lower), and GLRT was 82.485837 ms versus 88.78 ms. It remains an
approximate path and its speed gain is small.

Evidence is in `host32-v2b/standard-audit.json`,
`host704-v2/standard-audit.json`, `hit-identity-diff-v2.json`, and the receipts
under `builds-v2/`. The earlier `host32-v2` predates the JSON precision-label
fix and is retained as historical evidence; `host32-v2b` binds the final source
and receipt.

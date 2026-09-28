# DS7 association/search smoke execution

Status: **local control qualified; multibasin stopped at the predeclared runtime limit**. No reference coordinate, pose, error, or score was read or computed.

The Direction A pinned-oracle audit passed before launch. Both Direction E arms consumed the same sealed `single-001` inputs, final baseline adapter SHA-256 `221ddff51a37f45e73fc420c3ef769e2943e6667f31e10bcc6fa6fd56e7fa43e`, candidate bank, normalized 11.2 GHz measurements, objective, bounds, and total 180-evaluation allocation.

The local wrapper completed in 29.59 seconds using 42 evaluations. All three starts converged to the same interior basin. Its winning objective was `-10129.739009069435`, exactly equal to the sealed baseline replay, with the identical east/north/timing state `[3.705984977262451, -1.9755568160870454, -0.2772259707590678]`. This qualifies the direction-owned transport, objective reuse, second-start winner selection, and compute accounting.

The first multibasin attempt failed before optimization because its arm file omitted two timing-grid values. The runner retained that sealed failure at `smoke-multibasin-v1`. The defect was found without reference information, repaired by restoring the exact 41-value grid, and covered by a regression test. The unique retry `smoke-multibasin-v2` then reached the fixed 60-second subprocess limit without producing a response. The runner retained a sealed `TimeoutExpired` failure at 60.00 seconds. The declared budget was not widened, and there is no multibasin objective or estimate to compare.

The timeout exposed a separate cleanup defect: because the adapter was launched through `sudo`, its privileged process survived the runner's process-group termination. The coordinator identified and killed only the direction-owned PID after 88 seconds; no other process was touched. A subsequent audit confirmed that the PID is absent and all three run seal inventories and seal-file SHA-256 values remain unchanged. Both checked-in arm files are now returned to `planned` status. They cannot run again until `sudo` is removed or an internal privileged deadline is added and descendant cleanup is re-audited.

Synthetic controls passed before real execution. Reordering complete candidate mixture rows changed log likelihood by exactly zero, confirming that a label permutation is only an invariance test. Reversing candidate trajectories over observation time reduced injected-data log likelihood by `41.51126234635748`, exceeding the frozen 10-unit requirement and establishing a meaningful physical mismatch control.

The scientific decision is **stop under the current smoke budget** for multibasin search. Local search is deterministic, converged, interior, and matched to the baseline. Multibasin search is unqualified because it did not return complete accounting or a result within 60 seconds. The execution path also requires cleanup repair before any future compute. Any later attempt needs a newly frozen, explicitly smaller start/evaluation design or a separately authorized runtime budget plus a safe timeout mechanism; this run cannot be repaired or interpreted as evidence of improvement.

## Sealed evidence

- Local seal SHA-256: `642c3eb6e1834a6b0eda48a71363292283626fda1a8f34f15e04d6a07024bfcc`
- Initial configuration-failure seal SHA-256: `b67a45e1c14e16a0bf22fd065ae4d315999e78051d3e38e5946562c59f149647`
- Multibasin timeout seal SHA-256: `b8d95bfd0f8f35d9c39b3c0f137e9c084d6c83fcec6fef89a8986ebaa0ddb83b`
- Pinned-oracle audit SHA-256: `818bb2aa036311f419a5818649b0bb7e39b25adafb0bd2ff478d46b36d91e1f7`

# DS22-059: the added basin exposes a band tradeoff, not an active disk limit

The training-selected added northwest basin loses to the retained full winner by 72.210635 objective units. Exact decomposition shows its low-band likelihood improves while its high-band likelihood worsens. Both full endpoints are well inside their own 25 km disks, so the prespecified outward-boundary screen does not support radius expansion from these endpoints.

| Component | Full winner, original start 2 | Added quadrant start 6 | Added minus winner |
|---|---:|---:|---:|
| Low-band NLL | 26863.144684 | 26547.461022 | −315.683662 |
| High-band NLL | 19431.189885 | 19907.849636 | +476.659751 |
| Common timing prior | 0.048441 | 0.134552 | +0.086111 |
| Relative timing prior | 640.101407 | 454.355522 | −185.745885 |
| Common clock prior | 157.785440 | 254.681592 | +96.896152 |
| Group prior | 0.406156 | 0.404324 | −0.001832 |
| Total objective | 47092.676013 | 47164.886647 | +72.210635 |

The full winner lies 4.236702 km from its center (50, 150); the added state lies 1.102100 km from (−50, 50). Radial geographic derivatives are −8.956e-5 and +8.749e-8; tangential gradient norms are 7.174e-5 and 5.349e-6. Neither satisfies the 1e-6 km boundary-distance gate, so no outward finite differences or radius fits were attempted. This does not establish that the entire discovery geography is adequate.

The separately optimized selected half states originate from the same added coarse basin. Their own NLLs are 26121.239908 low and 19476.850130 high, versus 26547.461022 and 19907.849636 at the full added endpoint. Full calibration and satellite timings still cannot reach both separately preferred scores at this stationary state. These differences are descriptive across optimized states; they do not isolate clock priors as the cause or prove a new calibration model would improve localization.

All four states use the same 61-satellite union. Existing exact wrapped likelihood and prior accounting were replayed; the source saves physical vectors, nuisance vectors, timing components, per-channel/per-receiver scores, and signal masses for subsequent training-only diagnosis. No reference or held observations were read, and no fit was performed.

Source `88f48d741`; six objective evaluations, zero optimizer fits, 85.459 seconds including genuine reconstruction of all three view frames. Internal cap 120 seconds, external TERM/KILL 135/140 seconds. Six component tests passed, including real likelihood accounting tests and geometric boundary-screen tests.

Receipt: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-059-quadrant-audit-v1/report.json`, SHA256 `0f69a938e4699a7724c55c5beb82a5eea5db033f3b5aa63dc03f6f5040d10a05`. Parent control is the sealed 27-call [quadrant experiment](DS22_059_QUADRANT_RESULTS.md). No model promotion or accuracy claim follows.

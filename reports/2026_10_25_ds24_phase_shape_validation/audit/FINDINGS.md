# Independent phase/shape audit

Preflight and terminal review pass. The scientific branch completed all 32
declared new fits; **30 qualify under the original gates**. All completed
endpoints, including both gate failures, enter the 16 paired four-cell
factorials. There was no audit position fitting or orbit propagation.

The [preflight](synthetic_preflight.json) binds protocol
`1d238c4434d478be51cd9214be5ca58c4978882d3a8c297503212d3ad2eaa5e1`.
Its 1,276 saved-array/source/hash checks include an independent rerun of the
six producer tests. The source changes only generating phase or shape:
phase removal retains every original shape coefficient and recomputes nonlinear
Doppler and the physical-mode design at the changed true phase. Inference
starts at zero phase references and receives unchanged priors and observations,
without access to the generating truth. Original full and both-removed controls,
noise/Gamma draws, source constants, aliases, IDs, masks and c-arm observation
pairs match their archives. The 32 saved forward closures pass at 1e-7 Hz.

The [terminal audit](synthetic_terminal_audit.json) contains 5,719 checks of
sealed files, every new result, raw residual threshold/cascade decisions,
16 c-arm input pairs, all four-cell vectors, norm and squared-norm contrasts,
and aggregate summaries. It uses saved replay statistics; it does not repeat
propagation, visibility evaluation or optimization. The producer's fixed
geometry gate replay is hash-bound rather than independently propagated again.

| Generating cell | Mean error c=0, km | Mean error fitted c, km |
|---|---:|---:|
| Phase draw and shape present (`11`, reused) | 0.460013 | 0.468903 |
| Phase draw, shape zero (`10`, new) | 0.402261 | 0.405434 |
| Phase at causal mean, original shape (`01`, new) | 0.396955 | 0.402628 |
| Phase at causal mean, shape zero (`00`, reused) | 0.295396 | 0.296559 |

Removing phase at original shape improves these means by 63/66 m; removing
shape at original phase improves them by 58/63 m. Combined removal improves
them by 165/172 m. Thus this small common-draw panel supports contributions
from both generating components; it does not establish phase-only dominance,
a real-data prior change or a localization precision floor.

The exact gate failures are `shape_zero`, DS24-0010/site1/stochastic_seed0,
both c arms, RX2 CH4 T004: 37 observations, profile/conditional slope z
3.122881 and 3.127226 against the unchanged threshold 3. All phase, Gamma
and regional bounds pass. These are scientific gate failures, not runtime or
numerical-replay failures, and are not silently removed from the averages.

The interaction is independently computed as `g11-g10-g01+g00` for each
error vector, error norm and squared error. Mean norm interaction is about
−0.043807/−0.042600 km in the two c arms. A vector interaction can be zero
while norm/squared-error interactions are nonzero: vector addition alone
already produces scalar cancellation or reinforcement. The independent
[math tests](test_audit_math.py) demonstrate this and verify the squared-error
identity, so the scalar contrasts are not treated as pure estimator
nonlinearity.

There is also an actual generating interaction before fitting:
`y11-y10-y01+y00 = [B(phi_draw)-B(phi_causal)] z`.
The [preflight's per-realization records](synthetic_preflight.json) distinguish
complete archived-vector RMS, 2.70–25.05 Hz, from likelihood-row RMS,
2.69–25.95 Hz. Maximum native-row interaction is 113.56 Hz. Common receiver,
source-constant, measurement-noise and alias contributions cancel. Therefore
endpoint interactions combine physical design coupling with estimator response.
Only eight draws on two scan geometries were tested; no significance or
general population claim follows.

The producer completed the fit batch in 58.36 s and the fixed replay within
200 s of first preparation, including review wait, under the original 600 s
deadline. Every frozen scientific/report hash checked unchanged. The source
and numerical kernels retain their stated VI/local-phase, Gaussian predictive
and linear physical-mode approximations; association and alias selection were
not simulated. No operational ALGO or real-data improvement is established.

[preflight.py](preflight.py), [terminal.py](terminal.py) and
[audit_math.py](audit_math.py) are the independent audit sources. The separate
[identity falsification design](IDENTITY_FALSIFICATION_DESIGN.md) explains the
small input adapter and parent-generation limitations that must be resolved
before testing the full catalogue nomination process, rather than only a
handpicked incorrect label. No such test was run here.

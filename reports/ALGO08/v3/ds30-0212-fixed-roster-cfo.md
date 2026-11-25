# DS30-0212 CFO-only final fit on the ordinary roster

The ordinary replay exactly reproduced the published endpoints and the full
selected likelihood witness in both arms. Applying the same 153 CFO edits
inside that fixed fit moved the endpoints by **39.34 m fixed** and **59.03 m
fitted**. The fixed-support hypotheses reduced RF RMS in both arms.
The original paired publication gate rejected them. [Frozen protocol](ds30-0212-fixed-roster-cfo-protocol.md) · [Sealed physical comparison](measurements/ds30-0212-fixed-roster-cfo-score.json)

| Calibration | Ordinary error | CFO-only fixed-roster error | Rebuilt corrected error | CFO-only error change vs ordinary | Rebuilt error change vs CFO-only |
| --- | ---: | ---: | ---: | ---: | ---: |
| `c = 0` | 1,068.12 m | 1,060.78 m | 1,085.62 m | −7.34 m | +24.83 m |
| Fitted `c` | 977.18 m | 983.94 m | 1,011.31 m | +6.76 m | +27.37 m |

The CFO-only hypotheses were 50.94 m and 50.00 m from the respective
rebuilt corrected endpoints. The fixed-support change had the opposite
sign of the final regression at `c=0`. It extended in the same direction
with fitted `c`, where the rebuilt result was a further 27.37 m worse
in surveyed error. These are condition-specific comparisons. The
ordinary-to-rebuilt difference can reflect all downstream changes in
Graph, support and fit state. The experiment does not separately identify
the contribution of the 12 removed owners or three changed residual roles.
[Sealed ordinary and rebuilt controls](masked-cfo-next-two-results.md)

The genuine ordinary fit was captured at `named_survivor_fit.fit_pair`.
Its unchanged control reproduced both endpoints, both 1,895-row
likelihoods, their ordered within-track identities, roles, NORADs,
aliases, noise, priors, optimizer traces and fit fingerprints. The
treatment applied all 153 signed physical CFO changes to detached
ordinary tracks, preserving integer Graph winding. Exactly 152 affected
owners entered each fitted arm. The paired solver used the same masks,
weights, signed means, predictive roles, 25 km offer and zero-start
phase refresh. Conditional RMS decreased from 184.98 to 181.61 Hz and
from 184.87 to 181.48 Hz. Both fitted positions were finite and inside the
12.5 km half-width, and the final phase updates stayed below 0.01 s.
The released gate therefore failed on track compatibility. The retained
fit witness cannot identify the failing track. These diagnostic
positions would require further scientific handling before publication.
[Genuine refit records](measurements/ds30-0212-fixed-roster-cfo-refits.json.gz)

The one RAM-only numerical child exited zero in 8.091 s from namespace
launch through exit. Worker CPU was 7.48 s from inside the namespace.
The unchanged and edited paired fit calls took 0.373 and 0.397 s wall,
excluding their separate likelihood witnesses. The rest was the genuine
ordinary fit capture from the already staged inputs. No new grid, PNGs,
published terminal, backing waveform reads or raw timing were involved.
The survey was joined on CPU3 only after the diagnostic sealed. A
reverse comparison would have required a second actual corrected
pre-finish capture and was outside this one-child measurement. Eleven
focused tests passed. [Execution seal](measurements/ds30-0212-fixed-roster-cfo-seal.json)

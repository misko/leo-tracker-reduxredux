# What rescue still costs on the current fast solver

The current DS30-0402 path no longer pays the three rejected named-v3 reassignment fits that cost 31.96 CPU s. It paid one useful isolated rescue and an endpoint trim. The exact fine-salvage change tested here saved **0.118 CPU s** across the current solver's 20 fine calls. It preserved the adopted rescue, endpoint trim, final signed pair, all 4,821 ordered owners per arm, both endpoints and RF residuals, and all eight published PNGs. [Frozen protocol](rescue-phase-prepare-protocol.md) · [Exact measurement](measurements/rescue-phase-prepare-0402.json.gz) · [Historical named reassignment](named-roster-0402.md)

## Available work on the fast path

| Current saved receipt | Ordinary coarse/fine salvage CPU (s) | Isolated rescue | Isolation CPU (s) | Cold discovery CPU (s) | Completed cold finalists / monitored fitting CPU (s) |
|---|---:|---|---:|---:|---:|
| DS30-0402, named 20 ms packet | 0.988 | One attempt, adopted | 0.286 | 6.875 | 3 / 3.266 |
| DS30-0374, named 20 ms packet | 0.901 | Admission only | 0.002 | 3.960 | 3 / 1.501 |
| DS30-0008, mixed 20/12 ms packet | 2.125 | One attempt, reverted | 0.678 | 5.808 | 1 / 1.367 |

DS30-0402's accepted isolated attempt moved the fit onto a valid larger roster. It also paid 1.093 CPU s for the associated predictive and paired work, including the 0.355 s shared endpoint trim. The ordinary successful pair is within that scope and would still need to run on a different route. Accounting for all 1.093 s as avoidable would double-count necessary work. DS30-0008 grants at most 0.678 s of recorded isolation time to a perfect early rejection of its failed attempt, before charging any certificate. DS30-0374 had no provisional fit to skip. Cold discovery remains larger than any paid rescue here. The prefix gaps on DS30-0402 and DS30-0374 fell short of the existing separation margin. Both cases completed all three original finalists. The difference between cold total and the recorded prefix/finalist clocks also includes preparation, ranking and bookkeeping, so it is an upper limit on a ranking-only optimization. [Accepted rescue](isolated-salvage-0402.md) · [0374 transfer](named-final-0374.md) · [Dense mixed transfer](mixed-named-finish-0008.md)

## Exactly matched fine-salvage work

The released fine search repeats a shortlisted satellite's causal knot rows 121 times to select its phase slot. At one original track the knot index, interpolation fraction, Earth rotation and phase order are shared by every shortlisted satellite. The patch computes those tracks' operands once and gathers each satellite's two original knots at those same positions. The underlying orbit interpolation, CFO and elevation projection, feasibility certificate, original conditional scores and alternative ordering use the same arithmetic. Unsupported phase bindings or input domains use the original path.

| Same-track matched scope | Current certified implementation | Prepared implementation |
|---|---:|---:|
| Whole fine calls, CPU (s) | 0.464560 | 0.346493 |
| Whole fine calls, elapsed (s) | 0.464802 | 0.346612 |
| Fine proof and preparation, CPU (s) | 0.404349 | 0.286299 |
| Original profiles and screen, CPU (s) | 0.055489 | 0.055472 |

Ten tracks ran control first and ten ran candidate first. All 20 ordered alternative lists and support counts matched. Both variants examined 12,575 support trials, rejected 11,119 by the original interval, skipped 652 by existing length dominance, performed 804 exact profiles, and reached the noise screen 136 times. The candidate prepared 20 track-phase grids for 603 shortlisted satellite projections with zero fallback. It avoided **1.173 GB of logical replicated array writes**. That figure counts allocations and does not measure DRAM traffic or peak RSS. No nonlinear position fit was skipped. The improvement is 25.4% of this exact fine scope and about 0.45% of the earlier 26.065 s fast solve if every other stage cost is held constant.

## Adoption and measurement boundaries

The completed saved publication reproduced the prior terminal digest and 4,821 ordered owners in each arm. Fixed and fitted `c` RF RMS remained **100.672203 and 100.576460 Hz**. The normalized numerical grid and path matched exactly, and all eight figures reproduced their file and decoded-pixel digests. One signed handoff ran with waveform and original manifest access denied. The shadowed process took **25.943 s elapsed / 25.930 CPU s**, with **22.328 CPU s** inside the complete solve. The process includes the original fine operation on every track for validation. Other stages and sessions vary, so only the within-solve matched fine clocks establish a saving. The first worker attempt spent 0.091 s before an isolated import failure and started no numerical solve. The corrected worker ran one saved solve, with zero filesystem input blocks.

Timed candidate source `b3a83e16d`. Uncompressed result SHA-256 `880477926cf3b994645a6db7fb68fa0aa25d39ad019df7da3acb7a0c4eb05142`. Run `rescue_phase_prepare_trial.py launch` under the recorded Gauss slot with the original staged DS30-0402 assets and a fresh tmpfs root, then `rescue_phase_prepare_score.py` as the output owner. Sixteen component tests passed across the new exact interpolation, original certified salvage and isolated rescue suites.

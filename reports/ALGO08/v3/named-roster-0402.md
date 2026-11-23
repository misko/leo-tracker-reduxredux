# Rejected cavity fits dominate the named DS30-0402 solve

Named DS30-0402 spent **31.963 CPU seconds** fitting three cavity configurations that all failed the paired gates. DS30-0155 made no cavity offer. The 0402 post-nomination cavity policy accounts for **67%** of the 47.556-second difference between the two measured selection scopes. One rejected constrained rescue ran ten SLSQP phase fits and took **21.261 profiled wall seconds**. Initial ranking and screening together account for **3.821 CPU seconds** of the difference. [Frozen protocol](named-roster-0402-protocol.md) · [Sealed stage, exit and science receipts](measurements/named-roster-0402.json.gz) · [0155 accounting](named-roster-0155.md)

## Disjoint CPU through the selected evidence call

| Installed named operation | DS30-0155 CPU s | DS30-0402 CPU s | Difference s |
|---|---:|---:|---:|
| Prepare native inputs, convert and build two scan contexts | 4.296 | 4.753 | +0.458 |
| Rank original discovery assignments | 4.503 | 5.537 | +1.034 |
| Fit the screened winner | 0.743 | 3.530 | +2.787 |
| Conservative paired gates and recovery | 3.923 | 8.385 | +4.461 |
| Family/history policy and predictive fit | 3.324 | 6.493 | +3.169 |
| Signed history context | 0.072 | 2.178 | +2.106 |
| Held-family nomination | 3.692 | 5.275 | +1.583 |
| Paired cavity policy after nomination | — | 31.963 | +31.963 |
| Other between measured ports | 0.105 | 0.101 | −0.004 |
| **Preparation to selected evidence** | **20.659** | **68.215** | **+47.556** |

Both initial screens ran six initial and three finishing phase fits. 0402 reproduced the exact three screened scores and original zero-based **rank 1**. Its two initial conservative gates still ran six actual arm fits, with a separate salvage seed. The conservative `fit_and_gate` calls took **6.210 CPU s** and salvage took **1.966 s**. History used **2.193 s** for curved policy and **2.526 s** for the two predictive refits. Signed history spent **2.098 s** in two actual refits. The 0155 signed context ran without a refit. [Ranking and stage call sites](../../../tools/pipeline_eval/variants/v5_core.py) · [Original named and cumulative publication](prospective-0402-solver.md)

## Why the cavity ran so long

The original held-family nomination supplied these three complete hypotheses. Each used the unchanged common mask and both calibrations. The installed cavity adopted none of them, and both baselines had exactly zero objective replay difference.

| Original offered family change | Constrained rescue | Final failed tracks, `c = 0` / fitted `c` | Adoption |
|---|---|---:|---|
| 66203 → 63143 | Yes, five phase fits per arm | 2 / 2 | Rejected |
| 67427 → 56420 | No | 1 / 1 | Rejected |
| Both replacements | No | 2 / 2 | Rejected |

The three `fit_configuration` calls used **31.886 CPU s**. The nested wall profile assigns **21.261 s** to the one constrained rescue. All **401** `gate_slacks` calls together used **12.650 s**. Of these, **393** were unique inner SLSQP visits costing **11.750 s**, six admitted or excluded rescue across the three paired trials, and two replayed final constrained gates. Each call tested 85 curved supports twice and 39 predictive supports once. The original noise wrapper was invoked **83,809** times, including **82,137** inner calls, and charged **8.491 s** inclusive. The captured failure occurred after doing the work needed by the stock acceptance rule. A label-based decision to avoid it would remove that rule. [Proposal and jointly valid pair policy](../../../src/leo/analysis/localization_v3/family_cavity.py) · [Constrained feasibility and final replay](../../../src/leo/analysis/localization_v3/feasible.py)

The likelihood trace charges **16.698 CPU s** to **1,704** original calls before selected evidence. The three candidate configurations consumed **6.662 s** of that subtotal. The native port reported **239 unsupported layouts**, with no positive, ill-conditioned, memory or nonfinite fallback. Those calls cost **8.051 CPU s** across four shapes. The cavity's 4,150-row, 236/237-column shapes account for 160 calls and 4.572 CPU s. The conservative gate's 4,494-row, 234/235-column shapes account for the other 79 calls and 3.479 s. These costs are a separate implementation opportunity inside the already counted stages. The unsupported status leaves the private widths and compatibility with the earlier wider backend unresolved. Six further likelihood calls belong to selected-evidence verification outside the selection CPU table. [Native fallback port](../../../src/leo/analysis/localization_v4/native_bound.py) · [Earlier wider-layout results](../single-core-2x/solver-wide-private-blocks.md)

## Exact next target and bounded measurement

The prepared SVD screen already exists in the released payload as a research module. Named v3 reaches the original `feasible.py` (`a9c5857f…`) and all 83,809 calls reached the original noise screen. The old overlay requires a different phase-release donor (`86922fff…`). That overlay replaces least squares with an orthonormal projection and replays stock near BIC boundaries, on rank ambiguity, and for final gates. DS29-0247's constrained CPU went **42.02 → 38.45 s** but its whole service CPU went **128.72 → 130.67 s**, and the published coordinates moved by up to **0.46 µm**. DS29-0357's constrained CPU went **12.12 → 8.99 s** with exact published science and changed optimizer visits. Applying the old overlay to 0402 would affect the 82,137 inner calls. The eight entry and final gate passes would still run stock. [Earlier overlay and independent holdout](../../2026_11_19_receiver_screening/acquisition-support/fit-work/README.md) · [Old source-bound overlay](../../../tools/pipeline_eval/qualification/fit_work_bundle.py)

The new unit variant preserves the original NumPy `lstsq`, its residual and BIC calculation, and every comparison. It prepares time-only vector norms, the three-column design and split scales once per exact track support. Within a screen it reuses the same computed mean for variance and lag statistics. A frozen sample used 12 supports of 12–113 observations from the real 0402 named ownership and original graph track times. Its residuals were the actual saved detector frequencies after subtraction of their quadratic fit. All six diagnostic fields, including the pass flag, matched bit for bit. Over three batches of 2,400 calls per mode, median CPU was **58.143 → 37.084 µs per call**, and preparing the twelve supports cost **0.185 ms**. Multiplying the unit saving by the 82,137 inner calls and charging 124 preparations gives **1.728 CPU s** if the rate transfers. This unit sample did not recreate constrained orbit-fit residuals, optimizer visits or whole-solver timing. [Unit protocol](exact-noise-gate-0402-protocol.md) · [Screen implementation](exact_noise_gate_0402.py)

An exact next change can pair the prepared screen with a constrained-only white profile. `gate_slacks` spent **1.616 s** in `profile` and **0.522 s** constructing diagonal whitening. Its curved gates consume the original integer alias, fitted bias, innovations and RMS. Its predictive gates consume the same fields with their existing 300 Hz bias prior. Neither reads the Gaussian `cost`. Bind each exact mask and time vector to its white diagonal and normalization, keep the original array layouts and operation order for the consumed fields, and omit construction of the unused cost. This is a distinct, nonoverlapping **2.138 s measured wall boundary**, with necessary arithmetic still to be charged. At least **1.272 s** must come from that boundary to reach a three-CPU-second combined saving at the unit rate. Exact emitted gate vectors and accepted SLSQP paths are the qualification target. [Stock profile and whitening](../../../src/leo/analysis/research/retained_track_likelihood.py) · [Original gate consumers](../../../src/leo/analysis/localization_v3/feasible.py)

## Science and scope

| Calibration | Archived horizontal error | Reproduced RF RMS Hz | Conditional / predictive owners |
|---|---:|---:|---:|
| `c = 0` | 0.863651 km | 100.672203 | 4,150 / 671 |
| Fitted `c` | 0.860302 km | 100.576460 | 4,150 / 671 |

The named diagnostics reproduced both original coordinates, frequencies, all 4,821 ordered owner rows per arm, and owner-role linkage to their executable likelihoods. The worker used the exact saved 20 ms packet, offer and 48-snapshot causal archive. It took **68.772 CPU s** from the wrapper to the selected-evidence hook, **0.366 s** to reconstruct and check its selected observations, and **70.072 CPU / 70.106 elapsed s** through exit. This profile excludes grid and figure generation and incurs instrumentation overhead. The earlier complete named replay took **68.774 CPU s** in its numerical solve including grid, and cumulative took **20.405 s** while returning 141 fewer owners and about 90 m more error per arm. The exact screen ran as a bounded unit sample only. Eighteen component and adjacent tests passed. The sole saved profile was frozen at `ac673b9c1` and the unit screen at `ecedc72b8`. [Prior complete publication](prospective-0402-solver.md) · [Saved profile driver](named_roster_0402.py) · [Stage tests](../../../tests/pipeline_eval/test_named_roster_0402.py) · [Screen tests](../../../tests/pipeline_eval/test_exact_noise_gate_0402.py)

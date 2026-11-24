# Combined successor on the two original South mirror offers

The current combined solver preserved the containing fix and reproduced the known **false fix** on the 100 m omission. Both calibration endpoints and RF residuals exactly matched the corresponding installed ALGO08v3 control. On the omitted offer the estimates were 242.474 m and 182.783 m inside the east face, so the boundary-triggered exterior check did not run. This is a retained failure on one simulated region pair. [Frozen protocol](combined-successor-south-protocol.md) · [Earlier saved omission](nomination-handoff-south.md)

| Original South offer | Published result, both solvers | Horizontal error, fixed / fitted `c` | Conditional and all-owned RF RMS, fixed / fitted `c` | Owners, fixed / fitted `c` |
| --- | --- | ---: | ---: | ---: |
| Site 100 m inside | Fix | 816.789 / 1,101.409 m | 6.502299 / 6.391940 Hz | 266 / 266 |
| Site 100 m outside | False fix | 817.172 / 1,102.143 m | 6.502345 / 6.392003 Hz | 266 / 266 |

Within each offer the calibration arms used the same evidence and search budget. Fitting `c` improved RF RMS by roughly 0.110 Hz while increasing position error by 284.620 m on the containing offer and 284.972 m on the omission. Swapping offers without changing the detector packet raised error by 0.383 m and 0.735 m, respectively. Both solver publications had the same owner digests and complete scientific grid and path per offer. The omitted candidate also reproduced all 266 ordered observation, satellite and role entries in each arm. The archived original containing control preserves owner counts and digests without a separately enrolled ordered role trace.

Each candidate published all eight genuine images and the complete 137-point matched numerical grid, with zero objective endpoint-replay difference for both arms. The same four orbit PNGs kept identical encoded and decoded checksums. Two Cairo residual sheets and the explicit-layout position and track sheets differed from the installed in their expected rendering paths. Each grid and path was independently checked against the actual verified position PNG in its publication. The current native template and projector ran on both grids with two exact assembly checks and two exact projection checks. [Scored receipt](measurements/combined-successor-south.json.gz)

## Actual guarded route

The original cutoff and history census selected `lean` with `healthy_samples` for both offers. The signed two-centre scout worked over all 1,618 catalogue rows and retained the four corners. Each run paid two centre fits and produced **two** distinct candidates, below the existing threshold of three. Both retried ordinary ranking. The ordinary producer captured three valid prefixes in the containing run and two in the omission. The proposed branch was not used as an ordinary checkpoint and no admitted checkpoint was consumed. The fixed ordinary winner was rank one in both cases, with `near_region_face` for containing and `not_three_finalists` for omission. The original named survivor finish then accepted both arms. No support repair, named inference fallback, orbit extension or original restart ran. Neither offer invoked the terminal exterior probe since no endpoint landed at the optimizer bound.

| Saved timing boundary | Containing candidate wall / CPU | Omitted candidate wall / CPU | Omitted installed wall / CPU |
| --- | ---: | ---: | ---: |
| Two-centre attempt | 0.210 / 0.210 s | 0.211 / 0.211 s | — |
| Ordinary rank retry | 0.296 / 0.296 s | 0.286 / 0.286 s | — |
| Complete numerical solve and grid | 3.403 / 3.400 s | 3.192 / 3.192 s | 4.473 / 4.468 s |
| In-worker official publication | 4.851 / 4.828 s | 4.584 / 4.584 s | 6.235 / 6.206 s |
| **Saved worker launch through exit** | **6.333 / 6.303 s** | **5.993 / 5.991 s** | **7.891 / 7.853 s** |

The omission saved **1.317×** versus the same-scope installed worker and cost 0.276 s more than the earlier routed saved control. The containing installed control's **14.370 s** was an original raw-through-exit clock, so it supplies scientific parity without a matched saved timing denominator. Common verification and setup for the two candidate workers cost **1.321 wall / 1.309 CPU s**, separate from the child clocks. The containing worker reported 2,456 process input blocks and 48 major faults, versus zero in the omission; the receipt does not attribute these to a file. Both runs used the shared Gauss lock, CPU 2, nice 15, best-effort I/O 7 and one numerical thread.

## Custody and reproduction

The two frozen original offers, 1,200 issued and admitted visits and exact named-receiver 20 ms packet `26e4ce9c24e81761e4d92cf05e29474e4ced9ba4effdffff89b817c0ea9f9ce3` shared the same causal cutoff `1794638719996253000` and all 35 verified RAM-staged catalogue bodies (62,574,375 B). The original containing configuration SHA-256 matches the installed ALGO08v3 scientific specification. The saved omission uses the verified existing installed worker and its sealed outputs. This experiment opened no original recording files or backing archive and launched no installed repeat.

Run `combined_successor_south.py run FRESH_TMPFS_ROOT` through the release interpreter as `leo` under the shared lock, then `score` with checkout `src` available for standard product readback. The wrapper uses the original `combined_successor_0289` worker with its exact `1245957b4` science, 45 source pins and two verified native grid libraries. The only adapter admits the two known direct RAM paths and the original single manifest spelling. The timed commit was `22ba48057`, and the prediction seal SHA-256 was `9bc1905cd2ca2130a52634228b5310636d0bd94cd7751558ea7a09bfd1ba639b`. The first offline score stopped on the valid historical `ok` numerical terminal spelling beneath a public `complete` receipt. The corrected verifier accepts that contract and scored the unchanged sealed processes without another worker launch. The uncompressed scored receipt SHA-256 is `042cb5bb89f2a4cd523761a74fc4932893474377407f326d922fd6f712257aec`. [Runner](combined_successor_south.py) · [Focused tests](../../../tests/pipeline_eval/test_combined_successor_south.py)

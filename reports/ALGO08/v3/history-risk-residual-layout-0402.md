# Ordinary orbit plots with faster standard publication

The public research option `--cairo-residual-layout` keeps all four orbit sheets in the installed Matplotlib renderer and its ordinary layout. It enables two Cairo residuals and the already qualified explicit layouts for position and track RMS. On the same saved DS30-0402 plotting packet, drawing and encoding eight figures fell from **2.625 to 1.690 s wall**, a **0.935 s** reduction also measured in CPU. All four orbit PNGs were byte identical to the ordinary publication, with **100% bidirectional support for all 64 orbit layers**. The earlier six-sheet Cairo option recorded two gray-layer failures on this case. [Frozen protocol](history-risk-residual-layout-0402-protocol.md) · [Verified receipt](measurements/history-risk-residual-layout-0402.json.gz)

All cases use the same renderer selection for the orbit-sheet class. The option is independent of the solver and input reader. It is mutually exclusive with `--cairo-six-sheets`. The CLI defaults to the installed renderer. A Cairo residual fallback also uses the installed orbit figure factory. The raw research witness identifies the route and records counts, actual orbit draw cost and any optimized-layout fallback. The measured transfer used a signed saved handoff. [Public research entry](exact_named_raw.py) · [Renderer binding](history_cairo_render.py)

## Paid scopes

| DS30-0402 saved scope | Ordinary wall / CPU, s | Residual layout wall / CPU, s |
| --- | ---: | ---: |
| Worker through exit | 27.240 / 27.130 | 25.954 / 25.815 |
| Launcher admission and worker | 27.247 / 27.136 | 26.272 / 26.131 |
| Solve with full grid | 22.792 / 22.697 | 21.256 / 21.194 |
| Publication minus solve | 3.177 / 3.174 | 2.534 / 2.459 |
| Draw and encode in the live worker | — | 1.955 / 1.881 |
| Post-publication plotting packet export | — | 0.806 / 0.805 |
| Draw and encode in a same-scene replay | 2.625 / 2.624 | 1.690 / 1.690 |

One new candidate ran in a fresh installed worker on Gauss CPU 2 under the shared lock, nice 15, I/O priority 7 and one numerical thread. The ordinary timing was the previously verified complete history-risk worker on the same input. The candidate worker clock includes a private 26,153,808-byte scene export after official publication for the render-only replay. The replay ran ordinary first and reproduced all eight timed publication hashes in each mode. The replay omits the solver, scene export, launcher and output-store verification. The faster solve and different worker faults contribute to variability in the through-exit difference. The isolated render comparison supplies the marginal renderer estimate. No waveform or backing archive opened. [Ordinary saved control](history-risk-0402-pair.md)

Before the DS30-0402 worker, the independent archived DS30-0316 scene passed the activation gate. The preflight recreated all eight archived ordinary images, matched the four orbit PNGs in candidate mode, and activated two residuals and both explicit layouts without fallback. It saved 0.602 s wall and 0.617 CPU s for that plotting packet. [Preflight receipt](measurements/history-risk-residual-layout-0402-preflight.json.gz)

## Science and media

Both workers used the same signed original full-20 ms detections, original region and cutoff, and prepared archive. They kept the same lean-route diagnostics, terminal, both calibration endpoints, conditional RF, 4,821 ordered owners and roles per arm, all 179 grid values and the fit path. Each grid and path sidecar pointed to its own position PNG. The reference joined offline gave **863.651 m / 100.672 Hz** at fixed zero and **860.302 m / 100.576 Hz** at fitted calibration. [Exact prior endpoints and reference authority](history-risk-cairo-0402.md)

All eight PNGs independently decoded at the original dimensions, DPI, RGBA mode and metadata. The four faster files matched their corresponding previously verified six-sheet/explicit-layout files on this same scene, byte for byte. Both publishers verified and reused eight artifact reads. Total PNG size grew from **12,445,091 to 12,826,483 bytes**. The matching orbit files preserve the original gray and colored marks, axes, legends and wrapping layout. [Earlier orbit failures](orbit-gray-layout.md)

Run `history_risk_residual_layout_0402.py preflight PREFLIGHT.json`, `launch FRESH_TMPFS_ROOT --preflight PREFLIGHT.json`, `replay FRESH_TMPFS_ROOT` and `score FRESH_TMPFS_ROOT` in the pinned saved-worker environment. The worker and renderer replay used `e79968b80`. The first preflight stopped before drawing because a replay-only import arrived before the release's lazy setup. The initial offline scorer also stopped after scientific parity because live dimensions were tuples and JSON dimensions were lists. The scorer now normalizes that representation while checking file and RGBA hashes. Neither correction required another solver. Thirty-two focused tests passed. The uncompressed result receipt SHA-256 is `8fea5dea44c42d473b36b5693ce13259cc3d004391ee98f3ad69366051ccb132`. [Saved trial driver](history_risk_residual_layout_0402.py) · [Tests](../../../tests/pipeline_eval/test_history_cairo_render.py)

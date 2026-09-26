# Execution record

The user authorized this replay and SOL delegation on 2026-09-26.

- Source: `scan-fw-32a202b6e55630ec`, immutable recording and existing analysis.
- Execution checkout: `/srv/bulk/leo-dev/scan-32a202-phase-replay`.
- Base revision: `e1a24b200d4bb68d4f38484dc591e9b9616a2e70`.
- Branch: `codex/scan-32a202-phase-replay`.
- Approved protocol: `plans/scan-fw-32a202b6e55630ec-phase-replay.md`.
- Worker model: `gpt-5.6-sol`.
- Original checkout and its untracked reports are preserved.
- Source recordings, published analysis, radio state and production services are read-only.
- Report outputs and scratch use bulk storage; the system filesystem is nearly full.

Initial parallel packages: capture audit (A), acquisition (B), experiment harness (C).
Frame/filter, sync/spectral, dual-RX, and cross-dwell packages begin when their
source validity and acquisition dependencies are satisfied. The coordinator owns
the final evidence reconciliation and report. No method is classified as successful
merely because a numerical procedure completed.

Review requirements for every numerical handoff:

1. State exact source coordinates, valid support, phase symmetry/reference and CFO branch.
2. Separate end-to-end yield from conditional estimator precision.
3. Separate fitting, random-held reconstruction and causal prediction.
4. Preserve failures, exclusions and incomplete units in denominators.
5. Do not integrate through RF-invalid rows or unobserved gaps without explicit evidence.
6. Reuse one set of qualified raw inputs; avoid independent full-corpus decompression per method.
7. Freeze selection before inspecting phase and retain unfavorable examples.
8. Geometric-phase or satellite claims require calibration and candidate-specific prediction.

Primary local-method mode rule, frozen before phase evaluation: within each
independently acquired receiver/probe, rank candidates by corrected fractional
exact-minus-control GLRT margin, then recorded candidate rank. The primary
single-mode trace uses the highest qualifying candidate. Preserve all other
admitted candidates in the acquisition inventory and use them for explicit
multi-mode/two-signal diagnostics. This bounds the local-method comparison
without selecting on its phase outcome. An epoch/CFO branch change between
probes is an association ambiguity, not permission to stitch phases or fit a
new intercept. Multi-mode analyses must report their own eligible counts.

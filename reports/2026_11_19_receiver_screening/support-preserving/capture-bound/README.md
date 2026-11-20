# Exact capture-GLRT pruning with magnitude bounds

**The energy bounds removed zero of 8,399,790 nonzero-input coarse cells.** Even the per-tap envelope could exclude no cell with the installed eighth-ranked score supplied for free. The measured four-block preflight added work and preserved all ranks and gates. Exactly silent CI16 was the distinct case where an exact bypass skipped all coarse correlations. [Stage figure](stage.pdf) · [All bound checks](bound-audit.csv)

| Held saved-IQ panel | Exact coarse attempts | Smallest per-tap upper bounds | Exact eighth score | Full detector CPU, stock → preflight |
| --- | ---: | ---: | ---: | ---: |
| DS26-0036, legacy lower edge | 8 | 0.794–0.796 | 0.169–0.172 | 1,527 → 1,532 ms |
| DS29-0174, screened upper edge | 10 | 0.785–0.788 | 0.165–0.172 | 845 → 903 ms |

The median paired CPU changes were −0.04% and −4.99% when expressed as improvements. The four-block C preflight alone took 15.78 ms median CPU per saved receiver attempt. The per-tap audit took 21.32 ms. Full detector wall medians were 1,550 → 1,565 ms and 876 → 1,022 ms. These are two alternating repetitions per window after IQ was loaded, on CPUs 2 and 3 respectively. The exact audit is separate from detector timing. [Per-call timing](stage.csv) · [Summary](summary.json)

## Why the bound stayed high

For one anchor and one supported frame, the installed coarse score divides the magnitude of the complex dot product by `sqrt(αβ)`. Here `α` is the anchor template’s power, `β` is the received interval’s power, and the CFO rotation has unit magnitude. Dividing the taps into four blocks gives an upper bound on the numerator by summing `sqrt(α_block β_block)` across blocks. Splitting all the way to single taps gives `Σ |template_i| |IQ_i|`, the triangle bound for that term with phases omitted. Both are shared across CFO frequencies. We average them over exactly the installed symbol/frame support, with zero contributions for zero-energy intervals.

The C kernel uses exact binary64 CI16 power-prefix additions over the admitted geometry. Every squared component sum and the entire bounded prefix fit below `2^53`. The audit includes a small outward allowance around the floating template and rotation arithmetic. The only active pruning decision uses exact silence, so it is independent of that allowance. Correlation cancellation makes the true ranked scores much smaller than the magnitude products. Keeping more magnitude detail lowers the upper bound from about 0.95 to 0.79 on saved IQ, while the useful cutoff stays around 0.17. Even the signed controls’ eighth scores were at most 0.324. The exact cutoff is already a generous comparison for this feasibility test. A live branch would need to establish its threshold and retain the neighbors needed by the original refinement. [Frozen protocol](PROTOCOL.md) · [C implementation](../../../../tools/pipeline_eval/variants/capture_bound.c)

The earlier dense FFT preserves the phase correlations but adds transforms on the screened release. Short-tap nomination replaces part of the original score and changed the retained order. The phase-independent envelope here preserves all support, but it loses the cancellations that make the detector selective. It gives no basis for a larger exact-pruning replay on ordinary nonzero windows. [Installed FFT comparison](../../acquisition-support/capture-fft/README.md) · [Short-tap comparison](../../receiver-core/complete-epoch-proxy/README.md)

## Exact detector controls

All 16 genuine archived probe rows reproduced. The paired runtime arms matched every recorded coarse rank, acquisition grid, refined CFO, fractional candidate, and gate across 16 authentic timing pairs and eight signed, weak, noise and empty pairs. The two envelopes separately covered all 9,519,762 exact CPU grid cells across 34 acquisition attempts, including the screened producer’s independent dense FP64 audit. Signed and weak plants retained their timing and CFO on both receivers on both releases. Noise and empty inputs produced zero gated candidates.

The exact-silence route omitted all 1,119,972 zero cells across the four empty receiver attempts. It took 5.12 ms vs 951.93 ms on legacy empty CI16 and 9.18 ms vs 525.17 ms on screened empty CI16. No nonzero saved or synthetic input skipped a cell in the runtime experiment. [Lower-edge traces](DS26-0036.json.gz) · [Upper-edge traces](DS29-0174.json.gz)

## Reproduction

`python -m tools.pipeline_eval.qualification.capture_bound_trial freeze <new-scratch>` authenticates the raw inputs, installed sources and framed geometry and compiles the C envelope. Run the same module with each recording ID using that case’s pinned capture release on `PYTHONPATH` and its installed Python on a single core. The optional Python `Envelope.activate()` context wraps the authenticated detector coarse port only. `python -m tools.pipeline_eval.qualification.capture_bound_results <scratch>` verifies the original archived factors and derives the bound audit, CPU/wall table, and figure. [Source and input lock](input-lock.json) · [Published result hashes](result-lock.json)

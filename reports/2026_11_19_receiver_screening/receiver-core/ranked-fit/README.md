# Skip unused orbital modes during ranked cavity nomination

Ranked fine nomination evaluates the incumbent satellite and the same ordered alternatives across five phase rounds. A candidate uses a three-column physical orbital block when its satellite already has support in the incumbent or its held curved observations have at least two independent receiver/channel owners. The original phase-release receiver built a separate previous-epoch orbital bank for the remaining candidates and never read that bank. The optional two-line overlay prepares a new bank only for the candidates that use it. The incumbent modes, priors, aliases, rank order, search budgets, and final two-arm fit remain in the original code.

## Measured source of work

An earlier complete DS29-0247 profile put 5.85 of 7.06 fine-nomination seconds inside physical mode-bank construction, with Python profiling overhead. Fresh lightweight stock probes under 512 MiB isolated the unnecessary subset. DS29-0247 made 71 unused mode requests in 1.003 process CPU seconds. DS26-0237 made 58 in 1.070 seconds. Each recording evaluated 208 fine candidates across 26 held families.

The lightweight probe retains a bit-sensitive digest of ordered candidate identities, scores, phases, frequencies, aliases, qualification flags, and winners. It also retains the held observation sets and coarse candidate counts in that digest. Both measured methods use the same probe. Each visible geographic result comes from a fresh standalone numerical worker with the same complete saved factors, truth-free offered tile, causal catalogue, and zero-swap 512 MiB cap.

## Primary release comparison

| Saved capture | Fine candidates | Unused mode builds, stock → overlay | Fine CPU (s), stock → overlay | Nomination CPU (s), stock → overlay | Supervisor wall (s), stock → overlay |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS29-0247 | 208 | 71 → 0 | 3.204 → 2.620 | 13.510 → 12.617 | 163.03 → 185.23, timeout |
| DS26-0237 | 208 | 58 → 0 | 3.058 → 2.549 | 12.347 → 12.553 | 82.43 → 105.29 |
| DS26-0122, held | 152 | 28 → 0 | 2.241 → 1.808 | 10.547 → 8.636 | 138.19 → 127.38 |

All 568 fine outcomes across 71 families retain their exact order and numeric digest. On the two complete stock/overlay pairs, both calibration arms preserve geographic coordinates, conditional RF RMS, frequency objectives and published decisions. Fine-nomination CPU decreased 16.6–19.3% on the primary captures. Some supported requests did their first previous-state lookup later inside nomination, offsetting part of the removed computation. Whole-worker changes varied. The DS29-0247 candidate reached the wall limit after 140.67 CPU seconds with 341.98 MiB peak charge.

DS29-0247's one separate confirmation used the same candidate, capture, CPU, 185-second deadline, and 512 MiB cap. It reached the same exact nomination digest and reached the wall limit again after 152.21 CPU seconds. Both reserve candidate attempts have null geographic endpoints. The primary chart retains its original denominator and the confirmation has its own chart. [Primary charts](figures.json) · [Timing counters](resources.csv) · [Both-arm scores](scores.csv) · [Reserve confirmation](confirmation/comparison.json)

## Supplementary complete DS29 pair

After both reserve deadlines, DS29-0174 was selected from the prior authenticated stock study's 0–55-second wall stratum. The unchanged overlay ran first on CPU 12, followed by fresh stock. Both used the same 185-second deadline and physical 512 MiB cap with zero swap.

Both methods completed all 176 fine candidates across 22 families with exact ranked digests. The overlay eliminated 47 unused builds. Fine CPU was 2.400 → 2.117 s and nomination CPU was 9.307 → 8.857 s. Whole wall was 77.05 → 82.43 s. Both geographic fixes, conditional RF RMS values, frequency objectives, published decisions and counts match exactly. This gives whole-position parity on two datasets and a prespecified held case. [Supplementary position chart](companion/figures.json) · [Timing and memory](companion/resources.csv) · [Both-arm scores](companion/scores.csv)

## Installed change

The 78-source release keeps both native libraries byte-identical. The only numerical source change is the guard in `family_cavity.candidate_prediction`. The installed source hash and the relocated native manifest are in the candidate lock.

The signed context still checks the previous catalogue and computes the phase alignment and widths across all candidates. Physical-mode propagation follows the original path where the fine candidate consumes those modes. The removed call could raise an incidental error while constructing a previous padded orbit for an unsupported candidate. The change is available as an optional installed overlay. Default adoption would require a completed reserve endpoint within the target deadline. [Protocol](PROTOCOL.md) · [Installed diff](installed-change.patch) · [Installed source lock](candidate-lock.json)

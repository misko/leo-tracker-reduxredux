# ALGO08v3

ALGO08v3 is the opt-in research release of the frozen two-scan receiver and compact v5 solver tested against deployed ALGO08v2. It is the baseline for the next single-core speed target. Gauss continues to use ALGO08v2 for automatic analysis.

The final 100-recording DS30 comparison measured **1.76× median paired elapsed speedup** and **1.79× summed elapsed speedup** over ALGO08v2. ALGO08v3 returned 92 fixes and ALGO08v2 returned 97. Three recordings were withheld by both builds, and five additional recordings hit an orbit-interpolation error in v3. Across the 92 shared fixes, the largest difference in fitted horizontal error was 2.58 m. The recordings all came from one roof. [Final report, histograms and recording-level results](ds30-100/README.md)

The receiver verifies all fractional scores, uses both scans and reads compressed members with a bounded read-ahead hint. The solver uses the supplied region, shared discovery, sparse orbit projections and a curved likelihood design. A fix produces the eight standard figures. The versioned launcher adds `algo08v3-release.json` alongside the existing scientific outputs, including when the pipeline withholds. It requires a fresh output directory for each run.

| Release identity | Value |
|---|---|
| Git tag | `algo08v3` |
| Frozen specification SHA-256 | `6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f` |
| Receiver SHA-256 | `2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5` |
| Gauss payload archive SHA-256 | `96f3c6e74264f1bbfea58e78337b4ec8d9160ddad6b360af2ab36dd300ba3eba` |
| Required Gauss numerical environment | `/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c` |

### Run on Gauss

```sh
/opt/leo-algo08/algo08v3/run --verify
output=$(mktemp -d)
/opt/leo-algo08/algo08v3/run --recording "$RECORDING" --archive "$TLE_ARCHIVE" \
  --region "$REGION_JSON" --bulk-root "$output"
```

For a second installation on Gauss, download the payload from the release and verify the archive before extracting into a fresh directory. The versioned launcher verifies the original spec and its pinned sources. It resolves the seven pinned native libraries inside the new installation. [Release and payload](https://github.com/misko/leo-tracker-reduxredux/releases/tag/algo08v3)

```sh
work=$(mktemp -d)
gh release download algo08v3 --repo misko/leo-tracker-reduxredux --dir "$work" --pattern algo08v3-gauss.tar.gz
(cd "$work" && echo '96f3c6e74264f1bbfea58e78337b4ec8d9160ddad6b360af2ab36dd300ba3eba  algo08v3-gauss.tar.gz' | sha256sum -c -)
mkdir "$work/payload"
tar -xzf "$work/algo08v3-gauss.tar.gz" -C "$work/payload"
install -m 0755 reports/ALGO08/v3/run "$work/run"
"$work/run" --verify
```

### Evidence at naming

For the subsequent one-core trial of early receiver stopping, solver layout reuse and regional pruning, see the [component ceilings and end-to-end comparison](bounds-trial.md).

Five subsequent experiments tested a cheaper timing search, an accelerated robust solver, interleaved capture visits, a regional uncertainty check and sparse two-sided receiver searches. The solver saved 1.08–5.48 CPU seconds on the dense recording. Skipping visits increased fitted position error from 1.512 to 2.612 km and introduced a false fix on a missing-region control. Historical clocks on the frozen 16-recording prefix imply that even a solver twice as fast needs acquisition **at least 2.35× faster** to meet both overall timing gates, holding publication time and the observed failure cost fixed. [Experiment ledger, runtime and error plots, and reproducible qualification protocol](https://github.com/misko/leo-tracker-reduxredux/blob/a200ab749fa1555bd285e86d35ecb1cdb6531634/reports/ALGO08/v3/development/README.md)

The installed launcher replayed DS30-0374 from saved I/Q in the single-core slot. All 9,288 detector probes, both calibration-arm positions and owners, path and grid scientific digests, and all eight PNG file hashes matched the corresponding frozen candidate publication. [Gauss replay and artifact digests](gauss-smoke.json)

On the first 55 of 100 assigned DS30 recordings, median paired and summed elapsed speedups over ALGO08v2 were 1.75× and 1.79×. ALGO08v2 returned 54 fixes and ALGO08v3 returned 52. The horizontal error matched on every shared fix for both calibration fits. ALGO08v3 stopped at an orbit-interpolation boundary on DS30-0022 and DS30-0129. Both builds withheld on DS30-0227. All physical DS30 recordings come from one site. The research version was named at the user's request before the full panel completed.

The next target halves **ALGO08v3** elapsed time on both the median paired and summed raw-I/Q-to-publication measures. Preserve its fixes and eight figures, measure recovery of the two ALGO08v2 fixes separately, and test containing and missing search regions away from the DS30 site. [Stage budgets and experiments](single-core-target.md) · [Runtime histogram](first-55/runtime.png) · [Position-error histogram](first-55/position-error.png) · [Paired measurements](first-55/recordings.csv)

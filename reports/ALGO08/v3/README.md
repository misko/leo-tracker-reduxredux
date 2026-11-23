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

Searching one third of the recording cut dense solver time to 10–11 CPU seconds. Both a contiguous prefix and staggered RF blocks returned worse positions on dense DS30 and the southern simulation. Fitted dense error reached 3.83 and 3.75 km against 1.51 km for installed v3. All routes withheld on the distant southern omission. A 128-window input benchmark halved warm acquisition CPU with a verified empty tail. A targeted second search predicted the correct satellite and frequency for 234 of 2,920 omitted dense factors and zero of 152 southern factors. Keeping all visits and sampling each track only inside the solver preserved dense accuracy by invoking v3 fallback and took 69.34 CPU s. [Matched time and error plot, input-cost model and follow-up](https://github.com/misko/leo-tracker-reduxredux/blob/7115d00f7b31005b6335220f28e6b400057fcf11/reports/ALGO08/v3/rf-block.md) · [Full-track solver comparison](https://github.com/misko/leo-tracker-reduxredux/blob/7115d00f7b31005b6335220f28e6b400057fcf11/reports/ALGO08/v3/track-quadrature.md)

On a second physical recording, DS30-0374, the joint solver produced all eight PNGs from saved detections in **19.13 s** versus **24.13 s** for v3. Its history check declined the signed correction. Horizontal error changed by +4 m with fixed-zero calibration and −7 m with fitted calibration. Across all of DS30-0008, both v3 fits used 239 observations found by the second receiver search, all after the initial 128-visit test. [Matched DS30-0374 publication and original position plots](https://github.com/misko/leo-tracker-reduxredux/blob/e2849853bcc8afa843e252da71c9c8336d5d6eb7/reports/ALGO08/v3/signed-0374-transfer.md) · [Receiver ownership census](https://github.com/misko/leo-tracker-reduxredux/blob/e2849853bcc8afa843e252da71c9c8336d5d6eb7/reports/ALGO08/v3/primary-schedule.md)

The signed phase fit cut dense DS30-0008 solve time from 54.52 to 38.06 s and fitted position error from 1.512 to 1.080 km. It reproduced the installed positions at the northern and southern simulated sites and withheld on both distant omissions. Applying its dense solve fraction to the historical 16-recording clocks would still require **3.05× faster acquisition** to halve complete elapsed time. On 128 dense visits, a receiver schedule with perfect foresight saved 39% of acquisition CPU with identical outputs. [Solver time and position-error plot](https://github.com/misko/leo-tracker-reduxredux/blob/4739c5c65e0a9c975f1ff6856a4a12f501ff7b53/reports/ALGO08/v3/blind-joint-signed.md) · [Timing assumptions and limits](https://github.com/misko/leo-tracker-reduxredux/blob/4739c5c65e0a9c975f1ff6856a4a12f501ff7b53/reports/ALGO08/v3/development/README.md#how-fast-would-acquisition-need-to-be-with-the-signed-position-fit) · [Receiver experiment](https://github.com/misko/leo-tracker-reduxredux/blob/4739c5c65e0a9c975f1ff6856a4a12f501ff7b53/reports/ALGO08/v3/primary-schedule.md)

The joint curved and predictive solver with one bounded repair completed the 1,200-window southern development recording in 13.38 s from raw I/Q through all eight PNGs. Installed v3 took 14.36 s. On dense DS30-0008 the saved solve took 45.37 versus 59.09 CPU seconds and improved fitted error from 1.512 to 1.070 km. Frozen northern transfer increased fitted error by 83 m. Both simulated distant omissions withheld. [Matched end-to-end report, original position PNGs and five-offer plot](https://github.com/misko/leo-tracker-reduxredux/blob/6a5190eb860be34686c514cc8c7a91d79a03bd72/reports/ALGO08/v3/development/joint-publication.md)

On four matched DS30 recordings, the fastest earlier build with complete coverage used 87.6% of v3 elapsed time and 99.7% of its CPU in separate archived sessions. Two follow-up experiments isolated different limits. A direct one-bit pilot search exceeded the whole receiver callback allowance even under optimistic instruction costs. Providing the solver with perfect curved satellite labels recovered the dense RF fit, while its fitted position still missed the accuracy gate. [Matched runtime and error plots](https://github.com/misko/leo-tracker-reduxredux/blob/7169c03291c08f03b0a80659bc8e1d8b08cf1411/reports/ALGO08/v3/development/archived-four.md) · [Receiver cost calculation](https://github.com/misko/leo-tracker-reduxredux/blob/7169c03291c08f03b0a80659bc8e1d8b08cf1411/reports/ALGO08/v3/low-bit-pilot.md) · [Solver label experiment](https://github.com/misko/leo-tracker-reduxredux/blob/7169c03291c08f03b0a80659bc8e1d8b08cf1411/reports/ALGO08/v3/mixture-oracle.md)

The accelerated robust solver saved 1.08–5.48 CPU seconds on dense DS30-0008. Skipping receiver visits increased fitted position error from 1.512 to 2.612 km and introduced a false fix on a missing-region control. On the frozen 16-recording prefix, a solver twice as fast still needs acquisition **at least 2.35× faster** to meet both overall timing gates, holding publication time and the observed failure cost fixed. [Experiment ledger, runtime and error plots, and qualification protocol](https://github.com/misko/leo-tracker-reduxredux/blob/214d12f72390c36ee4141776dee0a67aa00a5960/reports/ALGO08/v3/development/README.md)

A full dense acquisition reproduced the archived detections using 37.34 CPU seconds inside the stereo detector and 21.62 CPU seconds elsewhere through solver handoff. Sparse cross-channel orbital prediction missed most measured signals, even when granted exact timing. A joint mixture solver required v3 fallback on all three tested offers and took 63.47 CPU seconds on the dense saved input, versus 54.72 for v3. [Measured acquisition split](https://github.com/misko/leo-tracker-reduxredux/blob/214d12f72390c36ee4141776dee0a67aa00a5960/reports/ALGO08/v3/acquisition-split.md) · [Mixture solver runtime and error plots](https://github.com/misko/leo-tracker-reduxredux/blob/214d12f72390c36ee4141776dee0a67aa00a5960/reports/ALGO08/v3/mixture-position.md)

The installed launcher replayed DS30-0374 from saved I/Q in the single-core slot. All 9,288 detector probes, both calibration-arm positions and owners, path and grid scientific digests, and all eight PNG file hashes matched the corresponding frozen candidate publication. [Gauss replay and artifact digests](gauss-smoke.json)

On the first 55 of 100 assigned DS30 recordings, median paired and summed elapsed speedups over ALGO08v2 were 1.75× and 1.79×. ALGO08v2 returned 54 fixes and ALGO08v3 returned 52. The horizontal error matched on every shared fix for both calibration fits. ALGO08v3 stopped at an orbit-interpolation boundary on DS30-0022 and DS30-0129. Both builds withheld on DS30-0227. All physical DS30 recordings come from one site. The research version was named at the user's request before the full panel completed.

The next target halves **ALGO08v3** elapsed time on both the median paired and summed raw-I/Q-to-publication measures. Preserve its fixes and eight figures, measure recovery of the two ALGO08v2 fixes separately, and test containing and missing search regions away from the DS30 site. [Stage budgets and experiments](single-core-target.md) · [Runtime histogram](first-55/runtime.png) · [Position-error histogram](first-55/position-error.png) · [Paired measurements](first-55/recordings.csv)

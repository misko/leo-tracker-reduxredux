# Exact named-v3 publication on saved DS30-0016 detections

The opt-in candidate used **4.921 CPU s** from process launch through exit with the sealed named-v3 detector packet, against **6.385 CPU s** for the saved control. Both reproduced the original terminal, both calibration arms, all 109 owners per arm, the complete 179-point objective grid and the optimizer path. The observed CPU difference was **1.464 s**. The control recorded 71,464 process input blocks and spent 3.20 s longer in the solve than its solve CPU clock. The candidate recorded zero input blocks. The elapsed difference includes storage waits. [Saved process clocks, scientific digests and visual audit](measurements/named-weak-exact.json.gz)

| Fresh saved process, control first | Control CPU (s) | Candidate CPU (s) |
|---|---:|---:|
| Complete process through exit | 6.385 | 4.921 |
| Numerical solve including full grid and path | 3.355 | 3.196 |
| Graph within numerical solve | 0.077 | 0.036 |
| Render and encode all eight figures | 1.767 | 0.488 |
| Complete process elapsed | 9.654 | 4.922 |

The runner verifies the installed launcher and frozen specification. It invokes the same named numerical publication with its original signed detector, schedule, screened solver, native grid and PNG codec. It uses the already installed lazy-startup finder when binding the scanner. The candidate scopes ordered graph edges and exact `_best_piece` reuse, scalar phase preparation, explicit figure layout and the guarded Cairo orbit and residual renderers. It used 123 polynomial cache hits in 158 calls, one exact causal forecast and six direct Cairo rasters without a fallback. Both launches used one source-verified handoff of the same sealed packet, the same causal archive and supplied region, fresh tmpfs output, a common font cache and Gauss CPU 2 at nice 15 and best-effort I/O priority 7 under the shared lock. The completed pair covers one recording and one order. [Launcher](named_weak_exact.py) · [Graph parity](graph-polynomial-cache.md) · [Causal forecast parity](exact-phase-forecast.md)

| Calibration | Latitude, longitude | Horizontal error (km) | RF RMS (Hz) |
|---|---|---:|---:|
| `c = 0` | 37.8349381849, −122.4913009694 | 1.644 | 109.375 |
| Fitted `c` | 37.8356817648, −122.4941904508 | 1.661 | 109.479 |

The packet and the original terminal and owner digests matched. Horizontal errors come from the existing named control's evaluation and were outside the runner. The 808 issued windows included 713 admitted stereo windows and 95 exclusions. The stock renderer reproduced all eight published PNG file and decoded RGBA digests. Each candidate figure kept the corresponding pixel dimensions, with changed pixels and changed encoded bytes. The eight files totaled 2,887,163 encoded bytes, up 268,512 from 2,618,651. Both position sidecars were checked against their own actual PNG. [Original warm raw receipt and reference errors](measurements/weak-combined-raw.json)

## Post-exit figure audit

The four orbit images kept eight data panels each. A separate script aligned their plotting rectangles from visible spines and compared each pane at a two-pixel tolerance. Colored marks achieved at least **99.9908%** support in both directions across all 32 panels. The dark neutral marks achieved **99.7795%** support in both directions on populated panels. The candidate legend pixels independently reproduced the labels Unassociated, 63510 and 64015 read from the named charts, with a 26-pixel minimum gap. The aligned footprints, labels and footer retained the same meaning with different layout and antialiasing. [Post-exit audit](named_weak_visual.py)

Both residual sheets retained their lane labels, counts, units and zero lines. CH1, CH3 and CH4 retained their visible signed residual marks. Empty panels display y ticks at (0,pm0.025,pm0.050) Hz in Cairo versus (0,pm0.02,pm0.04) Hz in the named figures. The position map retained both fit annotations, the grid, markers, paths and colorbar. The track RMS chart retained three labeled fragments and their bar heights relative to the axis. Prior scene comparisons independently checked the orbit and residual data and native draw bindings. [Orbit qualification](direct-orbit-figures.md) · [Residual qualification](direct-residual-figures.md)

## Raw-to-exit budget

Half of the previous 10.831 s fully resident named-v3 raw launch is **5.415 s**. At the observed candidate's saved elapsed time there would be **0.493 s** left, or **0.548 s** after removing the measured saved callback that raw acquisition would replace. A separate all-resident named-v3 run previously took **5.936 s from launch through the sealed detector file**, a broader stage that includes startup and validation. These are stage and process measurements from different launches. The retained receiver makes halving that original raw clock implausible without another acquisition change. The optional raw entry delegates acquisition to the installed receiver unchanged, and this experiment executed no raw handoff. [Archived all-resident named detection boundary](measurements/bounds-DS30-0016-pair.json)

For the saved comparison, use the same Gauss shared lock, one-thread environment and installed venv with the repository’s `src`, checkout root and report directory on `PYTHONPATH`. Run `named_weak_exact.py compare NEW_TMPFS_ROOT` against the original saved publication at `/dev/shm/leo-v3-combined-frontier-weak-01/stock`. Then run `named_weak_visual.py NEW_TMPFS_ROOT` to audit the resulting stored plots after both processes exit. Four handoff and raster-audit tests passed with 18 adjacent Graph, phase and renderer cases. [Component tests](../../../tests/pipeline_eval/test_named_weak_exact.py)

# Corrected orbit rendering on saved DS30-0057

Adding the four native orbit sheets to the existing native-residual renderer cut DS30-0057's eight-figure render from **1.170 to 0.976 CPU seconds**, a **0.194 s** saving. The fresh saved processes finished in **10.436 and 10.218 s elapsed** through exit. Their CPU clocks were **10.323 and 10.206 s**. Both reproduced the original complete signed publication. [Frozen protocol](direct-orbits-medium-protocol.md) · [Paired measurement and media checks](measurements/direct-orbits-medium-DS30-0057.json.gz)

| Saved boundary | Control CPU s | Native orbit CPU s |
| --- | ---: | ---: |
| Full scientific solve | 7.491 | 7.604 |
| All eight figures, render and encode | 1.170 | 0.976 |
| Four native orbit figures | — | 0.621 |
| Encoding within the four native orbit figures | — | 0.188 |
| Complete saved publication within the worker | 10.027 | 9.927 |
| Fresh process through exit | 10.323 | 10.206 |

The control-first process pair measured **0.118 s CPU** and **0.218 s elapsed** gains. Solve CPU increased 0.113 s in the candidate. The control recorded 3,288 dependency input blocks and one major fault, and the candidate recorded zero of each. Those differences contribute to the whole-process comparison. The paired render clocks isolate the measured chart change more closely.

The two launches used the same genuine unfiltered 20/12 ms detector packet from the completed medium tmpfs publication, the supplied region, 2,717 issued visits, the original causal archive and the unchanged numerical routes. Both used the common font cache, explicit layout and two native residuals. The candidate drew four native orbit figures with zero fallbacks. Both paid through standard store publication and verification, and both exited zero. Neither timed process exported a scene or invoked an audit renderer. [Original saved medium publication](cumulative-medium.md) · [Previous weak and dense qualification](direct-orbit-figures.md)

## Scientific and figure checks

| Calibration | Original and retained latitude, longitude | Original and retained RF RMS |
| --- | ---: | ---: |
| Fixed zero | 37.84690247°, −122.48596873° | 125.297918 Hz |
| Fitted | 37.84767156°, −122.48286328° | 125.310558 Hz |

Both processes retained the published terminal, all **1,542 owner and role rows per arm**, the full 179-point grid and numerical path. Both sidecars bind the actual position PNG. All eight file hashes and decoded RGBA hashes were verified after exit. The two residuals, track RMS and position PNGs were identical between modes. The control's four orbit images, track RMS and position also match the previously audited explicit-layout publication.

Each native orbit legend's RGB pixels match an independently drawn legend built from the 14 sealed fitted-owner satellite IDs. The minimum column gap is **26 pixels**. A representative chart review found the legends and panel labels legible. Over every data rectangle the bidirectional saturated-pixel coverage within two pixels was at least **99.9986%**. This checks the visible colored footprint of the curves and associated points. The shapes and colors in the four corrected PNGs differ at the raster level, and the original image metadata matches.

| Native orbit output | Pixels changed | Mean absolute RGB difference (0–255) | Added bytes |
| --- | ---: | ---: | ---: |
| CH1–4 all observations | 16.08% | 5.277 | 91,768 |
| CH1–4 unassociated | 15.85% | 5.302 | 86,416 |
| CH5–8 all observations | 16.27% | 5.273 | 78,796 |
| CH5–8 unassociated | 15.95% | 5.285 | 72,892 |

An initial setup attempt stopped before the solve because the trial passed checked library contents in place of paths. The retained pair passed verified paths. The first post-exit raster check included the spaces between panels, where Cairo's subpixel text edges affected its color test. The corrected checker verifies each actual data rectangle at the same tolerance and reuses the completed process pair. The timing driver as run is preserved at revision `5f4639017`. Twenty focused and adjacent tests passed. [Runner and standalone verifier](direct_orbits_medium_trial.py)

## Reproduce

Use the existing sealed medium packet and a fresh private tmpfs output. The parent checks the current repository's storage contract and each fresh child loads the installed release. The `verify` subcommand rechecks an existing completed pair without repeating either timed process.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$PWD/reports/ALGO08/v3:$PWD:$PWD/src:$release/src:$release" \
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs reports/ALGO08/v3/direct_orbits_medium_trial.py "$output"
```

# Candidate-only native residual rendering through publication exit

The native residual opt-in reduced the complete saved DS30-0016 process from **5.118 to 4.828 seconds elapsed**, a **0.290 s** or **5.7%** saving. Complete eight-figure rendering and encoding fell from **1.088 to 0.865 CPU seconds**. This is one fresh control-first pair, timed through exit with the installed numerical solver and standard publication. [Frozen protocol](direct-residual-entry-protocol.md) · [Matched receipt](measurements/direct-residual-entry-DS30-0016.json.gz)

| Saved scope | Control CPU s | Native CPU s |
| --- | ---: | ---: |
| Scientific solve | 2.546 | 2.521 |
| Complete eight-figure render and encode | 1.088 | 0.865 |
| Complete saved publication | 4.927 | 4.594 |
| Fresh process through exit | 5.116 | 4.826 |

Both runs exited with status zero and reported zero dependency input blocks and major faults. The process difference includes small movements outside rendering, including the measured solve difference. The measured **0.223 s** render reduction describes the actual replacement. The earlier diagnostic paired both residual renderers inside one process and had a larger component difference. The present pair pays only one renderer per residual sheet. [Earlier component measurement](direct-residual-figures.md)

## Opt-in and parity

Enable `--direct-residual-figures` with `--one-pass-web-png`. The optional code loads in the active renderer call. It uses the reviewed Cairo scene builder with the original packet and title, delegates the other six plots to the installed path, and passes both native RGBA buffers through the currently configured libdeflate encoder. The scoped adapter skips construction of Matplotlib artists for the two original residual slots. The original plot source, residual layout and encoder are checked before selection. Unsupported layouts or native drawing failures use the incumbent renderer.

The control recorded two Agg residual sheets. The candidate recorded two native sheets, zero Agg residual sheets and zero fallbacks. Fresh timing paid the original save and publication figure verification in both launches. The pair's independent scientific and image comparisons ran after exit.

Both results reproduced the original signed terminal, calibration endpoints and RF RMS, all 116 owner and role rows per arm, the numerical path, and the complete 179-point grid. Both numerical sidecars bind the actual unchanged position PNG. The same region and causal archive were used in both. Six encoded files and decoded RGBA arrays match the original explicit layout. The two published Cairo files and decoded arrays match the already-audited native outputs exactly. That audit established the original axes, limits, labels, tick labels and all 116 ordered scatter points. The same small empty-axis tick placement differences and visibly different Cairo pixels apply here. The two native files add 109,169 bytes. [Scene and raster audit](direct-residual-figures.md)

The runner supplies the original authenticated saved packet to the normal active publication entry. It creates two fresh tmpfs outputs under the shared low-priority Gauss slot. Sixteen focused and adjacent tests passed. [Entry](unified_short_bootstrap.py) · [Renderer adapter](direct_residual_entry.py) · [Pair runner](direct_residual_entry_trial.py)

## Reproduce

Use a fresh private tmpfs parent and an account permitted to read the sealed signed inputs.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$PWD/reports/ALGO08/v3:$PWD:$PWD/src:$release/src:$release" \
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs reports/ALGO08/v3/direct_residual_entry_trial.py "$output"
```

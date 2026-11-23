# All-visit readout after the signed scouts

Removing the entire post-scout verifier and its input load saved at most **28.1% of native CPU** on the saved dense slice while keeping both scouts and signed cancellation. The independent held-block readout came close to that timing floor. It matched only **15 of 80 dense factors and 5 of 58 weak factors** within two wrapped samples and 250 Hz. The sole dense continuation selection disappeared. This waveform replacement does not warrant a raw publication replay. [Paired timings and per-lane evidence](measurements/scout-readout.json.gz)

## What the original scouts already measure

The linked tracing entry preserved every ordered release factor byte on 36 DS26 weak lanes and 96 authenticated DS30-0008 lanes. A scout independently confirmed every rank eventually exported on these slices. It confirmed no additional rank that the original verifier later withheld. All 44 installed-empty dense lanes had no primary confirmation, so this panel did not expose rejection of a spurious coarse-confirmed rank by the final verifier. The dense scout used its early independent gate on 15 of 80 issued ranks. The weak scouts used their later gates on all 58. [Trace runner](scout_readout_trial.py)

| Saved slice and rank | Released factors | Scout signed CFO exactly equal | Maximum absolute CFO change | 95th-percentile scout-to-final timing change |
|---|---:|---:|---:|---:|
| Weak primary | 36 | 36 | 0 Hz | 0.352 samples |
| Weak residual | 22 | 22 | 0 Hz | 0.437 samples |
| Dense primary | 52 | 50 | 443.892 Hz | 0.351 samples |
| Dense residual | 28 | 27 | 443.892 Hz | 0.451 samples |

The three dense CFO changes were one stock residual FFT bin each. All retained coarse epochs were within 0.864 wrapped samples of the final timing. This identifies a small-slice measurement correlation between the scout and published CFO. The verifier also supplies a waveform-dependent exact-versus-rolled margin for release gate, continuation ordering and uncertainty fitting. Archived full-recording probe packets contain only the final values. The older directed trial used the coarse values internally and archived no full-recording coarse/final ledger. [Directed comparator](directed-verifier.md) · [Continuous score consumers](../single-core-2x/receiver-fractional-score-consumers.md)

## Independent held pilot blocks

The alternate readout uses symbols 130–157 at the scout's fractional time on the original CI16 samples. The nominated epoch's timing and refinement templates and the original confirmation regions use other pilot symbols. Four seven-symbol blocks per frame form exact-pilot and rolled-pilot correlations, using linear interpolation and the signed scout oscillator. The adjacent-block phase gives a residual CFO. Separate even and odd frame groups yield the smaller normalized exact energy and larger rolled energy. The frozen study rule requires an exact-minus-rolled contrast of at least 0.010, a correction within ±1,000 Hz, and a difference of at most 350 Hz between the even and odd CFO estimates. These scores describe the held aperture. They have a different meaning from the released fractional GLRT scores. [Native implementation](../../../tools/pipeline_eval/variants/experimental/receiver_scout_readout.inc)

Every lane still ran the original acquisition, and any confirmed primary still caused the original signed cancellation and residual scout. Both ranks used the same held check on untouched I/Q. Only 21 of 58 weak factors and 37 of 80 dense factors met the held contrast threshold at their original scout location. Only 19 weak and 28 dense met the frame-group CFO agreement. The median held contrast was about 0.008 in each sample. The corresponding released GLRT margins had medians 0.285 and 0.300. Substituting the held scores into the same continuation changed its selection on the dense prefix.

| Slice | Held primary / residual issued | Held primary / residual matched | Held factors on released-empty lanes | Rolled-first gates passed | Released → held continuation selections |
|---|---:|---:|---:|---:|---:|
| DS26 weak | 9 / 1 | 4 / 1 | 0 | 0 | 0 → 0 |
| DS30-0008 dense | 17 / 5 | 12 / 3 | 0 | 0 | 1 → 0 |

The rolled-first control exchanged the two templates and ran the same threshold and CFO checks on each coarse-confirmed rank. Neither weak nor dense I/Q passed that control. Synthetic checks separately recover a known signed CFO, identify a planted rolled pilot as a negative for the exact gate, and withhold silence. The known-positive and released-empty controls do not establish receiver false-alarm rates. [Component tests](../../../tests/pipeline_eval/test_receiver_scout_readout.py)

## Complete native cost ceiling

The table averages five alternating-order repeats of complete native calls with resident samples and initialized plans. The linked stock path calls the installed scout, cancellation and verifier and returns the installed factor bytes. The free readout arm drops the verifier load and all waveform checks after the scouts. It publishes no factors and serves as a timing floor only.

| Saved slice | Installed CPU / elapsed | Linked stock CPU / elapsed | Free readout CPU / elapsed | Held blocks CPU / elapsed |
|---|---:|---:|---:|---:|
| Weak | 3.784 / 3.786 ms | 3.762 / 3.762 ms | 2.382 / 2.383 ms | 2.435 / 2.435 ms |
| Dense | 2.568 / 2.569 ms | 2.552 / 2.552 ms | 1.835 / 1.836 ms | 1.870 / 1.870 ms |

The dense trace timed 0.100 ms of original-sample loading and 0.618 ms of verification per lane, including lanes that reached neither stage. The difference between installed and linked controls was under 1%. Even if the complete sample savings transferred to the recorded **37.338 CPU seconds** of full native calls, a free readout would save only **10.482 seconds**. Holding the measured outside-callback CPU fixed would leave **48.479 CPU seconds** of the original **58.961 CPU seconds** to reach sealed acquisition. This is a cost-attribution projection. It excludes cache transfer, storage waits, solver effects and position quality. [Full acquisition attribution](acquisition-split.md)

The older directed fixed-offset variant lowered scorer cost after an oracle supplied the final fractional time. It lost evidence with realistic proposals. The earlier selected-score path spent extra acquisition CPU restoring exact scores after continuation on dense saved windows. The held-block readout avoided both operations and paid for an independent physical score. Its losses and the free-readout ceiling rule out treating this substitution as the remaining all-visit 2× opportunity. [Earlier directed test](directed-verifier.md) · [Selected-score timing comparison](../single-core-2x/receiver-fractional-score-transfer.md)

## Reproduce

The measurements use only the original 18 weak stereo visits and the first 48 signed dense visits. Nine focused tests passed. The libm/compiled path and saved assets are pinned in the receipt.

```sh
bench=/tmp/leo-algo08v2-2x-bench
tree=/home/mouse9911/gits/leo-tracker-reduxredux
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
lock() {
  flock -x "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 timeout 48s "$@"
}
lock sudo -n -u leo env OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$PWD:$release/src:$release" "$release/venv/bin/python" -BPs \
  -m reports.ALGO08.v3.scout_readout_trial /var/tmp/leo-scout-readout \
  /opt/leo-algo08/algo08v3/payload/receiver.so "$bench/receiver-fractional-exact-v1" "$release/assets" \
  "$tree/reports/2026_11_20_single_scan_glrt/satellite-reference.zip" \
  /srv/bulk/leo-dev/ds30-full-20261121/bindings/DS30-0008.json /srv/bulk > /var/tmp/leo-scout-readout.json
lock env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  PYTHONPATH="$PWD:$release/src:$release" "$tree/.venv/bin/python" -BPs -m pytest -q \
  tests/pipeline_eval/test_receiver_scout_readout.py tests/pipeline_eval/test_receiver_directed.py
```

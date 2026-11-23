# Exact FIR reuse when a 12 ms receiver escalates to 20 ms

On 18 saved weak stereo visits, reusing the FIR prefix saved a median **65.8 µs native CPU per forced escalation** against starting the 20 ms call from scratch after 12 ms. The forced escalation still cost **1.25 ms more per lane than a fresh installed 20 ms call**. Every full signed factor matched byte for byte, including all 22 rank-1 factors. Even if the measured saving transferred to every one of the 11,834 short calls in the archived dense raw run, the projected gain over restarting would be **0.78 CPU s**. A retry policy would realize that saving only on escalated lanes. [Both CPU2 receipts](measurements/incremental-escalation.json.gz) · [Dense raw clocks and actual call counts](dense-full-short-raw.md)

## Exact reuse boundary

Both detectors search the same immutable stereo window, antenna, signed band and pilot. At 10 MS/s the short scout sees `[0, 120000)` input samples and the full scout sees `[0, 200000)`. The stride-four, 81-tap FIR result at output `j` has rightmost input `4j + 40`. Thus `j < 29990` has identical input support. The original AVX2 tiles start at 10 and span four outputs, so 29,990 is also an original tile boundary. The full scout copies the **239,920-byte** prefix, recomputes the ten previous short trailing edge outputs and computes 20,000 new outputs. It uses the released reduction order, coefficients and edge arithmetic. The hook holds two pointers and two integers and allocates no extra FIR workspace. [Native scoped hook](incremental_escalation.c) · [Pinned suffix build and benchmark](incremental_escalation.py)

| Stage | Exact overlap and required work |
|---|---|
| Lane input and FIR | Same mixer and its deterministic phase recurrence give the same first 120,000 converted values. The prototype still converts the entire full lane. It reuses only the proved FIR prefix from the short primary. |
| Timing covariance | The first eight normalized 4,740-sample timing planes fit below the shared FIR boundary. They and 36 of 105 unique pre-Jacobi covariance entries could be kept. Extending the covariance changes the eigenproblem. Both ordered projections require all 14 frames. The prototype recomputes the complete statistics, eigensolve and projections. |
| Timing, CFO and confirmation | The eight lag transforms and the carrier FFTs depend on the changed projections and timing picks. Refinement may share a per-frame operand when the exact epoch, coarse CFO and reduction path recur. The released early group count also changes from four to seven. No overlap in those requests was assumed. |
| Signed verifier and secondary | A short verifier that actually loads its input has the first 120,000 gathered samples for that lane. Its exact and rolled fractional gates depend on the longer scout and full verifier aperture. The original full readout recomputes both factors and their ordering. Its secondary scout starts from the original signed cancellation residual and always performs its own FIR. |

The research relink pins the recipes, relinks both pristine binaries to their original SHA-256 values, and adds a linker hook only around the FIR call. There is one scoped capture after the short primary and one opportunity to consume it in the longer primary. The two calls receive the same input pointer and signed interval. A different FIR, unsupported AVX2 path or missing prefix selects the original full FIR. The hook is disarmed before returning. An off-clock check matched all 50,000 assembled FIR outputs on each authentic lane, in addition to the complete full and short factors. [Native implementation and dependencies](incremental_escalation.py) · [Existing 8-to-12 ms analysis](resumable-primary-ceiling.md) · [Eight-frame scout geometry](short-primary-dead-work.md)

## Saved receiver comparison

The authenticated DS26 archive contains 18 weak physical stereo visits from five recordings. The tested lane mix was 20 lower-edge and 16 upper-edge calls, all using their original zero mixer. Four arms ran in each repeat. Both launches used three forward and three reverse repeats under the single low-priority Gauss CPU2 lock. Their receiver contexts, pilots and decompressed samples were ready before the clock. The two launches reproduced the same binary and factor digests, with 14 single-factor and 22 two-factor lanes. Rank 1 preceded rank 0 on three lanes. The short branch returned 34 factors and two empty results. The full secondary scout executed on all 36 authentic lanes in each linked arm. A separate +125 kHz check exercised the original nonresident secondary. A synthetic zero lane verified the full no-confirmation branch, and a one-ULP FIR mismatch forced exact fallback. [Input and factor digests, individual repeats, build commands](measurements/incremental-escalation.json.gz)

| Mode | Native CPU, ms/lane | Native elapsed, ms/lane | Batch CPU, ms/lane | Batch elapsed, ms/lane |
|---|---:|---:|---:|---:|
| Installed 20 ms | 3.758 | 3.759 | 3.780 | 3.780 |
| Same relink, fresh 20 ms | 3.737 | 3.737 | 3.758 | 3.758 |
| 12 ms then restarted 20 ms | 5.108 | 5.109 | 5.138 | 5.138 |
| 12 ms then FIR-resumed 20 ms | 5.030 | 5.031 | 5.059 | 5.059 |

These are medians of 12 repeat means. Pairwise native CPU savings versus restarting were **62.7 µs** with installed-first ordering and **72.6 µs** with resume-first ordering. The overall median was **65.8 µs** and the range was **−224.8 to +292.1 µs**. One repeat favored restarting. Forced resume exceeded fresh installed by **1.125–1.413 ms of native CPU per lane** in every repeat. The batch includes preparation of the harness call and factor readback. Both clocks exclude archive I/O, authentication, shared setup and publication. [Timing driver](incremental_escalation.py)

## Recording budget

The entire original 20 ms FIR took a standalone median **144 µs** per call in both launches. Even giving away that entire primary stage for every short opportunity projects to only **1.70 s** at the archived dense count. The historical dense prefix priced the whole FIR and whole mode stage at **152 + 169 µs** per scout. Their combined **3.80 s** at the same count is a generous transferred ceiling for those two stages. It grants free six-frame normalization and new covariance entries, the 14-frame eigensolve, both projections and the FIR suffix. Those calculations remain necessary. It leaves all read, decode, verification and signed secondary work in the raw budget. The observed projected 0.78 s is (0.78p) s if the retry fraction is (p) and the saved-panel costs transfer. [Dense stage profile](receiver-polyphase-timing.md) · [Authenticated input coverage](authenticated-input-coverage.md) · [Dense budget](next-2x-directions.md)

Using each repeat's paired native clocks, the incremental cost of the short attempt is estimated by restart minus fresh on the same relink. The remaining full extension cost is forced resume minus that estimate. Under homogeneous lane costs the selective schedule breaks even with all-fresh 20 ms at a median retry rate of **65.6%**, with a 62.8–67.7% repeat range. The estimate gives accepted short outputs for the other lanes and does not price the selector. It does not establish how many exact retries localization needs. Only forced lanes were tested for exact 20 ms parity. No new capture, complete raw replay, selection change, position result or publication timing was measured. [Frozen next routing question](next-2x-directions.md)

## Reproduction

The compact receipt SHA-256 is `b6ddca5f79fd0fff912cf83f503bf232813bfd3ba4e556862f4a799588f5d6ad`. It contains both full benchmark receipts and their original JSON digests. The first launch timed the same arms and flags. The second added the extra synthetic-zero check and edge labels outside the clocks. Five component and adjacent tests passed, including full FIR reconstruction across both boundaries and the one-use fallback. [Tests](../../../tests/pipeline_eval/test_incremental_escalation.py)

```bash
install_root=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
weak=/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_20_single_scan_glrt/satellite-reference.zip
gauss() {
  flock -w 60 -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
    sudo -n -u leo ionice -c2 -n7 nice -n15 taskset -c 2 env \
    TMPDIR=/dev/shm PYTHONPATH="$PWD:$PWD/src:$install_root/src:$install_root" \
    OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 "$@"
}
gauss "$install_root/venv/bin/python" -B -m reports.ALGO08.v3.incremental_escalation \
  --work /dev/shm/leo-incremental-escalation-rebuild --weak "$weak" \
  --receipt /dev/shm/leo-incremental-escalation-rebuild.json
gauss "$install_root/venv/bin/python" -B -m pytest -q -p no:cacheprovider \
  --basetemp=/dev/shm/leo-incremental-escalation-rebuild-tests \
  tests/pipeline_eval/test_incremental_escalation.py tests/pipeline_eval/test_receiver_short_signed.py
```

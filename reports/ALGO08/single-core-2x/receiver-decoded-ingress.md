# Decoding sealed ingress after the compressed-buffer optimization

Decoding a whole Zstandard member in one call added **32–37 ms of acquisition CPU** on matched physical prefixes. Using three reusable per-window buffers avoided every owned-window allocation in the measured chunks, but still added **0.9–8.6 ms**. Both prototypes reproduced the raw authority and ordered detection probes with the frozen `950c2b94` receiver. The existing compressed-member input buffer remains the faster measured path. [Timing and output receipts](receiver-decoded-ingress-results.json)

## What was removed

The earlier whole-chunk trial filled a bytearray using streaming `readinto` and also cost more than the compressed-only path. This follow-up used the installed Zstandard decoder's one-shot operation to request one exact-size output bytes object, then lent its read-only slices to the existing reader. It checks the known frame size before allocating because the one-shot API can use that size in place of the explicit output bound. It uses the original stream on an unexpected decoded length, any decoding failure or extra compressed data, and when the experimental 128 MiB allocation limit is exceeded. The limit applies only to optimization eligibility. [Earlier decoded-buffer comparison](receiver-ingress.md)

The per-window route uses the released stream's `readinto` with three scratch buffers sized to the requested window. A borrowed array keeps that slot in use. If all slots are still borrowed, the stream returns its ordinary owned bytes. Three slots accommodate the previous yielded window and the active geometry and hash checks when the reader verifies the remainder of a sealed chunk beyond the acquisition prefix. A two-slot trial still made twelve owned-data reads per chunk. The third slot removed all twelve, leaving the original one-byte trailing check.

The same reader still checks the compressed member and index SHA-256, each window SHA-256 and the full decoded-chunk SHA-256. It uses the same index order, geometry, metadata and prefix clipping. New tests compare emitted windows and subsequent errors on malformed indices and frames, truncation, oversized members, declared size disagreement, extra decoded bytes, trailing compressed data and concatenated frames, including an empty trailing frame. A window outside the requested range can still fail checksum validation. The tests also verify that a retained NumPy view stays read-only and receives no overwritten data when another window is read. The ingress and storage test invocation passed **33 tests**.

## Matched CPU

Each case used the first 40 scheduled visits. The reader verified the entire 64-window compressed member for both variants. Both input edges were tested twice per prototype, reversing arm order within each edge and alternating which arm ran first across the edges. All timings use process CPU and exclude publication.

| Saved prefix | Valid visits | One-shot reader increase | One-shot acquisition increase | Three-buffer reader change | Three-buffer acquisition increase |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS30-0016, lower edge | 36 | 37–38 ms | 32–37 ms | −0.9 to +2.4 ms | 0.9–8.6 ms |
| DS30-0374, upper edge | 29 | 38 ms | 37 ms | +1.1 to +1.4 ms | 1.7–2.0 ms |

The profiler measured **74–78 ms** for the original Zstandard calls, **110–112 ms** for one-shot decoding and **75–76 ms** with all window allocations removed. The one-shot comparison's process high-water mark rose by about 93 MiB when the first variant arm ran. The three-buffer comparison did not allocate an entire decoded chunk. On these prefixes, making all original Zstandard calls free would remove only **18–21%** of acquisition CPU. Window allocation reuse left that decompression cost intact and showed no repeatable reader saving.

## Reproduce

The presets are available in the isolated acquisition profiler. The publication runner and its compressed-only input context were left unchanged. Both arms use packed receiver SHA-256 `950c2b9412020317654fd7c79d30063e9258b70152ed9c91b4129d379ac75a13`, as built in the verifier study. [Frozen receiver recipe](receiver-stencil.md)

```bash
algo08_work=/tmp/leo-algo08v2-2x-bench
algo08_python=/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python
algo08_bindings=/srv/bulk/leo-dev/ds30-full-20261121/bindings
algo08_detector="$algo08_work/receiver-stencil.so"

algo08_lock() {
  flock -x "$algo08_work/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src timeout 80s "$@"
}

for strategy in direct window; do
  algo08_lock sudo -n -u leo -- env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 /opt/leo-algo08/current/venv/bin/python \
    -m tools.pipeline_eval.variants.experimental.receiver_acquisition_profile \
    "$algo08_detector" "$algo08_detector" \
    "$algo08_bindings/DS30-0016.json" "$algo08_bindings/DS30-0374.json" \
    --bulk /srv/bulk --assets /opt/leo-algo08/current/assets --visits 40 \
    --control-ingress compressed --ingress "$strategy" --repeats 2
done
algo08_lock "$algo08_python" -m pytest -q tests/pipeline_eval/test_experimental_receiver_direct_decode.py \
  tests/pipeline_eval/test_experimental_receiver_ingress.py tests/storage/test_short_window_storage.py
```

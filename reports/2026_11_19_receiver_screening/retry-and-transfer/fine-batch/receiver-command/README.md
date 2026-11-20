# Four-frame pruned fine search in the saved-I/Q receiver

Use `--fine-search batched` to run the exact prefix transform with four independent frames per AVX2 batch. The default remains the installed fine scorer. `--fine-search pruned` selects the original one-frame prefix transform. Either optimized fine scorer can be combined with the row-wise peak selector. [Normal receiver and input contract](../../../original-support/receiver-command/README.md) · [Four-frame qualification](../README.md)

```sh
.venv/bin/python -m tools.pipeline_eval.original_receiver \
  --case DS29-0174 --out /var/tmp/ds29-batched-fine --cpus 22 \
  --peak-selector row-wise --fine-search batched --raw-limit 120 --smoke
```

The command authenticates the supported producer and NumPy/PocketFFT runtime, checks AVX2 availability, verifies the native library digest, and checks both native transforms against the original FFT on worker startup. It can reuse a verified `fine_batch.so` in `--kernel-dir` or the default qualified installation. With a missing binary it compiles the pinned C source locally and requires the same qualification digest. The source lock records the chosen backend, four frame lanes, source and library hashes, and installation time. The summary carries the worker's arithmetic check and original-scorer fallback counts. [Runtime and exactness evidence](../qualification-lock.json) · [Pruned receiver command](../../../pilot-search-and-region/fine-search/receiver-command/README.md)

## Paired command check

The first DS29-0174 chunk replayed sequentially on CPU 22, using the one-frame pruned scorer and then the four-frame scorer. Both kept full fractional candidate scoring and row-wise coarse selection. Each worker had a 120-second limit, 512 MiB of charged memory and zero swap. All 64 ordered visit records matched byte for byte after omitting only the detector CPU and wall fields. Both kept 128 probes, 585 projected candidates and 157 fractional gate passes. Each used its selected transform 1,128 times with zero installed-scorer fallbacks. [Raw command receipts](smoke-receipt.json) · [Actual shared visit records](smoke-visit-records.json.gz)

| Fine scorer | Setup wall | Valid detector CPU | Median valid detector wall | Raw coordinator wall | Peak cgroup memory |
| --- | ---: | ---: | ---: | ---: | ---: |
| One-frame pruned | 1.68 s | 40.98 s | 570.79 ms | 51.20 s | 286.45 MiB |
| Four-frame batched | 1.75 s | 36.23 s | 525.73 ms | 44.25 s | 293.98 MiB |

The batched run used 11.6% less detector CPU in this single sequential pair. Both reused their pinned libraries, and zero of 64 visits met 20 ms in each mode. The detector smoke covered 64 of 6,774 saved visits and ended before position fitting. The full replay carries the position and frequency results. An initial setup failed before raw launch because the screened acquisition checksum in the command omitted one digit. The corrected checksum matches the installed file and frozen qualification, and a regression test checks all three producer pins. [Component tests](../../../../../tests/pipeline_eval/test_original_receiver_batch.py) · [Full batched waveform](../../batched-waveform/PROTOCOL.md)

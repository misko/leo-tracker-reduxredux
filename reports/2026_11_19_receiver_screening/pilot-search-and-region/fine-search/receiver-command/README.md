# Pruned fine CFO search in the saved-I/Q receiver

Add `--fine-search pruned` to select the qualified prefix transform on supported authenticated recordings. The installed fine scorer is the default. The fine search, row-wise coarse peak selection and final interior publication guard are independent options. The command accepts either a frozen `--case` or an authenticated `--input` locator. [Recording and deployment requirements](../../../original-support/receiver-command/README.md) · [Row-wise peak selector](../../../receiver-deadline/receiver-command/README.md)

```sh
.venv/bin/python -m tools.pipeline_eval.original_receiver \
  --case DS29-0082 --out /var/tmp/ds29-pruned-smoke --cpus 3 \
  --peak-selector row-wise --fine-search pruned --interior-guard \
  --raw-limit 120 --smoke
```

The pruned option authenticates the capture producer and the fine-search sources from the qualified installation, plus NumPy 2.5.2 and its PocketFFT extension. Each worker verifies exact prefix arithmetic before processing I/Q. An unqualified runtime fails the requested pruned execution. The scorer uses the installed implementation on individual calls outside its supported geometry, and the run summary records the number of pruned and installed-fallback calls per worker. [Detector qualification](../README.md) · [Qualification seal](../qualification-lock.json)

Place the SHA-256-verified `fine_search.so` beside the other files in an operator-supplied `--kernel-dir` to reuse it. The default library lookup can also reuse the existing qualified installation. When neither applicable location supplies a binary, the command compiles the pinned C source in the new local output directory and checks the resulting binary against the qualified digest before staging it. This permits the qualified host and toolchain to build without the earlier study directory. A present binary with a different digest is rejected. Build and verification wall is recorded in the source lock and included in command setup wall, which is measured separately from raw replay.

## Paired command check

Both normal commands replayed the first 64 of 6,772 saved DS29-0082 visits on CPU 3, in installed-then-pruned order. Each worker had 120 seconds, 512 MiB charged memory and zero swap. Both used row-wise coarse selection and recorded the same interior guard. The ordered visit records matched byte for byte after omitting only the detector CPU and wall fields. Each arm retained 48 valid and 16 capture-invalid visits, 96 physical probes, 442 projected candidates and 77 fractional gate positives. The valid detector paths finished within 20 ms on zero of 48 visits in each arm. [Matched worker receipts and comparison digest](smoke-receipt.json)

| Fine scorer | Command setup wall | Valid detector CPU | Median valid detector wall | Raw coordinator wall | Peak cgroup memory |
| --- | ---: | ---: | ---: | ---: | ---: |
| Installed | 1.41 s | 18.09 s | 409.94 ms | 47.61 s | 222.91 MiB |
| Pruned | 1.34 s | 16.80 s | 401.85 ms | 34.41 s | 225.71 MiB |

The pruned run compiled and verified the library in 0.124 s within command setup, passed the runtime check, and used the prefix transform for 872 calls with zero installed fallbacks. Detector CPU fell by 7.1% in this sequential pair. Raw wall includes archive I/O, worker launch and terminal verification under shared host load. A separate setup-only check reused the staged binary from a supplied directory without invoking the compiler. The command check stopped after detector output under `--smoke`. [Interleaved detector timing](../README.md) · [Whole-waveform position study](../../field-exact-waveform/PROTOCOL.md)

# Row-wise peak selector for the saved-I/Q receiver

Add `--peak-selector row-wise` to run the qualified row-wise selector with the prepared original detector. Omitting the option or selecting `installed` uses the original installed selector. The same flag works with an authenticated `--input` locator or a frozen `--case`. Full mode feeds the newly emitted detector factors into the same compact fit for both calibration arms. [Normal receiver usage and input contract](../../original-support/receiver-command/README.md)

```sh
.venv/bin/python -m tools.pipeline_eval.original_receiver \
  --case DS29-0082 --out /var/tmp/original-row-wise-smoke \
  --cpus 10 --raw-limit 90 --peak-selector row-wise --smoke
```

The row-wise option requires one of the three qualified capture producer installations and checks its acquisition source and the row-wise source byte for byte against the qualification hashes. New `source-lock.json` and `summary.json` outputs record the backend, version, source path and SHA-256. The row-wise record adds the installed acquisition source hash and qualification receipt hash. Earlier locks that lack the option identify the historical installed backend. [Selector qualification and producer coverage](../prepared-hotpath/README.md) · [Qualification receipt](../prepared-hotpath/qualification-lock.json)

## Paired command check

Both modes completed the same first DS29-0082 chunk on CPU 10, in installed-then-row-wise order. Each worker had a 90-second deadline, a 512 MiB charged memory limit and zero swap. The ordered visit data were byte-identical after omitting only the two elapsed-time fields. Each arm kept 48 valid and 16 capture-invalid visits, 96 physical probes, 442 projected candidates and 77 fractional gate positives. The matched visit bytes include source I/Q hashes, clock and RF fields, validity decisions, candidate order and scores. [Matched run receipts and comparison digest](smoke-receipt.json)

| Selector | Valid detector CPU | Median valid detector wall | Raw coordinator wall | Peak cgroup memory | Valid visits within 20 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| Installed | 37.50 s | 699.03 ms | 48.93 s | 294.74 MiB | 0 / 48 |
| Row-wise | 33.93 s | 650.02 ms | 41.50 s | 247.24 MiB | 0 / 48 |

The row-wise run used 9.5% less valid detector CPU in this single sequential pair. The raw coordinator wall includes worker launch, archive access and terminal verification. This check replayed 64 of 6,772 saved visits and stopped after detector output under `--smoke`. The interleaved selector panel supplies the detector timing comparison across producers. The separate whole-waveform study carries the paired position and frequency evidence. [Interleaved detector panel](../prepared-hotpath/README.md) · [Whole-waveform comparison protocol](../selector-waveform/PROTOCOL.md)

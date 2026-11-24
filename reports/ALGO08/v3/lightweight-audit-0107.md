# Fresh DS30-0107 raw withholding with the merged lightweight audit writer

The merged all-member worker finished in **0.536 s** wall and **0.532 CPU s**, versus **0.967 s** wall and **0.956 CPU s** for the earlier exact all-member worker on the same original member and map. The observed through-exit reductions were **0.431 s wall** and **0.425 CPU s**. Both produced the same verified withholding. The new acquisition audit is byte-identical to the old serializer's output for that same fresh audit object. [Machine receipt](measurements/lightweight-audit-0107.json.gz)

| DS30-0107 condition | Wall, s | CPU, s |
| --- | ---: | ---: |
| Historical installed ALGO08v3 | 1.497 | 1.496 |
| Earlier matched original-file ordinary 20/8 ms worker | 0.549 | 0.547 |
| Earlier basic literal-map worker | 0.917 | 0.914 |
| Earlier exact all-member worker | 0.967 | 0.956 |
| Fresh exact all-member worker with lightweight writer | 0.536 | 0.532 |
| Fresh worker with measured custody and source checks charged | 1.555 | 1.545 |

The signed native file, terminal, scan report, proof and support all matched. Both actual terminal files were byte-identical. Both arms had null positions and no RF value under `no_active_curvature`, with no path, grid or PNG. The reader authenticated all 33,519,983 encoded bytes in the original member and committed 24,960,000 decoded bytes on eight full and 19 short visits. It kept both invalid visits in the acquisition ledger and returned the same 54 supported opportunities and 19 signed factors. The original and detached map were already resident, and no map preparation read or extra comparison child ran. The fresh process recorded zero input blocks and major faults. [Original all-member control](legacy-block-all-0107.md)

The cross-run audit's data and schema matched after excluding its named live CPU, wall and resource counters. Re-encoding the fresh audit with the actual old scientific serializer reproduced its complete sorted JSON bytes, including integer precision and the final newline. The fresh audit SHA-256 is `59a9238293462f0b0b390bc1305cefe9808a8534f6dd444217e28ccd2522afdf`. The earlier isolated writer test showed a roughly 300 ms import cost. The full-process clocks bracket normal input, launch and verification work as well. The one-off fresh admission took 1.019 s wall and includes external source, metadata and residency checks. The earlier all-member admission was 0.890 s. [Writer-only comparison](legacy-map-receipt-writer.md)

The fresh worker used integrated base `133b6374d` with the pinned `legacy_block_all_entry.py` and its original native decoder and literal map. Across the archived runtime source pins, the differences were the merged map audit writer and an exception-map preparation helper in `legacy_block_multi.py`. The literal-only raw child did not call that helper. All native and scientific options were carried forward with only the entry location and output changed. This is one fresh through-exit observation under the shared low-priority Gauss lock, with archival controls as shown. [Frozen launch protocol](lightweight-audit-0107-protocol.md) · [Driver and verification](lightweight_audit_0107.py)

The launch froze at `49f40cef0`. Seven component and adjacent tests passed. The unpacked receipt SHA-256 is `64fa809fcff4f146244db5e2a5bcc354fbaca14d5da558d52e76df8096a74cd8`. The prediction seal is `b6b6e263f54edf14bd492d9cc5366778c6f81e6caa0e871820e83dda17e80d5f`.

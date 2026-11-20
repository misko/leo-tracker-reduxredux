# Direct compact v5 cavity at 512 MiB

The staged direct receiver returned no position on either ordinary recording under a true 512 MiB, zero-swap Linux service. Both exact staged workers entered native preparation and were OOM-killed before initial selection started. Disabling retention of parsed TLE snapshots let both recordings finish preparation. Both follow-up workers were then OOM-killed during initial selection. All four attempts remain in the chart and receipts. The separate lifetime-cavity service returned both arms on the same inputs. [Both-arm charts](charts/index.html) · [Attempt and source seal](receipt.json) · [Measured resources](resources.csv)

| Input and pin | Entry | Last stage entered | Supervisor wall s | Cgroup CPU s | Peak through initial entry MiB | Final peak MiB |
|---|---|---|---:|---:|---:|---:|
| DS26-0036 · CPU 4 | Staged direct | Native preparation | 14.88 | 14.19 | Incomplete | 512.00 |
| DS26-0036 · CPU 4 | Direct with zero-retention parser | Initial selection | 25.71 | 25.21 | 390.03 | 512.00 |
| DS29-0082 · CPU 5 | Staged direct | Native preparation | 14.58 | 14.19 | Incomplete | 512.00 |
| DS29-0082 · CPU 5 | Direct with zero-retention parser | Initial selection | 30.12 | 29.60 | 409.64 | 512.00 |

All four services confirmed `memory.max = 536870912`, `memory.swap.max = 0`, and zero sampled swap. The workers used one pinned numerical thread at nice 10, with a 165-second service limit. Systemd reported `oom-kill` and SIGKILL for each outcome. Supervisor wall includes service launch and teardown. The high-water sample at initial-selection entry includes preparation and the first scan context construction. The qualification observer records coarse stage entries. In the baseline the interval after the last entry includes preparation and first scan setup. In the modified workers the last entry was initial selection. [Protocol](PROTOCOL.md) · [Service limits and status evidence](receipt.json)

## One allocation change

The prior matched preparation study accounted for 160.80 and 197.26 MB of retained parsed TLE records on these same ordinary captures. It established that snapshot eviction preserves catalogue bytes, forecast, ordering, and the two position fits. The capped variant uses the existing strict `ElementParser` with `maximum_bytes=0` at the direct preparation call. It still parses and validates each archive snapshot required by the original policy. Repeated snapshots may be parsed again. The build changes only the direct worker’s parser construction and import in a separately sealed bundle. Every other source file and the rebuilt native numerical binary match the original staged release byte for byte. The running worker keeps the existing direct numerical bindings and uses no extra source-rewriting layer. [Prior parser lifetime measurements](../../refinement/history-stream/README.md) · [Bounded build recipe](../../../../tools/pipeline_eval/qualification/direct_cavity_cap_bundle.py) · [Bounded source ledger](bounded-lock.json)

The follow-ups show that parser retention is sufficient to change where these capped jobs stop. They do not establish a lower complete-worker peak or verify the capped variant’s geographic and RF endpoints. Separate same-input profiling measured large whole-catalogue projection and association arrays in early discovery, where both modified workers next stopped. The later fit was never reached in any capped direct attempt. [Existing discovery measurements](../../working-memory/README.md)

## Same-input lifetime control

The archived whole-IQ lifetime-cavity workers returned both fixes under the same 512 MiB zero-swap limit. Their sealed native, causal catalogue and offered tile match this trial. Their sealed prior request bytes and canonical scientific request also match. Those workers used additional bounded numerical stages and a wider whole-IQ service time budget on different pins. Their endpoint coordinates and conditional Doppler RMS match the unrestricted staged direct outputs exactly. There are no capped direct coordinates or RF scores to compare. [Whole-IQ lifetime results](../whole-pair/README.md) · [Match and publication status](parity.json) · [Per-arm geographic and RF scores](scores.csv)

| Lifetime cavity control | `c = 0` error km | Fitted `c` error km | `c = 0` RMS Hz | Fitted `c` RMS Hz |
|---|---:|---:|---:|---:|
| DS26-0036 | 0.218118 | 0.180112 | 102.253327 | 102.288908 |
| DS29-0082 | 2.789469 | 2.654183 | 106.672251 | 106.588481 |

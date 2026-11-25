# Standalone held-odd CFO features

`held_cfo_features.derive(native, approved_graph_config)` takes an already authenticated signed 20/8 packet with the original one-in-eight full anchors and its release `TrackConfig`. It removes both radios' factors at held odd visits before rebuilding the released Graph. The same-radio and RF straddlers must agree on the Graph piece and alias lift and pass the frozen spacing, slope and wrapped-arrival checks. A nonempty target within one original 20 ms frequency bin of the prediction gets half of the signed frequency difference. The target's measured arrival is preserved.

`apply_to_winners(native, ordinary_winning_rows, features)` binds the separate CFO features to the original packet and edits only the measured CFO in the matching observation rows. It checks original values and observation IDs, and rejects missing edits or a different packet. The caller retains the native packet, signed source and detector identities, opportunity order, RF, arrivals and margins. Only the stage module and the released `leo.analysis.localization_v3.tracks` entry are needed beyond the Python standard library and ordinary numerical runtime. The audit worker and its historical case fixtures are separate from the callable.

Both fresh CPU3 checks and the CPU2 measurement reproduced every frozen forecast, gate and edit, and the complete winning-observation arrays consumed by the earlier saved position workers. The original native packet and extraction metadata were unchanged. DS30-0019 applied 366 edits among 4,996 ordinary winners. DS30-0274 applied 499 among 6,596. No new position fit was run.

## Measured added work

One fresh serial child per case ran on CPU2 at nice 15 with idle I/O and one numerical thread, under the exclusive shared Gauss lock. The two children occupied 2.009 s shortly after the verified DS30-0155 storage deferral. The scientific files were checked read-only tmpfs operands, with 20,799,808 resident bytes at preflight. The capsule denied access to backing storage, the campaign source tree, the historical audit module and IPv4, IPv6 and Unix sockets. A clean import and each timed derivation succeeded in that namespace. Historical comparison operands were opened after the feature stopwatch. The first two preflights corrected a residency rounding check and the order of the negative path checks and audit hook. Neither ran a Graph or used the CPU2 timing slot.

| Boundary | DS30-0019 wall / CPU (s) | DS30-0274 wall / CPU (s) |
| --- | ---: | ---: |
| Sealed source and Graph-config checks, decoding | 0.047 / 0.047 | 0.055 / 0.055 |
| Ordinary winning-observation extraction | 0.053 / 0.053 | 0.069 / 0.069 |
| **Added masked Graph, forecast and applied rows** | **0.602 / 0.600** | **0.781 / 0.781** |
| Independent historical readback and equality checks | 0.102 / 0.102 | 0.132 / 0.132 |
| Fresh child through exit / Python CPU through readback | 0.885 / 0.866 | 1.123 / 1.107 |

The feature stopwatch starts with the authenticated native and its ordinary winning rows in memory. The ordinary extraction is already part of normal publication. The remaining 0.080 and 0.086 s of child wall cover interpreter, import and namespace checks, receipt serialization and exit together. There was no separate import-only timing. Wrapper CPU was below 0.002 s per case. The timed feature logged minor/major faults of 2,853/2 and 4,316/0 and process peak RSS of 66.2 and 71.4 MiB before the post-time comparisons. DS30-0019 incurred 840 process input blocks during the feature in the restricted environment. This counter does not attribute the blocks to a particular approved runtime file.

For DS30-0274 the measured 0.781 s would consume about 57% of the previously recorded 1.363 s raw half-time headroom, leaving 0.582 s by subtraction. This is a single stage-only observation on each saved case. It establishes no integrated speedup or added production overhead from startup, feature persistence, or solver changes. The running field entry was unchanged.

[Frozen protocol](held-cfo-features-protocol.md) · [Callable](held_cfo_features.py) · [Sealed CPU2 timing](measurements/held-cfo-features-timing.json.gz) · [Kernel preflight and separate parity checks](measurements/held-cfo-features-verification.json.gz)

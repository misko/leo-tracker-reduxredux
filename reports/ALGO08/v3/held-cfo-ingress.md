# Reusing ordinary Graph ingress for held-odd CFO

`held_cfo_ingress.derive(native, approved_graph_config, original_winners)` accepts the authenticated 20/8 packet and the released winning rows already needed for ordinary Graph. It checks each observation's native identity, its order, clock-derived time, RF, receiver, channel, signed winner and margin. The same stereo timeline defines the held or retained visit, including empty opportunities and excluded-visit gaps. The retained winners keep their original order, receiver numbers and times and enter the released `graph_tracks` directly. The released curvature check, signed alias and arrival logic, forecast and half-bin rule, and the existing `apply_to_winners` overlay follow. The native packet stays unchanged. The frozen masked-document callable remains available with its original behavior.

Both paths reproduced the complete sidecar and consumed rows on each saved recording and in each timing order. DS30-0019 produced 366 edits among 4,996 ordinary winners, DS30-0274 produced 499 among 6,596. Complete corrected rows matched the earlier saved position workers. Contract tests also checked stereo and stream masking, original winner tie-break, empty input factors, ordering and rejection of missing, extra, duplicate and changed rows. The callable assumes the native packet has already passed the ordinary released evidence boundary.

The follow-up consumes the supplied winners once and filters the rows kept in their validated insertion order. The regression uses a one-shot generator and requires the released masked Graph to produce tracks and CFO edits. The separate overlay accepts the original reusable rows or a fresh iterable. The timing and two saved-fixture receipts below remain bound to `28ea3205a`, the revision before this correction.

## One isolated comparison

| Case | Order | A wall / CPU (s) | B wall / CPU (s) | Saved wall / CPU (s) |
| --- | --- | ---: | ---: | ---: |
| DS30-0019 | AB | 0.601 / 0.599 | 0.539 / 0.539 | 0.062 / 0.060 |
| DS30-0274 | BA | 0.768 / 0.768 | 0.827 / 0.724 | −0.059 / 0.044 |
| DS30-0274 | AB | 0.786 / 0.786 | 0.717 / 0.717 | 0.069 / 0.069 |
| DS30-0019 | BA | 0.618 / 0.617 | 0.558 / 0.551 | 0.060 / 0.066 |

A is the frozen artificial masked packet route. B is the new ordered ingress. Every phase starts with both the native packet and the ordinary winning observations in memory. It pays all checks, Graph and forecast work for its route, and ends with the actual corrected rows. B's ingress binding and verification are included in its clocks. The common verified input/config decode cost 0.049–0.057 s wall per child and ordinary winner extraction cost 0.054–0.070 s. Independent verification after both phases took 0.117–0.170 s. Whole child wall, including both phases, was 1.438–1.951 s. The remaining 0.072–0.083 s wall covers interpreter, import, namespace proof, serialization and exit together. The experiment did not isolate an import-only cost or a separate B-only binding timer.

Mean CPU savings were 0.063 s on DS30-0019 and 0.057 s on DS30-0274. On DS30-0274 B ran slower in wall time when it went first despite spending less CPU. That phase had a 0.104 s wall–CPU gap, one major fault and 504 process input blocks. The counters give no exact attribution of the gap. A single run in each order shows a small CPU improvement and order-sensitive wall time. The 0.717–0.827 s B wall range would leave 0.536–0.646 s of DS30-0274’s previously measured half-time headroom by subtraction. This is stage arithmetic without an end-to-end clock.

The four fresh children finished in one 6.767 s exclusive CPU2 slot, nice 15 with idle I/O and one numerical thread. The official DS30-0155 storage deferral was 99 ms old at admission and had no live field child. Preflight proved the exact approved mount and network restrictions. The 20,809,479 bytes of staged scientific inputs and trial source were resident. Only saved detector and comparison operands were read. This run made no field change and performed no receiver, orbit or position work.

[Frozen protocol](held-cfo-ingress-protocol.md) · [Opt-in callable](held_cfo_ingress.py) · [Timing and verification receipt](measurements/held-cfo-ingress.json.gz)

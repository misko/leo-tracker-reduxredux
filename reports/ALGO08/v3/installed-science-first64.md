# Where a science-preserving ALGO08v3 change must save time

The largest observed installed interval is **4,153.169 seconds from launch to native detector output**, 65.8% of the frozen first-64 wall total. Even giving away every later stage and all waiting leaves a **3,360.934 s lower bound on pre-output CPU**. That is **205.270 s above** the summed half-time target, with a paired median time ratio of **0.54361**. A port that only changes downstream computation or storage wait cannot reach 2× on this one-core workload. The required reduction is in work still paid before native output, independently of any modeled all-full callback rate. [Per-case source bindings, clocks and thresholds](measurements/installed-science-first64.json.gz)

## What the installed process already pays for

| Disjoint recorded wall boundary | First 64 (s) |
| --- | ---: |
| Launch through native detector file write | 4,153.169 |
| Native write through signed inventory write | 4.784 |
| Inventory write through standard terminal, 62 successful exits | 1,903.516 |
| Inventory write through the two actual solver-failure exits | 39.722 |
| Terminal write through child exit | 178.910 |
| Independent verification | 31.225 |
| Verified total | **6,311.327** |

The installed source signs `ingress=paired-sha256`, `schedule=all`, and a screened/tiled original solver. It already uses buffered snapshot reads, paired decoded hashes, native TLE parsing and Graph paths, sparse rank projection, endpoint reuse, recovery reuse and direct curved design. Its `member_lookahead` port gives the kernel a `POSIX_FADV_WILLNEED` hint for up to 16 MiB of the next signed member. It retains no full speculative buffer or leased destination. The verified receipts report **83.785 GB of advisory extent and 20.554 process CPU s** around this port on 62 successful exits. They do not supply the charted successor's wholly different full-member producer cost. [Pinned run specification and observed port counters](measurements/installed-science-first64.json.gz) · [Charted producer boundaries](first64-producer-transfer.md)

The installed numerical grid already runs the native posterior handoff. Its factor path activated on **54 of 58 fixes**, with 19,224 factor calls. One more had predictive calls without a native factor call, and three had no recorded predictive calls. The installed renderer is `lossless-raster` with pinned native PNG filtering and deflate. The candidate's direct six-figure Cairo renderer, later checked posterior exporter, portable causal index and exact grouped catalogue rank are separate ports. It would double count existing work to credit the original PNG and posterior optimizations again. Giving away the entire terminal-to-exit tail **and** common verification saves at most 210.135 s. That leaves 2,945.529 s above half-time, so rendering and verification have little leverage here. [Standalone saved Cairo comparison](exact-named-cairo.md) · [Installed publication code binding](measurements/installed-science-first64.json.gz)

## Hard limits of the recorded path

All 64 original detector-write prefixes individually exceed their own half-time budgets. The recorded prefix includes startup, signed input reads and decompression, native detection and the original output write. The stock receipts contain no exclusive clock for the full acquisition or its detector callbacks. For each case, let \(P\) be wall through the detector write, \(T\) be child wall through exit, and \(C\) be child CPU. A single processor can supply at most \(T-P\) CPU after the write. The lower bound before the write is \(\max(0,C-(T-P)-0.010)\) seconds. The 10 ms allowance preserves the earlier clock-reconciliation tolerance. The file timestamps define data-write boundaries and may put subsequent durability work into the following interval. The newly audited prefix reproduces the first 30 archived marker and cost records exactly. [Earlier frozen clock method](installed-receiver-first30.md)

| Favorable scenario with installed outputs held fixed | Net wall charged (s) | Remaining above half (s) | Paired median time ratio |
| --- | ---: | ---: | ---: |
| Entire post-detector tail free | 4,153.169 | 997.506 | 0.65807 |
| Entire tail and every wait free, using the lower prefix CPU allocation | 3,360.934 | 205.270 | 0.54361 |
| Also grant all reported stock hint CPU, and make both failure prefixes with missing hint counters free | 3,211.739 | 56.075 | 0.53848 |

The last row deliberately removes more than any comparable measured ingress change. It still misses both timing gates. These limits describe ports with unchanged CPU elsewhere in the recorded prefix. A new implementation that materially reduces original input or full-detector CPU can change that prefix. The clocks cannot identify which part of it supplies an adequate reduction. [Individual-case savings ceilings](measurements/installed-science-first64.json.gz)

## One exact splice and the threshold it would need

The compatible unmeasured combination keeps the installed all-20 ms detector and chronological continuation, uses the existing authenticated owned-window/full-member destination pool at the original source iterator, and calls the exact named numerical ports with the original raster renderer and full verification. It would need distinct research provenance, complete original manifest, index, encoded and decoded checks, identical native rows, both named arms and owner order, the unchanged standard grid, path and PNG content, and the original failure or withholding route. Source or state mismatch would use the ordinary original route. This composition differs from the raw exact-detector control, which used the charted downstream solver and renderer. [Raw full-science detector control](installed-receiver-control.md) · [Exact named solver binding](exact_named_route.py)

DS30-0016 is the best existing physical donor for the receiver and owned input combination. It reproduced the installed packet, terminal, both arms and owner rows byte for byte where applicable. Its **5.661 s actual authenticated acquisition already exceeds the entire 5.412 s historical half-child budget**. It took 10.935 s through raw exit plus 0.409 s for common verification. The historical installed raw child took 10.824 s, with different process faults and no matched common verification clock. This donor establishes scientific compatibility and shows no whole-runtime gain on that source. The strongest ordinary dense saved solver donor, DS30-0374, preserved both fits, 2,905 ordered owners per arm and all eight PNGs. Its complete saved child improved **28.324 to 23.630 s**. The larger proportional DS30-0160 improvement includes a special history retry and should not price ordinary cases. [Dense same-packet solver](exact-named-dense.md) · [Other named-port physical comparisons](exact-named-0402.md)

Generously apply the entire ordinary dense saved rate, a **16.57% reduction**, to each completed first-64 inventory-to-terminal span. Cap it there per case and give away the independently timed terminal tail and verifier as well. This gives **315.426 + 210.135 s** of savings, while the original detector prefixes still cost 4,153.169 s. Both timing gates would then require **another 2,630.103 s**, equivalent to accelerating the whole launch-to-detector prefix **2.727×**. That requirement charges input and output as well as detection. Current same-input evidence gives no basis for that rate. The next qualifying component would have to show a large paid CPU change inside the actual installed prefix before repeating a raw-to-publication composition. [Disjoint donor model and individual thresholds](measurements/installed-science-first64.json.gz)

The reducer used only the independently signed export for the frozen first 64, original attempt telemetry, verified publication-file metadata, pinned code and existing physical donor receipts. It opened no native packet contents, original waveforms, orbit bodies, PNGs or post-64 scores. It ran on CPU3 at nice 15 and idle I/O and made zero receiver or solver calls. [Reducer](installed_science_first64.py) · [Component tests](../../../tests/pipeline_eval/test_installed_science_first64.py)

```sh
sudo -n -u leo env PYTHONPATH="$PWD" taskset -c 3 nice -n 15 ionice -c 3 python3 -B \
  -m reports.ALGO08.v3.installed_science_first64 \
  /tmp/leo-routing64-139b02f8 /srv/postgres-nvme/leo-ds30-evaluation-20261124 \
  /tmp/new-installed-science-first64.json.gz
```

# Capture-era GLRT provenance and saved-IQ replay

The installed capture-era detectors reproduced **all 38 sampled receiver probe records**, including all 181 complete fractional candidate records. The ordinary wave8 build independently reproduced all 38 probes and 177 candidate records in its own archive. The two detectors gave different complete probe records on all 38 same-input comparisons. Both preserved the five sampled capture exclusions. These are detector-stage measurements across four recordings. [Protocol](PROTOCOL.md) · [Complete comparison](comparison.json)

## Recovered numerical entry points

The archived input manifest, release digest and analysis run ID identify the installed Python worker. The worker's `implementation_identity` hashes its scientific source and loaded native acquisition extension with its environment. We reproduced all four run identities under the original CPython 3.12.14 and NumPy 2.5.2. The outer worker invokes `fast_scan_analysis.analyze_window` with the archived `FastScanPolicyV2` and its default `production_glrt`. It converts the recorded 20 ms, 10 MS/s dual-receiver CI16 visit, uses actual retune metadata for the RF center, and runs `acquire_symbolwise`, `conditioned_glrt64_scores` and `refine_glrt64_epochs`. The native acquisition path reports AVX2/FMA on this host. [Release hashes, absolute runtime paths and policy](comparison.json)

| Recording | Verified capture release | Numerical source |
| --- | --- | --- |
| DS26-0036 and DS26-0237 | `fast-1f3a91c6a882b6e7eac8827fbb95f215` | Shared `native-scope64-v2-3460060352b364a9` deployment |
| DS29-0082 | `fast-33b3892e0162eac7fd2232898aa9d1ce` | Standard fast release `17bf8ccfa3dd495f040fcb05fbcffcb1e11c42e3` |
| DS29-0174 | `fast-a9ce664313cc56759cdffefe4750f833` | Qualified runtime `a1b999aad5bdc924fd90d35e055878bc23bd4c06` |

DS29-0082 shares byte-identical acquisition, scanner, scoring and native-extension bytes with the DS26 worker. The DS29-0174 manifest identifies integer coarse screening and batched exact columns in acquisition. Its acquisition source and extension binary changed. Its scanner entry and fractional scoring source remained identical. The ordinary control instead uses `NativeShortWindow` from the separate `wave8-gate314-source-v1` C build. Its library SHA-256 begins `110c3e8f74952ef6`. [Bound build and reference inputs](comparison.json)

## Earliest measured divergence

The first divergence is the acquisition search. On DS26-0036 visit 1 the actual native capture call evaluated **21 CFO rows × 13,333 epoch cells** with 12 anchor symbols. Its capture coarse results included +560 and −720 kHz on the two receivers. It reran the receiver without a passing fractional candidate with 22 anchor symbols after its peer passed. Ordinary starts with four proposal centers, tests their neighboring epochs on a fixed 11-row ±400 kHz bank, and applies a 0.152 coarse threshold at 10 MS/s before retaining its fine candidates. [Native call argument fixture](folded-fixture.json) · [Complete raw stage traces](DS26-0036.json.gz)

Intersecting only the capture-era absolute CFO domain with ±400 kHz changed **seven of eight** probe outputs across the four first valid visits. The altered capture detector reproduced zero of the eight ordinary outputs. On DS26-0036 alone it changed the two-receiver complete candidate count from 13 to 11. Ordinary returned nine on the same visit. This establishes an early causal contribution from search support. Proposal-centered epoch selection, the coarse gate, candidate retention and later refinement still differ. [Intervention receipts](comparison.json)

## Timing and architecture

The table includes validated candidate projection for both arms. Each admitted visit ran three alternating warm pairs on one x86 core. Archive decoding happened before these timers. The timings are medians over the measured calls and include no position work.

| Recording | Valid / sampled visits | Capture CPU / wall | Ordinary CPU / wall |
| --- | ---: | ---: | ---: |
| DS26-0036 | 6 / 6 | 2,054.51 / 2,623.00 ms | 16.79 / 16.79 ms |
| DS26-0237 | 6 / 6 | 1,429.77 / 1,444.74 ms | 14.73 / 14.73 ms |
| DS29-0082 | 1 / 6 | 1,488.10 / 1,505.62 ms | 15.91 / 15.91 ms |
| DS29-0174 | 6 / 6 | 594.23 / 602.69 ms | 16.25 / 16.25 ms |

The fixed DS29-0082 roster reached one valid later visit and five original capture exclusions. All four complete recordings have broader archived evidence. Applying the DS26-0036 sample CPU median to its 6,765 admitted visits gives about 3.86 CPU-hours for a naive full detector replay. Only the bounded replay was timed here. [DS26-0237 raw receipts](DS26-0237.json.gz) · [DS29-0082 raw receipts](DS29-0082.json.gz) · [DS29-0174 raw receipts](DS29-0174.json.gz)

On the exact deployed one-receiver coarse fixture, x86 processor CPU was 512.39 ms with AVX2/FMA and 747.45 ms with the installed portable entry. The two coarse grids differed by at most `1.11e-16`, with the same strongest cell. The separate standalone portable C body used 0.680 s native x86 CPU and 27.886 s under Cortex-A9 QEMU for that same input. It preserved the eight selected basins, with a maximum `5.56e-17` score difference relative to native x86 portable. The complete capture-era ARM detector and physical board throughput were unmeasured. [Installed x86 primitive clocks](coarse-x86.json) · [Cortex-A9 primitive and runnable capsule](../embedded/README.md)

## Reuse

Use the exact release source as the first `PYTHONPATH` entry, the repository second, and `/opt/leo-fast-auto/20261010-r1/venv/bin/python`. Run `-B -m tools.pipeline_eval.qualification.capture_detector_lineage <recording>` once for each recording. Then run the same module with `compare` to authenticate field parity against both archives. For a larger replay, bind the release with `capture_release.producer` and `_bind_producer`, read windows using the verified archive provider, and pass the original window and receiver order to `capture_detector_replay.scan_capture_window`. It returns the validity decision and native science probe rows without a database, an orbit fit or any position reference. [Evidence seal](source-lock.json)

# Cost of retaining every sixteenth full receiver visit

Changing the full-anchor schedule from every eighth to every sixteenth admitted visit per RF stream projects **1.452 CPU s** in detector savings on dense DS30-0008, **0.113 s** on the warm weak physical DS30-0016 recording, and **0.124 s** on the signed northern simulation. This estimate uses measured mean costs for the full and 12 ms calls. The measured budgets for **all** full calls were 4.716, 0.430 and 0.588 CPU s respectively. Even erasing that entire work leaves each historical elapsed comparison above its half-time target when other stages keep their original costs. [Dense recording](dense-full-short-raw.md) · [Warm weak record](weak-combined-raw.md) · [Northern containing simulation](north-causal-transfer.md)

| Existing one-in-eight receiver | Stereo visits | Full antenna calls, 8 → 16 | Full work at converted slots if evenly priced, CPU s | Mean net saving, CPU / elapsed s | Ceiling from all measured full work, CPU / elapsed s | Original complete CPU / elapsed s |
|---|---:|---:|---:|---:|---:|---:|
| Dense DS30-0008 | 6,765 | 1,696 → 848 | 2.358 | 1.452 / 1.484 | 4.716 / 4.801 | 67.352 / 95.429 |
| Warm weak DS30-0016 | 713 | 186 → 100 | 0.199 | 0.113 / 0.113 | 0.430 / 0.430 | 8.878 / 8.901 |
| North containing simulation, unfiltered | 1,200 | 304 → 160 | 0.279 | 0.124 / 0.124 | 0.588 / 0.588 | 12.818 / 12.872 |

Each stream is keyed by pilot edge, channel and actual RF. With the first admitted visit anchored, a stream of length `n` contributes `ceil(n / k)` stereo anchors at interval `k`. Streams restart independently. Both radios still make exactly one native call per admitted visit. Each converted full call is replaced by a genuine 12 ms primary. The calculation reproduces the recorded one-in-eight call census in all three cases. The proposed native call totals remain 13,530, 1,426 and 2,400. [Existing frozen schedule and clock scope](mixed_aperture_receiver.py)

The archived instrumentation totals clocks by detector mode. For each CPU or elapsed clock, multiply the exact number of converted antenna calls by `full_total / full_calls − short_total / short_calls`. The converted-slot gross column charges all replacements zero at the mode's mean recorded full cost. The slower or faster full calls at precisely those slots cannot be identified from the aggregate clocks. The ceiling column grants the entire observed full-call clock, including retained anchors, at zero cost. It bounds savings from that measured detector work with unchanged other work. Acquisition still decodes and authenticates the signed stereo windows, and the solver can do different work when the input factors change.

## Inputs for the arithmetic

| Receipt | Admitted visits by RF stream | Original 12 ms calls | Measured full / short CPU ns | Measured full / short elapsed ns |
|---|---|---:|---:|---:|
| Dense | 846, 847, 847, 847, 845, 846, 841, 846 | 11,834 | 4,715,500,143 / 12,635,274,396 | 4,800,924,621 / 12,791,498,651 |
| Warm weak | 87, 100, 99, 101, 100, 75, 50, 101 | 1,240 | 429,733,897 / 1,233,808,062 | 429,846,548 / 1,234,024,021 |
| North containing | 150 on each of eight streams | 2,096 | 588,160,363 / 2,247,971,740 | 588,308,842 / 2,248,990,262 |

- Dense receiver receipt `/var/tmp/leo-full-short-dense-DS30-0008/publication/full-short-recipe.json`, SHA-256 `a86307c85d8405fd9c4a14b4bd09066f924016c82922b02b65d05557a6dc89bb`.
- Warm weak receiver receipt `/var/tmp/leo-v3-weak-combined-warm-Nov23/candidate/full-short-recipe.json`, SHA-256 `d708b22baa7c48acc8db5dec7925fb5528b61000a601638c53b6340ea0891f5b`.
- North receiver receipt `/var/tmp/leo-north-short-regional-nov23/containing/full-short-recipe.json`, SHA-256 `1527e0760265da4888ae5037c3f9edbf49884bb61ad19e40e5e95017d2528912`.

The saved profiles establish the small detector-work opportunity. No one-in-sixteen receiver, raw run, or position replay was executed. Changes to the signed winner, position and RF residual in either `c` arm remain unmeasured. The one-in-eight implementation and its pinned digests retain their existing values.

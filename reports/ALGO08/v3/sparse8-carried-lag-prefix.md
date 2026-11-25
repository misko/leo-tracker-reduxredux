# Register-carried lag energy in the active sparse8 scout

The actual sparse8 AVX2 lag kernel reloads each previous four-sample block's stored Float64 energy prefix. The pinned `c5b57b` PGO loop uses both a `vmovsd` and a memory-operand `vaddsd` on that entry. Its next block therefore depends on forwarding the previous store. The candidate carries the last Float64 sum in a register while writing the same full prefix table. The matched candidate PGO loop uses register operands at both sites. At the active stride of four, the two modes have width 4,740 and actual lag offsets are 2, 4, 6, 11, 18, 28, 44 and 74. The eight surfaces include 37,733 energies, or 9,431 four-sample blocks and nine scalar tail samples. The disassembly removes 18,862 hot-loop memory operands per lane at these two positions. They are repeated loads of recently written values, and may be satisfied by forwarding. The count does not measure CPU savings. [Active receiver profile](sparse8-native-profile.md) · [Source overlay](sparse8_lag_prefix.py)

For each lag, `prefix[0]` is positive zero. Each existing Float32 power is converted to Float64 and added to the preceding Float64 sum in the same sample order. By induction, on the x86-64 arithmetic path the carried sum has the same binary64 value as the stored prefix endpoint. There is no fused arithmetic, reassociation or extended-precision accumulator. Scratch, mode arrays and the prefix arrays are independently allocated by the pinned constructor. This overlay changes only the AVX2 helper. Eight forward and eight inverse FFTs still execute over all 4,800 points. The original 3,333 normalized score additions per lag and the twelve strict, circularly separated timing ranks remain. [Ordered spectral arithmetic](../../../tools/pipeline_eval/variants/experimental/receiver_spectral_vectors.inc)

Nine component tests cover the installed width and all active lags, scalar tail lengths, 19,200-point geometry, signed zeros, nonfinite classifications, and a constructed Float64 counterexample to regrouping small powers. Two-mode synthetic tests compare products and prefix bytes, then compare every score and all twelve selected indices after the unchanged FFTW sequence. The all-zero tie test checks lower-index preference and exclusion across the circular boundary. The preceding spectral vector study already vectorized lag products and normalization. The blocked maxima study preserved bytes but its complete native time was flat. Full-grid polyphase FFT folding cost 2–3% more, and the frozen 8 ms cross-lag route lost three factors. This change removes a dependency within each of the eight required lag surfaces. [Prior vector kernels](../single-core-2x/receiver-spectral-vectors.md) · [Blocked maxima](../single-core-2x/receiver-epoch-blocks.md) · [Polyphase folding](receiver-polyphase-timing.md) · [Cross-lag transfer](cross-lag-eight-ms.md)

Archival feedback failed a strict relocation trial. Even the ordinary source compiled under a new object path reported missing function identities. The changed source also reported location mismatches. Fresh matched training on CPU6 at nice 15 used the pinned 32 generated calls with two edges, zero and nonzero mixer centers, and both radios. Both independently trained arms reproduced the archived count digest and compiled with `-Werror=coverage-mismatch` and `-Werror=missing-profile`. The control DSO and timing object reproduced the installed bytes. [Build reproducer](sparse8_lag_prefix_build.py)

| Build evidence | SHA-256 |
|---|---|
| Archived timing C | `10d8ec75ac2d6e820dd9cee184b2825b8d6510a465bbb8bfa38fc782126daea5` |
| Archived spectral include | `779d863a56ce9cfd1fa0fed80ef31115a9040307ca06df68839c0db7be27eee8` |
| Candidate timing C / include | `d300296c7771acd9ebbb0903db2bbca7ef9884b9cf87ca71b092341dc0d86d4f` / `0eb6b584852324fa651a4d17eb87dcb97ac34de791a00f7413079ccfb5132eda` |
| Exact control DSO / timing object | `c5b57b0602e81a6a85c14caf648eb12341f098d09915b4d3f705094ed309574c` / `b56bf27134e8f55be937ed1120db404e73b0ea944309a9cb468f7d39806223c4` |
| Candidate DSO / timing object | `6a15c9f451d5102454eebb5fcc77c06a065b42f76a0adbbe5943607881c0471d` / `557b90e6026a05f712fd6a625ef3240f1db3066f36dc7de294791801c308f1ba` |
| Site-free trainer / output | `c63b849fb630d33fee53d8011b1766891b7e3c9038295334275135055dc443ac` / `a43fe596d806cf29079a1b909a993e6128d4ff0e96862ed6ccfdce01b60a14ec` |
| Exact local build manifest | `7ea974a67dc60e66de03635d6b774e1c34583b10be2879d6dda5fb2000bda268` |

The earlier disjoint profile assigns 160.37 µs per short lane to this entire timing stage. Changing the prefix dependency keeps all its FFT and scoring costs. As a scale check only, at an assumed 4.5 GHz an average saving of one cycle per four-sample block would be about 2.1 µs per short lane. A measured 5 µs callback improvement would require about 2.4 cycles per block at that clock if it came entirely from this loop. PGO code layout and other stages can affect the measured callback difference. The small matched trial checks the full native callback through signed factor return, which is the decision boundary for advancing the change. [Frozen protocol](sparse8-carried-lag-prefix-protocol.md)

The one authorized readiness watch expired without a timing child. It observed 180 polls. There were 164 without a fresh deferral, 13 with excessive rolling queue, two before a two-second window was available, and one that failed the instantaneous storage check. At the last fresh rolling refusal, the field had deferred DS30-0445 for 3.171 seconds. The Gauss lease was free and both instantaneous device queues were zero. The bulk rolling queue still averaged 4.835 over 2.018 seconds against a limit of two. With no admitted child, no I/Q payloads were read and there are no paired callback clocks. [Readiness and build receipt](measurements/sparse8-carried-lag-prefix.json)

The separately authorized RAM-only comparison completed during an actual DS30-0445 field deferral. The capsule mounted only the two signed detached waveform files and manifests, two matched libraries, pilot files, and read-only runtime and source dependencies. Preflight and the child both showed six denied backing or alias paths and kernel denial of all three socket families. All 11,329 DS30-0163 and 5,860 DS30-0419 waveform pages were resident before and after. The exclusive lease was taken with 29.725 seconds until the field retry. The controller reserved a 12-second maximum child, leaving 17.725 seconds of margin. The visible research NVMe queue averaged 0.029. [RAM capsule](sparse8_lag_prefix_ram.py) · [Signed admission and timing receipt](measurements/sparse8-carried-lag-prefix.json)

All **252 paired outputs** matched byte for byte, including 84 positive and 168 empty pairs. An independent join reproduced the ordered output and original window digest for every pair against the archived original profile. Across both recordings the balanced median paired saving was **10.160 µs per complete callback (1.29%)**. Each DS30-0163 round averaged the per-lane savings across 18 control-first and 18 candidate-first pairs. These six balanced round means were +15.679, +9.613, +9.689, +9.684, +15.025 and +9.496 µs per lane. The six-lane DS30-0419 sample had four faster rounds and two slower. Each table entry takes the median of the six round means for its specified lane and order group. The candidate-first column considers that half of each round separately, so it can have the opposite sign from the complete balanced round. [Archived exact control](sparse8-native-profile.md) · [Signed timing receipt](measurements/sparse8-carried-lag-prefix.json)

| Scope | Pairs | Balanced saving, µs/lane | Control first | Candidate first |
|---|---:|---:|---:|---:|
| Both prefixes | 252 | 10.160 | 36.500 | −15.882 |
| Both, positive | 84 | 12.319 | 83.268 | −55.572 |
| Both, empty | 168 | 10.422 | 16.390 | 3.880 |
| DS30-0163 | 216 | 9.687 | 35.466 | −13.307 |
| DS30-0163, positive | 60 | 14.182 | 84.594 | −57.675 |
| DS30-0163, empty | 156 | 9.907 | 16.798 | 3.219 |
| DS30-0419 | 36 | 12.462 | 48.975 | −28.404 |
| DS30-0419, positive | 24 | 11.264 | 68.813 | −54.911 |
| DS30-0419, empty | 12 | 15.951 | 9.920 | 23.973 |

| Scope | Control callback CPU summed over six repeats, ms | Candidate callback CPU summed, ms | Control / candidate |
|---|---:|---:|---:|
| DS30-0163 | 168.859621 | 166.368912 | 1.014971× |
| DS30-0419 | 30.609161 | 30.160372 | 1.014880× |
| Both prefixes | 199.468782 | 196.529284 | 1.014957× |

The positive callback strongly favored the arm that ran second. Empty callbacks were faster in both orders. The order effect and small sample limit transfer of the balanced gain beyond these fixtures. Complete capsule wall time was **1.59 s**. The worker measured **1.231 CPU s** across authenticated input, native setup, callbacks, and its own accounting. The outer process timer measured elapsed through exit but missed the nested child's CPU. The timed worker saw 30,488 input blocks and one major fault. The kernel mount proof excludes backing data from this process, and the available counters have no per-file attribution. Ten component tests passed in total. [Comparison driver](sparse8_lag_prefix_measure.py) · [Signed timing receipt](measurements/sparse8-carried-lag-prefix.json)

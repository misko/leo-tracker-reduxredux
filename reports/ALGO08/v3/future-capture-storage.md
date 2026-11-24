# First-use cost of aperture-aligned capture

On one complete, previously staged DS30-0016 member, level-1 aperture-split storage saved a median **2.72 ms elapsed** across three paired capture-to-first-analysis comparisons. Its paired changes ranged from **8.31 ms slower to 17.36 ms faster**. The fast level −1 split saved a median **51.77 ms**, with **30.32% more stored bytes** than the ordinary writer. The comparable-size split did not establish a repeatable first-use benefit. [Measurements and exploratory controls](measurements/future-capture-storage-0016.json.gz)

| Capture layout | Capture write, wall / CPU | First mixed analysis, wall / CPU | Joint clock, wall / CPU | Stored bytes | Decoded on first use |
|---|---:|---:|---:|---:|---:|
| Ordinary level 1 | 157.56 / 157.56 ms | 296.02 / 296.01 ms | 456.04 / 456.03 ms | 78,731,276 | 102,400,000 B |
| Split level 1 | 185.91 / 185.85 ms | 255.82 / 255.81 ms | 442.57 / 442.49 ms | 78,753,870 | 60,800,000 B |
| Split fast level −1 | 155.47 / 155.28 ms | 244.99 / 244.98 ms | 401.34 / 401.14 ms | 102,603,737 | 60,800,000 B |

The table uses medians by scope. Savings above use within-order differences on the continuous clock. Level-1 splitting added 22,594 bytes and spent a median 110.24 CPU ms inside split encoding and block hashes. Fast splitting spent 66.08 CPU ms there and added 23,872,461 bytes to each write and first read. At equal serial read and write rates, moving that extra 47.74 MB would take the measured 51.77 ms at about 922 MB/s. This is an arithmetic crossover. The experiment used resident tmpfs.

The ordinary writer reproduced the original compressed payload SHA-256. The split writer reused the same capture metadata, original per-window and whole CI16 checks, and durable file writes. Its trusted root sealed the exact order, extent, compressed digest and decoded digest of each 12 ms prefix and 8 ms tail. The first split analysis read and verified all 128 compressed blocks including unused tails. It decoded 66 blocks and skipped 41.6 MB of decoded material. An independent complete recovery of each layout reproduced the 102,400,000 original sample bytes and the signed metadata index remained identical. [Capture emulator](future_capture_storage.py) · [Seekable format and corruption checks](seekable_member.py)

All nine first analyses reproduced the complete ordered timeline and signed probe digests. The original member issued 64 visits and admitted 58. Each arm made eight full and 50 short-primary stereo visits and selected 45 factors. The one-core run used CPU 2, nice 15, and best-effort I/O priority 7 under the Gauss lock. Every timed scope recorded zero input blocks. No new RF or backing-storage read occurred.

Fixture authentication and decoding cost 174.70 ms elapsed before the emulator owned the raw windows. Shared dependency and native setup cost another 453.45 ms and sat outside all three arms. An exploratory order paid that first-use setup in its first ordinary analysis, and its results are retained separately. The independently timed legacy conversion cost 253.48 ms wall and 253.42 ms CPU. Complete recovery of that conversion cost 157.76 ms wall and 157.75 ms CPU. Neither stage receives new-capture performance credit. Thirteen component and adjacent tests passed. [Frozen protocol](future-capture-storage-protocol.md)

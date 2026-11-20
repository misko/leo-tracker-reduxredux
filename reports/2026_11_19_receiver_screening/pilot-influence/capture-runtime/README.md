# Installed capture acquisition versus current native GLRT

The original installed detector took a median **2,618 ms wall** on eight saved windows from four recordings. Current stock four-region GLRT took **16.57 ms** with both receivers and **8.88 ms** with one physical receiver. Those are fresh detector-only timings on the same core and IQ bytes from the enriched known-time study. The old detector recovered all eight registered targets. Both current modes recovered the four previously matched targets and missed the four previous misses. [Timing chart](stage.png) · [Per-call data](stage.csv) · [Numerical comparisons](parity.json)

## Matched timing

Each original decoder ran on native x86 CPU 7 through its installed Python and exact case-bound producer. The four cases used three producer roots. Each worker preloaded the same dual 20 ms, 10 MS/s CI16 arrays before all calls. Current dual and one-RX used the same sealed wide native binary, templates, registration and Python output projection. Current one-RX includes the contiguous IQ copy and lead-row remap, plus an empty companion on the original physical receiver and probe clock. Capture includes its installed primary/fallback policy and probe projection. Each method warmed on the first window for its case before two rotated timed passes. CPU and wall exclude input reads, context initialization, and file writing. [Predeclared roster, producer fingerprints, IQ and template hashes](input-lock.json)

| Detector | CPU median (ms) | Wall median (ms) | Calls ≤20 ms wall |
|---|---:|---:|---:|
| Capture-era dual | 2,610.72 | 2,617.67 | 0/16 |
| Current wide dual | 16.37 | 16.57 | 16/16 |
| Current wide one physical RX | 8.88 | 8.88 | 16/16 |

| Recording | Edge | Visit | Capture CPU / wall (ms) | Current dual CPU / wall (ms) | Current one RX CPU / wall (ms) |
|---|---|---:|---:|---:|---:|
| DS26-0162 | Upper | 0 | 1,511.57 / 1,540.05 | 17.67 / 17.71 | 8.58 / 8.58 |
| DS26-0162 | Upper | 1 | 2,618.37 / 2,669.88 | 16.03 / 16.09 | 9.06 / 9.06 |
| DS26-0237 | Lower | 4 | 3,070.81 / 3,103.58 | 14.29 / 14.65 | 7.85 / 7.96 |
| DS26-0237 | Lower | 64 | 2,642.77 / 2,648.34 | 17.73 / 17.73 | 9.75 / 9.75 |
| DS29-0082 | Upper | 0 | 2,635.28 / 2,640.16 | 16.81 / 16.84 | 8.92 / 8.92 |
| DS29-0082 | Upper | 2 | 2,670.86 / 2,835.26 | 17.25 / 17.29 | 9.79 / 9.81 |
| DS29-0519 | Lower | 4 | 978.42 / 982.39 | 16.31 / 16.45 | 9.46 / 9.46 |
| DS29-0519 | Lower | 155 | 964.72 / 965.70 | 15.11 / 15.65 | 7.35 / 7.64 |

The median paired per-window capture-to-current CPU ratio was **151.9×** for dual and **272.0×** for one RX. The selected one-lane schedule ran receiver 0 on seven windows and receiver 1 on one, based on the prior valid visits on each RF independently. The roster comprises the first prior matched and missed target per case. These eight selected windows do not establish recording-wide throughput, live cadence or positioning time. [Protocol](PROTOCOL.md) · [Structured summary](summary.json)

## Scientific differences on the same windows

Original capture reproduced all archived probe rows across both measured repeats. The active current one-RX row matched current dual exactly, including the raw probe clock and output factors. Across the eight unique windows, the capture-era dual detector emitted 25 gated candidates, current dual 48 and current one-RX 34. Matching once per receiver within two samples and 1 kHz after CFO alias folding yielded 21 capture-to-current-dual matches and 16 capture-to-current-one-RX matches. Twenty and 16, respectively, also matched the unwrapped CFO within 1 kHz. The extra candidates have no independent physical labels.

Both current branches retained the four previously matched targets. Three of the four prior misses lay on the unselected peer, and the one remaining prior miss also failed under current dual. The archived detector found all four. This panel directly demonstrates one accuracy cost of changing the acquisition hypothesis budget even where the current detector satisfies the host visit deadline. [Per-probe matches, target identities and physical selection](parity.json)

The first startup was rejected because the installed Python lacked SciPy through an unrelated qualification-only import. Moving that import to the prospective input preparation path allowed all three original producer environments to run, without changing their installed software. That preflight produced no timed rows. [Seal](qualification-lock.json)

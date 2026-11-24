# Exact ordinary Agg reuse on DS30-0359

The two existing exact Agg shortcuts together saved **0.156 s** on
the four DS30-0359 orbit sheets. The ordinary and candidate replays
both reproduced the four published PNGs byte for byte. The saving
fell below the earlier **0.20 CPU s** screen and is much smaller
than the **1.197 wall s** gap to the saved worker's twofold target.
This is one renderer-only comparison on the same saved scene.
[Frozen protocol](ds30-0359-agg-reuse-protocol.md) ·
[Complete saved comparison](ds30-0359-combined.md)

| Paid four-sheet scope | Ordinary, CPU s | Exact reuse, CPU s |
| --- | ---: | ---: |
| Full renderer including setup | **1.135** | **0.979** |
| Figure construction, including both layouts | 0.427 | 0.309 |
| Two Agg base draws | 0.286 | 0.293 |
| Copies and restores | 0.039 | 0.022 |
| Four PNG encodes | 0.244 | 0.240 |

The paired wall clocks were **1.135 and 0.979 s**. The comparison
ran ordinary first, so the difference includes order and timing
variation. Signed scene admission and the renderer setup before both
arms took **0.522 s**. Independent output verification took **0.386 s**.
Neither is part of the four-sheet interval. The earlier complete
saved worker measured **1.232 CPU s** for the ordinary orbit views.
Its other stages remain outside this measurement.

The ordinary renderer already constructs one figure and paints
one base raster per band. The paired sheets share it and repaint
only titles, footer and the associated observations that change.
The prototype reuses the previous fixed-limit `PathCollection` and
`Line2D` construction and elides the first restore right after the
background copy. The two first restores cost **6.63 ms CPU** in the
ordinary arm. The original four encodes still execute. All four
encoded hashes, decoded RGBA hashes, dimensions, mode and PNG
metadata match the earlier official publication. The axes, labels,
titles and legend matched between replays. The fixed-limit path
handled 16 axes, 432 curves and 134 scatter collections. Earlier
tests studied these two shortcuts separately on other saved scenes.
[Existing shared Agg reuse](ordinary-orbit-reuse.md) ·
[Fixed-limit artists](agg-orbit-artists.md)

On this scene, removing every copy and restore and granting free
second-band layout and axis construction yields only **117.2 ms**
of gross CPU opportunity. Granting both bands' layout and axis
construction for free raises that ceiling to **205.4 ms**. Some
background preservation and axis construction are required. The
bands had **zero exact matches** among 216 folded orbit paths each,
even before comparing transforms and clips. There was no discarded
second base draw for either pair to recover.

The four ordinary encodes spent **209.3 ms CPU** on libdeflate,
**24.7 ms** on the native row filter, **2.9 ms** on header templates
and **6.1 ms** on stream assembly. Keeping the exact deflate work,
eliminating all other encoder costs would release at most **34.3
ms** here. The views have distinct encoded bytes. No exact reuse
of their compressed streams was established. These bounds concern
the existing operation scopes. Whole-worker savings and a different
encoder were outside this trial.

One low-priority CPU 2 lease covered the pair. The worker used the
stored signed scene and four ordinary PNGs with no solver, waveform
or backing-archive read. The first controller invocation stopped
before rendering because its scene-digest spelling was wrong. Both
timed arms ran once after correcting that check. The offline reducer
kept the raw clocks and distinguishes the candidate's two second
restores from the elided first restores. Six component and adjacent
tests passed. Timed commit `5cf28ec57`.
[Runner](ds30_0359_agg_reuse.py) ·
[Machine receipt](measurements/ds30-0359-agg-reuse.json), SHA-256
`3ada76ba9bce3c283a62a2c5ba8707756aef6a72291466e7cf843b07e9d29040`.

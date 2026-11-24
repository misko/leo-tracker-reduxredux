# Continued-CFO raw transfer on DS30-0107

On the complete signed DS30-0107 recording, installed ALGO08v3 and the continued-CFO candidate both exited zero and published `no_active_curvature`. The candidate reached exit in **0.533 s wall and 0.531 s CPU**, versus **1.466 s wall and 1.453 s CPU** for installed v3. The staged-input pair was 2.75× faster on elapsed time and 2.73× on CPU. Both arms used the same 29 issued visits, 27 valid visits, 54 per-radio opportunities, original 25 km offer, and 51 signed causal catalogue names. [Machine receipt](measurements/continued-cfo-small-raw-0107.json.gz)

| Arm | Detection file, wall | Terminal, wall | Process exit, wall | CPU | Signed factors |
|---|---:|---:|---:|---:|---:|
| Installed v3 | 1.214 s | 1.251 s | 1.466 s | 1.453 s | 0 |
| Continued-CFO candidate | 0.470 s | 0.471 s | 0.533 s | 0.531 s | 20 |

The candidate ran the exact tested `continued_cfo.raw_entry` with its held-cycle selector. Its publication configuration enabled the named survivor finish and the current Graph guards. It visited eight full and 19 short-primary windows. The selector kept its unfiltered 20 measured factors. Causal continuation admitted zero CFO refinement calls. The signed guard found the longest lane spanned 0.708 s against the required 20 s and ended the candidate run before final fitting. Both the c = 0 and fitted-c arms had no RF RMS or geographic estimate. Both withheld publications had zero PNGs and no position sidecars.

The prospective 455-binding census had no recordings between 32 and 64 issued visits. The closest higher counts were 92 and 124, both previously tested. The approved nearest-lower exception selected the 29-visit DS30-0107 by length alone, excluding the previously measured 18-visit DS30-0227. The enrolled original consists of one complete signed member. Neither inference process used a prefix.

The original payload and index were fully cold before staging at 50.30% full I/O pressure. One separately charged pass copied 33,519,983 compressed bytes, 78,609 index bytes, and the 3,542-byte signed manifest in 1 MiB blocks paced at 4 MiB/s. It cost 8.012 s wall and 0.032 s CPU, with 65,632 input blocks of 512 bytes. The pair bound that staged original read-only at its canonical path in a private mount namespace. All 8,184 payload pages and 20 index pages were resident before and after both children. The catalogue used 51,836,455 unique bytes from existing tmpfs copies, with zero original catalogue body reads. Installed v3 incurred 1,256 process input blocks and one major fault. The candidate had zero for both. The two child clocks exclude staging and reflect one named-first warm pair.

The pair verified the installed release, the exact source and library pins on `250c07d0c`, the signed terminal and archive identities, and both published calibration arms. The outputs were sealed before geographic scoring. Nine harness and continuation component tests passed. [Protocol](continued-cfo-small-raw-protocol.md) · [Runner](continued_cfo_small_raw.py)

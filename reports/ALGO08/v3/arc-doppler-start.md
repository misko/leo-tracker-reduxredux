# A Doppler-change proposal for full-observation starts

The six-sample Doppler-change scout abstained on all three saved cases. It cost 0.065 CPU s on dense DS30-0008 before full-observation scoring. Even forcing the exact rebuild from its best sampled position recovered only **100 of 112** original satellite and signed-alias assignments. The northern simulation recovered **12 of 13**. Neither rebuilt assignment matched any branch in its original shortlist. Keep the original cold search. [Frozen experiment](arc-doppler-start-protocol.md) · [Complete receipts](measurements/arc-doppler-start.json.gz)

## What the scout kept

The scout selected up to 12 native curved arcs across receiver, RF bank and observed time thirds. Each contributed six observed points and three disjoint differences. This cancels any constant per-arc offset, including a fixed alias roll or constant fitted RF calibration term. Fitting a causal phase tangent still leaves noise and receiver drift in the differences. The scout scored the entire original prepared sky at the centre and four face centres. It used the supplied box and retained the same signed cutoff and causal archive. No stock identity or position entered the proposal. [Implementation](arc_doppler_start.py)

The dense scout used 12 representative arcs and 72 distinct times. Its strongest sampled point was the eastern face. The interpolated east coordinate was 12.44 km against the 10 km interior limit. Its interpolated north coordinate was 0.96 km north, while the original exact cold race selected a point 7.85 km south. The north scout used ten arcs and 42 distinct times, but the east–west stencil had negative curvature. Weak DS30-0016 had only two representatives after grouping its three active arcs. It stopped before projection. [Full diagnostic fields](measurements/arc-doppler-start.json.gz)

| Saved case | Shared causal orbits | Arc representatives / active arcs | Stock cold branches | Original orbit in sampled slate | Exact rebuild owner and alias matches | Whole branch matches |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DS30-0016 | 1,449 | 2 / 3 | 2 | — | — | — |
| Northern simulation, containing | 1,569 | 10 / 13 | 4 | 10 / 10 | 12 / 13 | 0 / 4 |
| DS30-0008 | 1,476 | 12 / 112 | 7 | 11 / 12 | 100 / 112 | 0 / 7 |

The sampled slate was the union of up to four approximate candidates per arc per probe. This is a post-run membership oracle. The diagnostic rebuild instead used every original curved observation, all causal orbits, the original phase-proposal logic and anchored integer alias selection. Approximate labels did not restrict that path. The dense rebuild chose 43 distinct orbit owners and the north rebuild chose nine. Stock fell back to its own ranked branches and reproduced the archived cold winner, position and score fields on all three cases. [Archived input and race verification](arc_doppler_start_trial.py)

## Charged fallback and dual-calibration evidence

| Saved case | Scout CPU s | Scan plus scout CPU s | Exact diagnostic rebuild and both scores CPU s | Original cold CPU s | Scout plus original fallback CPU s |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS30-0016 | 0.000057 | 0.026883 | — | 0.207477 | 0.234360 |
| Northern simulation | 0.046705 | 0.070710 | 0.040785 | 0.386316 | 0.457026 |
| DS30-0008 | 0.064570 | 0.114223 | 0.827757 | 5.679934 | 5.794156 |

The diagnostic costs are separate because the frozen route abstained before them. The measured fallback builds a fresh original scan. Even if that scan preparation could be reused, the scout adds CPU on every observed fallback. The cold boundary excludes shared Graph and sky preparation, the already-published regional proof, later recovery and both-arm evidence, and rendering. No complete pipeline timing is inferred. Giving away the entire previous 5.724 s cold stage would still leave 20.381 CPU s of the 26.105 s dense unfiltered solver. [Dense stage accounting](regional-dense-pair.md)

The forced diagnostics use exactly the same reconstructed arcs, signed aliases, causal priors and position in both arms. They test conditional RF scoring at a fixed probe. No geographic optimizer ran on those branches. The ordinary archived terminal results below come from the identical signed receiver documents, with their own accepted observations and both original calibration arms. The geographic scorer reads the site references only after the cold receipts are sealed. [Physical reference](../../2026_11_21_ds30_full/reference-audit.json) · [Simulation reference](../regional-release/scoring-key.json)

| Saved case | Forced fixed-point RF RMS Hz, zero / fitted | Archived final RF RMS Hz, zero / fitted | Archived final horizontal error km, zero / fitted |
| --- | ---: | ---: | ---: |
| DS30-0016 | — | 121.526 / 120.291 | 1.311 / 1.694 |
| Northern simulation | 58.341 / 57.987 | 69.401 / 70.860 | 0.390 / 0.121 |
| DS30-0008 | 6,626.983 / 6,608.685 | 140.961 / 140.950 | 0.919 / 0.857 |

Commit `644532708` froze the design. One shared low-priority Gauss lease covered all three saved inputs, in weak, north, dense order. Use the released Gauss interpreter and installed payload, with the report folder on `PYTHONPATH`, and run `arc_doppler_start_trial.py CASE OUTPUT` for `weak`, `north` and `dense`. The runner verifies the archive, detector, original offer, stock terminal, installed graph and selected cold winner before writing the receipt. Use tmpfs scratch, CPU 2, nice 15, I/O priority 7 and one numerical thread. Twenty component and adjacent tests passed. [Runner](arc_doppler_start_trial.py) · [Focused tests](../../../tests/pipeline_eval/test_arc_doppler_start.py)

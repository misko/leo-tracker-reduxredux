# Rotating whole RF dwells on the original hardware clock

The two-lane policy keeps one physical RF lane per bank for at least 30 seconds. The four-lane policy keeps two per bank and gives each slot at least 60 seconds. Changes alternate between banks 15 seconds apart once rotation begins. The starting permutation uses the same salted RF bank offset as the fixed-lane comparator. Each policy retains every available visit on active lanes, with complete dual-receiver candidate records, original sample and delivery clocks, and the unchanged original exclusions. [Protocol](PROTOCOL.md) · [Frozen visit schedules](schedule.json) · [Hardware-clock switches](dwell-events.json)

The eight mechanism recordings exactly match the earlier full-pass frequency experiment. DS26-0297 and DS29-0519 are two additional metadata-hash selections fixed before their position results. Either schedule can spend a different number of valid calls from fixed lanes on the same recording. The per-recording comparisons preserve the exact ratios. [Plan](plan.json) · [Per-RF and 15 s call counts](rf-counts.csv)

The numerical route uses the same installed compact phase-release scientific implementation, with the earlier read-only Graph observer to record winning and assigned observations, total tracks, active curvature, and longest track duration. The resources include this observer. The eight earlier full and fixed-lane controls are reused at their measured boundary. The two prospective cases also have freshly fitted full and fixed-lane comparators. [Measured Graph support](graph-support.csv) · [Numerical resources](resources.csv)

Both calibration arms use the same observations and position request. Each comparison reports horizontal errors against the surveyed roof, conditional RF independently, and the four original v5 evaluation roles. [Per-case accuracy and frequency](scores.csv) · [Paired differences](effects.csv) · [Capture-era v5 archive](capture-era-v5.csv) · [Position figures](charts/README.md)

## Eight mechanism recordings

All rotations returned positions in both arms. Rotation reduced both budget tails, while the panel medians rose. Each entry lists `c = 0` / fitted `c`.

| Support | Median error, km | P95 error, km | Within 10% of original v5 |
| --- | ---: | ---: | ---: |
| Full original inputs | 0.928 / 0.920 | 1.958 / 1.759 | 8 / 8 |
| Fixed two RF lanes | 1.947 / 1.947 | 11.307 / 11.311 | 3 / 3 |
| Rotate two RF lanes | 2.595 / 2.638 | 7.337 / 7.310 | 1 / 1 |
| Fixed four RF lanes | 1.246 / 1.210 | 10.963 / 10.986 | 4 / 3 |
| Rotate four RF lanes | 1.416 / 1.395 | 4.894 / 5.909 | 2 / 1 |

Against matched fixed lanes, rotating two improved five of eight in each arm with median paired changes of −0.447 and −0.243 km. Rotating four improved three of eight with median paired changes of +0.662 and +0.636 km. Four-lane rotation lowered fitted error on DS29-0082 from 15.325 to 6.778 km with 2,519 versus 2,327 calls. Two-lane rotation lowered it from 15.161 to 9.124 km with 1,153 versus 835 calls. Those call increases matter when attributing the improvement to rotation. Full support on that recording gave 0.516 km. [Case-level changes and call ratios](effects.csv)

Across the eight, rotated schedules spent 12,927 versus 12,656 calls at two lanes and 26,067 versus 25,943 at four. The per-case call ratio ranged from 0.979 to 1.381 at two lanes and 0.983 to 1.083 at four. The medians of the fitted paired RF RMS changes were +0.741 Hz and +0.308 Hz. [Call census](rf-counts.csv) · [RF scores](scores.csv)

## Two prospective recordings

Both four-lane rotations improved both arms versus four fixed lanes, with call increases of 0.4–0.6%. Both two-lane rotations increased geographic error versus two fixed lanes. Fitted-c error in km is shown below.

| Recording | Full | Fixed two | Rotate two | Fixed four | Rotate four |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0297 | 1.264 | 0.215 | 1.552 | 0.837 | 0.601 |
| DS29-0519 | 0.306 | 0.757 | 6.553 | 1.200 | 0.715 |

The prospective rotating-two RF RMS improved by a median 21.255 Hz in the fitted arm while median paired geographic error rose by 3.566 km. Across ten recordings, the median active-curvature track counts were 13.5 and 34.0 at two and four rotating lanes. All 26 new services published both arms. The two rotating budgets had median stored-factor wall times of 28.3 and 41.2 s and median CPU times of 24.1 and 36.0 s. Peak charged memory was 448.3 MiB with zero swap. [Graph counts](graph-support.csv) · [Resources](resources.csv)

## Reproduction

Run `python -m tools.pipeline_eval.qualification.rotating_dwell_trial /path/to/new/local/work` with the original archives and no existing rotation plan. After the terminal prediction lock, run `python -m tools.pipeline_eval.qualification.rotating_dwell_results /path/to/work --plot /path/to/plots`. All runs start from stored factors. [Terminal prediction lock](prediction-lock.json)

# Rate triplets from native GLRT detections

The rate-triplet receiver withheld every position on the six archived recordings in both search modes and calibration arms. All twelve workers completed and produced forced estimates. With fitted calibration, the global forced median error was 11,054 km. The supplied tile brought the forced median to 7.14 km. Original v5 returned all six fitted positions using the same supplied tile, with a median error of 0.83 km. [Position errors](position-errors.csv) · [Global predictions](global.jsonl.gz) · [Supplied-tile predictions](matched-tile.jsonl.gz)

| Search | Calibration | Returned / attempted | Forced median / P95 / max (km) |
|---|---|---:|---:|
| Global | Zero | 0/6 | 11,053 / 11,530 / 11,532 |
| Global | Fitted | 0/6 | 11,054 / 11,530 / 11,533 |
| Supplied tile | Zero | 0/6 | 7.88 / 17.17 / 19.23 |
| Supplied tile | Fitted | 0/6 | 7.14 / 15.76 / 18.14 |

Every global result matched centered Doppler shapes with a per-recording median RMS of 94–266 Hz. The corresponding global fits all exceeded the 1,200 Hz conditional frequency gate when the receiver terms had to explain the absolute CFO across tracks. Every supplied-tile fit also exceeded that gate. Under the matched calibration ablation, fitted (c) lowered conditional RMS by a paired median of 7.0 Hz globally and 38.5 Hz with the tile. It changed forced position error by a paired median of +0.61 km globally and −0.38 km with the tile. [Conditional frequency residuals](conditional-frequency-rms.csv) · [Paired summary](summary.json)

The estimator unwraps each antenna and RF lane from triplets of nearby GLRT peaks, extends the tracklets by local frequency prediction and compares seven-point Doppler shapes with nominal causal orbits. The shape fit removes a constant CFO from each comparison. An intercept vote groups the selected candidate orbits by receiver and RF half-band before either calibration fit. The two fits use the same selected orbit identities, observations, alias integers, endpoint bounds and evaluation budget.

Global workers searched a fixed equal-area grid and independent refinements of its twelve best separated basins. The optional tile workers received the same 25 km search tile as the archived v5 control. On the shared host, median worker wall time was 194.1 s globally (163.9–234.8 s) and 13.0 s with a tile (8.4–35.8 s). The wall clock starts after the archive packet is prepared and includes sandbox startup and packet decoding. Each worker ran in separate Bubblewrap mount and network namespaces and received the verified native capture and causal TLE packet on stdin. The runtime and numerical source mounts were read-only. The archive, historical estimates and geographic scorer were outside the worker filesystem. [Worker timings](summary.json)

A planted noisy lane retained 95 of 96 observations across a CFO wrap. On the separate analytic circular-orbit fixture, the supplied-tile shape search recovered all eight planted orbit identities. With fitted calibration it estimated 8,998.25 Hz/GHz against the planted 9,000 Hz/GHz, with 0.225 Hz conditional RMS and 0.031 m forced position error. The zero-calibration fit had 1,229 Hz RMS and 0.994 km forced position error. The global shape search missed the narrow planted basin on that fixture. Its best false basin was 1,205 km away and its consensus advantage was below the return gate. The random-peak and sign-reversed-orbit controls withheld at track formation and assignment respectively. [Planted and null tests](../../../tests/pipeline_eval/test_rate_triplets.py)

An interface preflight failed before producing any estimates because the coordinate helper required an explicit altitude and the frozen tile used an implicit default width. The final replay uses sea-level receivers in the projection and the original explicit 25 km tile width. The scientific gates and search budgets were set before opening geographic scores. [Protocol](PROTOCOL.md)

Run the blind workers and then score from the sealed outputs. The replay uses the bound corpus and needs Bubblewrap on a Linux host. The scorer reads the shipped files without the detector archive.

```sh
nice -n 15 .venv/bin/python -m tools.pipeline_eval.qualification.rate_triplet_trials \
  --scratch /tmp/glrt-rate-triplets --output /tmp/glrt-rate-results --cpus 12 13 14
.venv/bin/python -m tools.pipeline_eval.qualification.rate_triplet_score \
  --directory /tmp/glrt-rate-results
```

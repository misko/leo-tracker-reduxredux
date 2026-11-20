# Closest-approach proposals and coherent orbit selection

On two roof recordings, the closest-approach receiver withheld both global fixes in both calibration arms. With the supplied 25 km tile, it returned DS26-0036 at 3.624 km with zero calibration and 3.224 km with fitted calibration. It withheld DS29-0082 in both arms. The original rate-triplet receiver withheld both recordings in both modes. Original v5 returned both recordings with the supplied tile, with fitted errors of 1.208 and 0.517 km. [Position rows](position-errors.csv) · [Global predictions](global.jsonl.gz) · [Supplied-tile predictions](matched-tile.jsonl.gz) · [Rate-triplet comparison](../../2026_11_19_glrt_cold_start/rate-triplets/README.md)

| Recording | Search | Returned, zero / fitted | Forced error km, zero / fitted | Worker wall time |
|---|---|---:|---:|---:|
| DS26-0036 | Global | 0 / 0 | 10,130.927 / 10,130.998 | 64.1 s |
| DS29-0082 | Global | 0 / 0 | 12,019.220 / 12,021.257 | 36.2 s |
| DS26-0036 | Supplied tile | 1 / 1 | 3.624 / 3.224 | 14.7 s |
| DS29-0082 | Supplied tile | 0 / 0 | 2.583 / 5.998 | 15.5 s |

For the global fits, conditional RMS fell from 1,079 to 980 Hz on DS26-0036 and from 1,514 to 844 Hz on DS29-0082 with fitted calibration. Both forced errors grew. The winning geographic basins led the competing basins by only 0.070 and 0.083 consensus units, below the predeclared 1.5-unit gate. On the tile, DS26-0036 stayed near 537–538 Hz and improved by 0.400 km with fitted calibration. DS29-0082 went from 1,575 to 1,559 Hz, above the 1,200 Hz return gate, while its forced position moved from 2.583 to 5.998 km from truth. Each calibration pair used the same observations, orbit candidates, selected labels and CFO integers. [Conditional frequency rows](conditional-frequency-rms.csv) · [Paired summary](summary.json)

The receiver fits closest-approach time and Doppler rate from each selected raw-GLRT tracklet. At the estimated pass time it intersects the plane of zero radial velocity with the Earth and solves the measured range acceleration on each side of the orbit. Eight distinct inferred pass times yielded 87,359 and 99,830 individual orbit intersections on the roof pair. The strongest geometry cells supplied ten basins per case. The carrier-coherence fit allows several candidate orbits per track and favors labels whose circular CFO intercepts agree within each receiver and half-band. That coherence lowered global residuals enough to pass the frequency gate in three fits at geographically incorrect basins. The geographic ambiguity gate withheld all three. [Method](../../../tools/pipeline_eval/variants/pass_geometry.py) · [Protocol](PROTOCOL.md)

Planted controls recovered both geometric intersections, estimated closest approach outside the observed interval with 14 Hz Gaussian frequency noise, and recovered six consistent orbit labels despite individually cleaner distractor shapes. Uncorrelated native-scale CFO values withheld before orbit propagation. These controls exercise the component arithmetic. [Tests](../../../tests/pipeline_eval/test_pass_geometry.py)

The separate prospective scene used a fresh seed after locking the estimator, worker, triplet extractor and independent causal-orbit generator. In the supplied tile, the returned error fell from 1.292 to 0.174 km when fitting calibration, while conditional RMS fell from 166 to 80 Hz. The fitted coefficient was 1,587 Hz/GHz against a planted 1,524 Hz/GHz. The global search forced a solution 8,998 km away with fitted calibration and 158 Hz RMS. It withheld with three distinct orbit labels and a 0.236-unit basin margin. The shuffled same-lane null withheld without forced coordinates. [Synthetic chart](synthetic-errors.png) · [Synthetic predictions](synthetic-predictions.jsonl.gz) · [Synthetic truth and source lock](synthetic-scores.json)

Reproduce the roof pair with the bound archival data and Bubblewrap. The prediction process receives only the native capture and TLE packet, plus the tile for the tile run. The separate scorer opens the archived geographic references after sealing predictions. The synthetic command generates a fresh prospective case unless supplied the seed from the published synthetic score.

```sh
nice -n 15 .venv/bin/python -m tools.pipeline_eval.qualification.pass_geometry_trials replay \
  --report /tmp/pass-geometry-report --scratch /tmp/pass-geometry-roof --cpus 2 3 4 5
.venv/bin/python -m tools.pipeline_eval.qualification.pass_geometry_trials score \
  --report /tmp/pass-geometry-report
nice -n 15 .venv/bin/python -m tools.pipeline_eval.qualification.pass_geometry_trials synthetic \
  --report /tmp/pass-geometry-report --scratch /tmp/pass-geometry-synthetic --cpus 2 3 4 5
```

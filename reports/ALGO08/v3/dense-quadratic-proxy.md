# Full-short quadratic graph on the dense installed detector proxy

On the same complete DS30-0008 detector packet, replacing the installed graph settings with the settings used by the full-short raw candidate increased the live saved solve from **33.677 to 41.783 CPU seconds**. Both position errors increased by more than 1.4 km. The quadratic run used the **installed v3 detector packet as a proxy**. An authenticated full-short dense detector packet would be needed to measure the joint candidate on this recording. [Frozen protocol](dense-quadratic-proxy-protocol.md) · [Numeric receipt](measurements/dense-quadratic-proxy-summary.json)

| Live full-catalogue route | Solve CPU s | Solve elapsed s | Early proof CPU s | Horizontal error, zero / fitted `c`, km | RF RMS, zero / fitted `c`, Hz |
|---|---:|---:|---:|---:|---:|
| Installed graph, archived same-input control | 33.677 | 33.728 | 10.040 | 1.088 / 1.079 | 128.822 / 128.753 |
| Full-short quadratic graph | 41.783 | 41.797 | 8.939 | 2.603 / 2.512 | 127.140 / 127.024 |
| Quadratic graph with exact endpoint slope check | 41.845 | 41.961 | 9.031 | 2.603 / 2.512 | 127.140 / 127.024 |

The graph changes are maximum degree 4 to 2, minimum support 8 to 6, and points per coefficient 4 to 2. All other settings came from the same pinned track asset. The archived control and measured quadratic path share the exact saved detector digest, authority, causal archive, offer and live inference constructor. The clock includes graph preparation, the original dense geographic proof, signed inference and standard numerical evidence. Detector authentication, launcher setup, waveform reads, PNG creation and web publication are outside the measured scope. [Control attribution](live-inference-profile.md) · [Complete receipts](measurements/dense-quadratic-proxy.json.gz)

## More tracks and more fit work

The same 7,016 winning observations produced **322 tracks with 144 active curved tracks**, up from 236 and 111. Assigned graph observations increased from 6,456 to 6,576. Quadratic graph preparation used 2.251 CPU seconds, including 0.066 for winning detections and 2.183 for graph construction and fitting across eight RF groups. The previously instrumented installed graph profile assigned 4.419 CPU seconds to the graph. Those two preparation clocks use different instrumentation. [Profile and graph counts](measurements/dense-quadratic-proxy-summary.json)

Cold work rose from **7.801 to 12.900 CPU seconds**. The control's nearest partial-score gap was 369.976 against a requirement of 311.531, so the race finished one finalist. The quadratic graph's closest gap was 93.879 against a requirement of 279.937, so the unchanged race finished all three. The warm signed pair then found the fitted arm still moving after two refreshes and paid **2.721 CPU seconds** to run the original paired signed refit. The signed stage total rose from 0.693 to 3.805 seconds. Numerical evidence rose from 5.947 to 7.375 seconds. Both routes returned a complete signed result without an installed-solver fallback.

The endpoint shifts were **2.057 / 2.092 km**. Horizontal error worsened by **1.515 / 1.432 km**, failing the predeclared 250 m screen in both arms, while RF RMS decreased by **1.682 / 1.729 Hz**. The quadratic solution owned 4,328 observations per arm, down from 4,440. Each arm retained 4,070 common observations and the satellite assignment for every shared observation. Of those, 539 changed role. There were 370 lost and 258 new observations, with 25 versus 24 active satellite families. [Owner and RF deltas](measurements/dense-quadratic-proxy-summary.json)

The survey reference lies 6.179 km inside the original offer. Each early proof evaluated 25 probes and stopped on `inside_score`. The complete original causal catalogue had 11,177 orbits and the horizon screen retained 771 with the installed graph and 774 with the quadratic graph. Both evidence packets have 179 complete nodes, including 81 identical coarse-grid locations. Each route's local grid follows its own arm endpoints. Both replay errors were zero and both arm minima matched their own endpoints. Coverage of the geographic check is one containing offer.

## Exact endpoint slope arithmetic

The quadratic graph-only profile attributed 1.622 of its 6.384 instrumented CPU seconds to the original slope gate. The gate ran 20,285 times. For constant, linear and quadratic polynomials, the derivative is constant or linear. The maximum of its absolute value over the support is attained at the endpoints. The specialized gate uses the same binary64 derivative coefficients, normalization and endpoint evaluation, with the original check for higher degrees or unsupported coefficient data. This specialization leaves the released degree search and polynomial fits intact. The earlier exact degree bound instead reuses support checks and prunes candidates by their model-selection penalty. [Endpoint specialization](quadratic_endpoint_slope.py) · [Earlier degree bound](../single-core-2x/graph-degree-and-allocation.md)

| Matched graph-only order | Standard CPU s | Endpoint CPU s | CPU s saved |
|---|---:|---:|---:|
| Standard, endpoint | 2.262 | 1.913 | 0.349 |
| Endpoint, standard | 2.244 | 1.930 | 0.314 |
| Mean | 2.253 | 1.922 | **0.331** |

The 14.7% graph-stage saving passed the preregistered timing threshold. Every graph digest matched. The full replay activated all 20,285 checks and reproduced both arm endpoints, RF summaries, every owner and role, all 25 visited probe scores and owners, the stopping proof, path, grids and zero endpoint replay errors. Its complete solve was 0.062 CPU seconds slower than the single ordinary quadratic replay, with a 0.322 second reduction in the measured graph stage. The reversed graph-only pair establishes the local saving. The full replay verifies exact science and supplies no complete-solve speedup. [Exact checks](measurements/dense-quadratic-proxy-summary.json)

## Reproduce

The signed native data, reference and original live result are reused by digest. Score after all outputs seal. Sixty component and adjacent tests passed. [Live runner](dense_quadratic_proxy.py) · [Graph-only runner](dense_quadratic_graph_trial.py) · [Scorer](dense_quadratic_proxy_score.py) · [Tests](../../../tests/pipeline_eval/test_dense_quadratic_proxy.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
here="$PWD/reports/ALGO08/v3"
out=$(mktemp -d /var/tmp/dense-quadratic-proxy.XXXXXXXX)
gauss() {
  flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
    ionice -c2 -n7 nice -n15 taskset -c 2 timeout 95s \
    env OMP_THREAD_LIMIT=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 "$@"
}
replay() {
  gauss env PYTHONPATH="$here:$payload:$release/src:$release:$PWD" \
    "$release/venv/bin/python" -BPs "$here/$1.py" "${@:2}"
}
replay dense_quadratic_proxy "$out/quadratic.json"
replay dense_quadratic_graph_trial "$out/graph-profile.json"
i=0
for mode in original endpoint endpoint original; do
  i=$((i+1))
  replay dense_quadratic_graph_trial "$out/graph-$i-$mode.json" --mode "$mode" || exit
done
replay dense_quadratic_graph_trial "$out/endpoint-full.json" --mode endpoint-full
gauss env PYTHONPATH="$here:$PWD/src:$PWD" \
  "$release/venv/bin/python" -BPs "$here/dense_quadratic_proxy_score.py" "$out"
```

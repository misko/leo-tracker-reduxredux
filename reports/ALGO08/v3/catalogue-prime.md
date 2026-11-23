# Manifest-only priming of the ALGO08v3 TLE parser

On the saved dense DS30-0008 request, priming moved **0.500 CPU s** of named catalogue parser work ahead of the sealed detection handoff. The first ordinary preparation call then finished **0.574 s earlier**. The primer cost **0.658 s**, bringing the combined elapsed time **0.084 s above** ordinary preparation. Both arms produced exactly the same prepared solver inputs. [Paired clocks and proof](measurements/catalogue-prime-DS30-0008.json.gz)

| Measured scope | Ordinary elapsed / CPU (s) | Primed elapsed / CPU (s) |
| --- | ---: | ---: |
| Manifest and source priming | 0 / 0 | 0.658 / 0.657 |
| First `prepare_native_scan` | 3.227 / 3.225 | 2.653 / 2.652 |
| Paid total | 3.227 / 3.225 | 3.311 / 3.309 |
| Content-keyed parser within first preparation | 0.508 / 0.508 | 0.008 / 0.008 |

The clocks cover one fresh process per arm, ordinary first, on CPU 2 at nice 15 and best-effort I/O priority 7. The pair used existing tmpfs TLE snapshots and a saved detection packet, with an empty parsed-object cache at process entry in both arms. Early source inspection had already read the small manifest. The timed primer authenticated that manifest again and opened no I/Q or window index. Both timed stages charged zero filesystem input blocks. Startup, loading the saved detection packet, and validation of the returned scientific inputs sit outside the table. The measured consumer boundary ends at the first prepared solver input. [Receipt and environment](measurements/catalogue-prime-DS30-0008.json.gz)

### What can move before detections

The first segment manifest's lifecycle timestamp is an expected cutoff. The real cutoff comes from the first authenticated window's UTC bracket, and the midpoint supplies the propagation origin. For DS30-0008 the true cutoff preceded `created_utc_ns` by **216.063 ms**. Spot-checking the existing DS30-0316 metadata found the same relationship at **206.740 ms**. Consequently the manifest creation/finalization interval cannot be treated as an authenticated cutoff bracket. DS30-0008's estimated and actual cutoffs happened to give the same 20 distinct snapshot bodies, in the same order. [Manifest contract](../../../src/leo/contracts/short_window_recording.py) · [Clock derivation](../../../src/leo/analysis/glrt_frequency_input.py) · [Dense proof](measurements/catalogue-prime-DS30-0008.json.gz)

The primer applies the expected 48/72-hour snapshot windows and reads one verified copy of each body. It uses the installed native TLE validator and SGP4 constructor, returning their content-keyed cache through the existing `element_parser` port. That operation depends on the manifest timestamp and immutable archive bytes. The consumer still obtains the real cutoff from the sealed detection clock, chooses its own snapshots by collection and element epoch, and authenticates the archive bytes in the ordinary order. A guessed body outside the true window can remain an unused cache entry. A body absent from the guess goes through the ordinary parser when requested. Geographical screening and the regional orbit bank use the true origin and track-derived duration. Forecast, final roster, noise and Graph-dependent work stayed at the normal boundary. [Primer and port binding](catalogue_prime.py) · [Causal selection](../../../src/leo/operations/causal_tle_catalogue.py) · [Track-dependent preparation](../../../src/leo/operations/localization_v3_inputs.py)

The primer covered **223,923** textual rows in **20** distinct bodies, constructing **98,647** unique SGP4 elements. The ordinary consumer after priming made **101 cache hits and zero misses**. The ordinary arm made 81 cache hits and 20 misses. Each arm's consumer retained all **101** original archive reads, or **180,598,286 bytes** including repeats. Priming added **35,765,447 bytes** of verified archive reads. The parser estimated **187.7 MiB** retained at its peak. Priming extends that state into acquisition, and this trace omits receiver memory during that longer live range. [Parser, archive and resident memory counters](measurements/catalogue-prime-DS30-0008.json.gz)

### Critical-path bound

The directly scoped parser work accounts for **0.500 s** of the measured **0.574 s** post-handoff reduction. The difference also includes ordinary preparation run variation. Under these observations at least **0.084 s** of primer elapsed must overlap an otherwise idle interval to break even, and the entire **0.658 s** would have to be hidden to realize the measured post-handoff reduction. The previous original-prefix trace exposed **0.452 s** over two reads after receiver work was exhausted. That is a ceiling on what those two intervals could absorb. The intervals were measured in a separate experiment, and the primer's availability and capacity within each interval are unmeasured. This pair measured portable catalogue CPU and paid serial cost. [Prior common-clock waits](ready-io.md) · [Paired timing](measurements/catalogue-prime-DS30-0008.json.gz)

### Verification and reproduction

The exact prepared-input digest is `sha256:1f8b0a2134e2f7eaf19303f3604235e1c3a2d76e042a00b4a023c8199c75592a` in both arms. It covers Graph tracks, nominal and previous TLEs, provenance, noise, phase history, forecast, and dense orbit-bank array bytes. Independent per-body witnesses compared ordered names, NORADs, epochs and canonical SGP4 export lines, and an aggregate digest covered the original unique line pairs. The source stamps, 1,476 regional candidates, prepared clock metadata and exact consumer archive read sequence agree. The output is a saved solver input, without a new numerical fit or publication. [Verified object digests](measurements/catalogue-prime-DS30-0008.json.gz)

The measured runner is at `42b38bdb`. The complete uncompressed pair receipt SHA-256 is `d96b3d1e2a84566e58dca65acee3508d9f15f9dfef737ef790a0cb4604394fd7`. Fifty component and adjacent tests passed, including source-clock scope, manifest digest rejection, the named parser and archive authentication. [Component tests](../../../tests/pipeline_eval/test_catalogue_prime.py)

```sh
repo=/dev/shm/leo-v3-catalogue-prime
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
report="$repo/reports/ALGO08/v3"
output=/dev/shm/leo-v3-catalogue-prime-0008-replay

sudo -n systemd-run --quiet --wait --pipe --collect \
  -p User=leo -p Group=leo -p Nice=15 -p CPUAffinity=2 \
  -p IOSchedulingClass=best-effort -p IOSchedulingPriority=7 \
  /usr/bin/flock -x -w 150 /tmp/leo-algo08v2-2x-bench/gauss.lock \
  /usr/bin/env PYTHONPATH="$payload:$release/src:$release:$repo:$report" \
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  /usr/bin/timeout 110s "$release/venv/bin/python" -BPs "$report/catalogue_prime.py" "$output"
```

# A persistent cache for verified TLE source records

The two later captures reused 36 exact snapshot bodies and 403,034 textual record occurrences from earlier captures. With installed ALGO08v3's native parser and preparation collection policy, the reusable strict parsing work was only **0.077 CPU s on DS30-0016** and **0.070 CPU s on DS30-0057**. Those are generous ceilings before lookup, authentication, decoding or record reconstruction. They miss the frozen 0.25 s gate, so the trial stopped at the measured ceiling and left the original parser in place. [Matched source-stage receipt](measurements/tle-source-cache-ceiling.json)

## Exact reuse across held captures

Three different chronological DS30 captures shared much of their immutable 72-hour source inventory. The 20, 20 and 26 distinct snapshot bodies required only 30 different content digests across the panel. Every contributing Space-Track file was read through the installed archive reader, which checks the confined path, recorded digest and ASCII bytes. The 48-hour newest selection ran with the original per-capture cutoff and the full catalogue. The 72-hour inventory followed the ordinary oldest collection stamp for each repeated body. Digest reuse never replaced the collection stamp or the epoch test. [Frozen protocol](tle-source-cache-ceiling-protocol.md) · [Reader authority](../../../src/leo/operations/tle_archive.py#L166)

| Held capture and UTC cutoff | 48 h / 72 h snapshot references | Unique bodies | Bodies seen in earlier captures | Rows in repeated bodies | Repeated / current distinct line pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS30-0008, Nov 13 07:59:43 | 33 / 47 | 20 | 0 | 0 | 0 / 98,647 |
| DS30-0016, Nov 13 11:21:52 | 32 / 46 | 20 | 19 | 212,721 | 89,123 / 92,697 |
| DS30-0057, Nov 14 05:03:44 | 33 / 49 | 26 | 17 | 190,313 | 82,293 / 107,749 |

The epoch check excluded zero bodies in these captures. It remains necessary when a new archive contains a future element epoch. The within-solve parser deduplicates exact line pairs across different snapshot bodies. The table counts further overlap across different captures. Only digests of exact causal line pairs carried from one measurement to the next, and the parser itself started empty for each capture. [Installed parser logic](../../../tools/pipeline_eval/variants/algo08_causal_reuse.py)

## What a persistent source index could replace

| Held capture | Original source CPU / elapsed s | Verified reads / decimal MB | Verified read CPU / elapsed s | All native parse CPU s | Ideal repeat saving CPU s |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS30-0008, first use | 0.915 / 2.594 | 53 / 94.77 | 0.082 / 1.761 | 0.087 | 0 |
| DS30-0016, repeat | 0.800 / 0.800 | 52 / 92.98 | 0.040 / 0.040 | 0.081 | 0.077 |
| DS30-0057, repeat | 1.004 / 8.300 | 59 / 105.47 | 0.062 / 7.357 | 0.109 | 0.070 |

Each original measurement is the no-sidecar path on that capture, with normal within-solve reuse and a fresh parser at scan entry. The oracle subtracts only measured strict native parsing for whole bodies that were also causal at an earlier capture. The resulting optimistic source CPU floors are 0.723 and 0.935 s on the two repeat captures, against 0.800 and 1.004 s measured. Even erasing every native parse call for a new and unseen archive would save at most 0.109 s in this panel. One natural-order run gives no controlled cache-residency comparison. The direct read span includes file open, bytes, digest and ASCII decoding, as well as waiting. The stock reader continues to incur those costs when a sidecar misses or hits. [Actual clocks and source counts](measurements/tle-source-cache-ceiling.json)

The installed C parser already validates each canonical 3LE row directly and returns exact text records. A compiled offset index could avoid some of that work. It would still have to reconstruct the original record from authenticated source bytes, preserve complete coverage and order, and build SGP4 records using the original routine. All present source reads must verify the archive authority even when the same body has appeared before. A self-reported digest on a sidecar would authenticate neither its offsets nor its completeness. Loading an authenticated derivation would require a separate trusted publisher for the sidecar and its parser version. An untrusted or unusable sidecar must leave the ordinary path available.

SGP4 construction took 0.226, 0.198 and 0.233 CPU s, respectively. The SGP4 Python type has no supported persistent representation in this pipeline. Its within-solve reuse depends on the particular accelerated propagator copying records when it constructs a bulk array. An index of epochs and original line offsets would remain location independent. Persisting mutable runtime objects, a screened catalogue, or a per-capture answer would cross a different interface and trust boundary. These source tests never use receiver coordinates or an offer, so an identical verified source body can contribute to a new site under that site's own capture cutoff. The measured ceiling applies to repeat textual parsing.

## Reproduce

The first startup stopped during metadata preflight before any timed TLE reads because it treated the held dataset ID as a top-level scalar. The first completed observer measured repeat parse ceilings of 0.265 and 0.212 s while allowing automatic cyclic GC and retaining temporary parser rows. The corrected observer uses the installed deferred-collection wrapper, original text and element lifetimes, and the same frozen workload. The ordered causal catalogue digest, row counts and overlap counts match the initial observer on all three captures. Its slower input-wall observations are retained as measured. [Initial observer receipt](measurements/tle-source-cache-observer-unmatched.json) · [Released collection policy](../single-core-2x/solver-gc.md)

Run `tle_source_cache_ceiling.py NEW_RECEIPT` with the release Python and installed payload ahead of repo packages on `PYTHONPATH`, after the report folder. Use CPU 2, nice 15, best-effort I/O priority 7, one numerical thread, and `/tmp/leo-algo08v2-2x-bench/gauss.lock`. Both measurements ran only source preparation without raw I/Q, orbit propagation or a fitter. The runner verifies the three frozen held requests, their capture bindings, each ordinary archive body read and the pinned native parser. Fifty focused and adjacent tests passed, including archive corruption and chronological cutoff coverage. [Runner](tle_source_cache_ceiling.py) · [Tests](../../../tests/pipeline_eval/test_tle_source_cache_ceiling.py)

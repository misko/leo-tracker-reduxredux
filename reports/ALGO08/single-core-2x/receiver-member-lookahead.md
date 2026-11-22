# Bounded advice at a compressed-member transition

The bounded look-ahead saved **143.7 ms median paired elapsed time** on a 16.7 MB private XFS acquisition that started with empty compressed-file page cache. All four cold pairs improved. Every arm returned the same complete acquisition digest and all **12 selected observations**. Warm timings were mixed, with a median CPU increase of **0.13 ms**. These timings cover the acquisition boundary. [Private timing and integrity receipt](measurements/private-member-lookahead.json)

The two-scan acquisition opens one verified segment at a time. Its reader checks the manifest, index SHA-256, compressed-member size and SHA-256 before returning a decoded window. It checks the per-window hashes during decode and the complete decoded-member seal before moving to the next member. Both the released sequential reader and the research one-buffer reader consume each compressed file once. The host's sequential read-ahead operates within that file. The prior storage audit observed a 16 MiB logical-device read-ahead setting and a 2 MiB underlying RAID setting. [Acquisition and storage accounting](storage-io-accounting.md#reader-and-readahead) · [Verified reader](../../../src/leo/storage/short_window.py)

The opt-in context wraps `FastSegmentSource.windows` around the existing reader. On the first yielded window of a touched member, it advises at most **16 MiB** of the next touched member in the same segment. It uses the manifest's member path and size, no-follow read-only descriptors, and the actual iteration scope. It then closes the advisory descriptor. The normal read and its integrity checks still determine the first error and every yielded value. Unsupported or unsuccessful advice reverts to ordinary iteration. The first member of every segment is demand-read; the last issues no hint. No application workers run concurrently with acquisition. [Variant](../../../tools/pipeline_eval/variants/experimental/receiver_member_lookahead.py)

The four recorded DS30 cases each have 106 compressed payloads in 14 segments. This design can advise at most 92 prefixes and request at most **1,543,503,872 bytes**, or **18.3–18.9%** of their compressed inventories. The useful overlap is bounded by the time before those members would otherwise be demanded. The earlier DS30-0374 comparison observed a 6.43-second difference in launch-to-detections time between a zero-charge arm and an arm charged for a full read. That difference also includes other run conditions and changes to the receiver. The byte bound does not turn it into a measured hint speedup. [Saved storage inventory and receipts](measurements/storage-io-accounting.json)

## Private acquisition test

The benchmark creates one temporary XFS recording on the same logical filesystem. It has 12 generated dual-antenna 20 ms windows in three members. Both arms use the normal `algo08_scan.acquire` boundary with a frozen full two-scan detector, compressed input buffering, and paired decoded hashes. The timer includes advisory opens, checks, system calls and the verified read. The cold arm setup advises dropping only the newly generated file inodes and observes their Linux page-cache counts before each arm. Lower storage-tier residency is outside the observation. Each arm starts with fresh receiver state.

| Compressed page cache at arm start | Pairs | Median elapsed, control → hint | Median paired elapsed change | Median paired CPU change |
| --- | ---: | ---: | ---: | ---: |
| Empty for all three files | 4 | 372.82 → 221.48 ms | −143.71 ms | −1.47 ms |
| All 4,071 pages present | 4 | 116.18 → 113.30 ms | −2.66 ms | +0.13 ms |

Each condition reverses call order twice. Cold savings ranged from 37.87 to 260.12 ms, and every cold arm charged **32,568 input blocks**. Each warm arm charged zero blocks. The two advisory calls per hinted arm took 2.36–3.11 ms of wall time cold and 0.25–0.28 ms warm. The fixture's two following files totaled 11,112,020 bytes and fit entirely within their hints. Typical audited recording members average 77–79 MB, so this coverage and elapsed improvement apply to the private fixture. The matched cold and warm arms reproduced the raw authority and all 24 ordered lane rows as well as the complete acquisition digest.

## Reproduce

The runner creates and removes its own private fixture directory. It accepts a parent directory on local XFS, the existing research receiver and SHA libraries, and the passive cache-query helper built for the storage audit. All **34 targeted tests passed**. They cover clipped iteration scopes, the 16 MiB limit, advice failure, and identical error behavior for compressed, index and decoded corruption, symlinks and hard links. [Component tests](../../../tests/pipeline_eval/test_experimental_receiver_member_lookahead.py)

~~~sh
p=/tmp/leo-algo08v2-2x-bench
t=reports/ALGO08/single-core-2x
py=/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python
lock() {
  flock -x "$p/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH="src:.:$t" timeout 80s "$@"
}
lock "$py" -m pytest -q tests/pipeline_eval/test_experimental_receiver_member_lookahead.py \
  tests/pipeline_eval/test_experimental_receiver_ingress.py \
  tests/pipeline_eval/test_experimental_paired_sha256.py tests/storage/test_short_window_storage.py
lock "$py" "$t/receiver_member_lookahead_trial.py" /srv/bulk/leo-dev \
  "$p/site-free-mode-pair-pgo/candidate/use.so" /opt/leo-algo08/current/assets \
  "$p/integration-full-float-phase-signed/paired-sha256.so" "$p/ds30-cache-residency.so"
~~~

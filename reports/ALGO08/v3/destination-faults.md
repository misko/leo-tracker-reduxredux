# First-touch cost of the compressed destination

Reusing a destination on one verified tmpfs member removed **344 read-side minor faults** and saved a paired median **3.99 ms** of descriptor CPU. Complete mixed acquisition saved a paired median **3.92 ms**, with two of six comparisons slower. Touching a fresh allocation before reading moved the faults out of `readv` and took **6.70 ms CPU** on median. It made the complete descriptor **2.84 ms slower** on median. The controlled effect is too small to account for the earlier **594 ms** read on original storage at the measured scale. [Frozen scope](destination-faults-protocol.md) · [Matched stage and fault receipt](measurements/destination-faults.json.gz) · [Earlier direct-storage measurement](direct-storage-0169.md)

## Matched measurements

The source was the existing signed DS30-0169 **member 0** tmpfs copy. No original archive payload was read. The worker verified its original manifest and index, all 78,852,856 compressed bytes, all 64 individual decoded I/Q hashes and all 102,400,000 decoded bytes. All 19 successful acquisitions reproduced the archived mixed signed packet, including 51 admitted stereo visits, 13 exclusions, 102 native lane calls, 66 ordered native factors and 56 selected factors. All 19,252 source pages stayed resident, and every measured payload descriptor charged zero input blocks. [Measured driver](destination_faults.py) · [Previously staged authority](receiver-ceiling-0169.md)

The released descriptor normally calls `np.empty` just before `readv`. The pool arm uses the existing readonly loan with its exporter pinned until the last derived view is released. The fresh pre-touch arm writes to each page, including the last partial page, before the same released descriptor performs the same read and hash checks. The first pool use was a complete verified acquisition. The six later triples alternate stock→pool→pre-touch and pre-touch→pool→stock, with all clocks from the same low-priority CPU2 worker. [Allocator and ownership checks](signed_ingress_reuse.py)

| Destination | `readv` CPU median, ms | `readv` minor faults | Complete descriptor CPU median, ms | Complete verified acquisition CPU / elapsed median, ms |
|---|---:|---:|---:|---:|
| Fresh released allocation | 15.25 | 344 in each run | 15.39 | 283.62 / 283.62 |
| Reused pool slot | 11.27 | 0 in each run | 11.37 | 278.70 / 278.71 |
| Fresh with explicit page touch | 11.25 | 0 in each run | 18.23 | 288.67 / 288.69 |

Descriptor CPU improved by **2.58–34.55 ms** in all six matched pool comparisons. Complete acquisition changes ranged from a **6.56 ms loss** to a **31.34 ms saving**. Subtracting the paired clocks gives the medians above. The released reader incurred the same 344 read faults in every repeat even as its `readv` CPU varied from **13.88 to 45.79 ms**. The pre-touch control moves minor faults into allocation work, with **344 faults** in five of six touches and **855** in the other. It narrows the actual warm readv CPU to **11.14–11.55 ms**. These counters distinguish a first-touch contribution from the larger variation in descriptor service. [Individual repeated clocks](measurements/destination-faults.json.gz)

The pool constructor cost **0.017 ms CPU**. Its lazily allocated slot cost **0.028 ms** to obtain and **14.89 ms** in the initial `readv`, including **344 minor faults**. The initial descriptor took **15.02 ms CPU** and complete initial verified acquisition took **279.95 ms**. The pool allocated exactly one **78,852,856-byte** slot, retained it for six reuses, and ended every attempt with no live loan or fallback. The process reached **407.4 MiB peak RSS** while alternating arms with the retained pool. This is the whole experimental process peak with both buffer paths exercised. The retained capacity directly charged to the pool is **75.2 MiB**. [Per-run capacity, loan and process counters](measurements/destination-faults.json.gz)

## Scale of the result

The earlier original-storage DS30-0169 resident run spent **594.28 ms CPU** inside its read syscalls despite zero block inputs. This member-0 tmpfs experiment gives a controlled first-touch effect at about **4 ms** per 79 MB read. Even its largest paid descriptor difference, **34.55 ms**, is far below the unexplained original-storage interval. The original-storage run used member 1 and did not record destination minor faults, so this result cannot identify why that read was slow. The earlier three-member DS30-0008 XFS allocator trial also changed sign across orders. [Original-storage trial](direct-storage-0169.md) · [Three-member allocator trial](signed-ingress-reuse.md)

The archived DS30-0016 recording contains 13 signed members. Granting the measured median descriptor saving on all 12 opportunities after the first pool allocation projects to **0.048 CPU s**. That extrapolation assumes the same member sizes and savings, and avoids charging any additional slot or memory pressure. The historical DS30-0016 mixed reader used **3.426 CPU s** in authenticated acquisition and **1.676 s** in native DSP. Ordinary first-touch savings at the tested scale are too small to explain its broader acquisition costs or establish useful end-to-end headroom. The experiment measured no DS30-0016 waveform, storage service, solve, or publication. [Prior raw acquisition clocks](full-short-physical.md) · [Signed member count](authenticated-input-coverage.md)

## Reproduction

The receipt SHA-256 is `551fee32ff37ad1bdd17d5668143b84c002dc2a51e6f1525980135e5245e72ae`. The run uses only the previously staged tmpfs member identified by the source pin in the driver. Ten tests passed, including page-boundary handling, loan lifetime, capacity bounds and independent hash rejection for damaged synthetic input. [Component tests](../../../tests/pipeline_eval/test_destination_faults.py) · [Ownership and integration tests](../../../tests/pipeline_eval/test_signed_ingress_reuse.py)

```bash
install_root=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
gauss() {
  flock -w 60 -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
    sudo -n -u leo ionice -c2 -n7 nice -n15 taskset -c 2 env \
    TMPDIR=/dev/shm PYTHONPATH="$install_root/src:$PWD:$PWD/src:$install_root" \
    OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 "$@"
}
gauss "$install_root/venv/bin/python" -BP -m reports.ALGO08.v3.destination_faults \
  /dev/shm/leo-destination-faults-rebuild.json
gauss "$install_root/venv/bin/python" -BP -m pytest -q -p no:cacheprovider \
  --basetemp=/dev/shm/leo-destination-faults-rebuild-tests \
  tests/pipeline_eval/test_destination_faults.py tests/pipeline_eval/test_signed_ingress_reuse.py
```

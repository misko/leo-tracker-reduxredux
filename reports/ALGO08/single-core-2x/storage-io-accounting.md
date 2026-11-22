# Storage contribution to five matched DS30 publication timings

The three arms with substantial charged reads fetched the equivalent of **one page-rounded pass** over their sealed recording, within **0.021%**. The two older full-phase runs charged for these reads were the deployed-first arms. The newer covariance pair charged them to the candidate-first arm. Both reader implementations open each compressed member once. The measured imbalance therefore belongs to run conditions, alongside the independently measured compute savings. [Full-phase stage](full-phase-ds30-stage.md) · [Covariance pair](covariance-publication.md) · [Metadata and timing evidence](measurements/storage-io-accounting.json)

| Receipt and first arm | Sealed compressed bytes | Page-rounded recording inventory | Charged 4 KiB page equivalents, deployed → candidate | Elapsed minus CPU, deployed → candidate |
|---|---:|---:|---:|---:|
| Full-phase DS30-0374, candidate | 8,413,511,694 | 2,058,708 | 0 → 0 | 6.99 → 4.88 s |
| Full-phase DS30-0008, deployed | 8,182,000,357 | 2,002,189 | 2,002,171 → 0 | 93.07 → 6.26 s |
| Full-phase DS30-0155, candidate | 8,317,567,010 | 2,035,289 | 0 → 0 | 7.41 → 2.11 s |
| Full-phase DS30-0001, deployed | 8,232,792,349 | 2,014,593 | 2,015,007 → 257 | 80.42 → 6.09 s |
| Covariance DS30-0374, candidate | 8,413,511,694 | 2,058,708 | 0 → 2,058,867 | 6.22 → 12.90 s |

The inventory sums independently rounded 4 KiB pages for 106 compressed members, 106 window indices and 14 segment manifests per recording. Manifest contents and digests come from the existing input bindings. The Linux task counter in the saved receipts represents storage-layer bytes divided by 512. The page equivalents above convert those bytes to the host's 4 KiB units. They include other reads attributed to the timed process and can include kernel readahead. A zero charge means the task was charged for no storage reads. Another task could have supplied or been filling the pages. The layered XFS, LVM cache and RAID backing also prevent identifying physical spindle traffic from the task counter alone. [Kernel task I/O accounting](https://raw.githubusercontent.com/torvalds/linux/v7.0/include/linux/task_io_accounting_ops.h) · [Linux process I/O counters](https://man7.org/linux/man-pages/man5/proc_pid_io.5.html)

## How much elapsed time was exposed to storage conditions

Across the two full-phase pairs with zero charges in both arms, deployed elapsed-minus-CPU ranged **6.99–7.41 s** and candidate ranged **2.11–4.88 s**. Relative to the deployed range, the charged deployed runs spent another **85.66–86.08 s** on DS30-0008 and **73.01–73.43 s** on DS30-0001. The covariance candidate spent another **8.02–10.79 s** relative to the zero-charge candidate range. For the same recording specifically, its gap rose **8.02 s** over the earlier full-phase candidate and its launch-to-detections interval rose **6.43 s**, from **47.95 to 54.38 s**. File timestamps mark stage boundaries. The receipts only attribute CPU to the whole process, so they cannot assign the non-CPU intervals to disk waits or distinguish storage tiers and scheduling. [Stage-clock receipts](measurements/storage-io-accounting.json)

Across the four full-phase recordings, the elapsed advantage was **494.06 s** and the CPU advantage was **325.51 s**. Their difference, **168.56 s**, is the differential non-CPU contribution, about **34.1%** of the observed elapsed advantage. The two zero-charge pairs together ran **1.97×** faster by elapsed time. For covariance DS30-0374, applying the earlier same-recording candidate's 4.88 s non-CPU gap to its current 63.01 s CPU would give **67.89 s**, about **1.00 s** above half the current deployed elapsed. This sensitivity calculation uses the earlier gap as a reference for several kinds of waiting. It supplies no measured speedup from a reader change. [Matched full-phase timings](full-phase-ds30-stage.md#timing-on-the-same-raw-recordings) · [Matched covariance timing](covariance-publication.md#first-physical-recording-in-the-ds30-order)

## Reader and readahead

The acquisition entry point is byte-identical across deployment, full-phase and covariance. It disables payload verification in `inventory` and verifies each chunk during the later single traversal. The repeated segment construction reads manifest headers. The verified reader opens each window index and compressed payload, checks their seals, and drives both detector scans from each yielded window. The deployed reader reads sequential 1 MiB blocks and joins them into one compressed object. The candidate's `readv` fills a single buffer and probes EOF. The difference is a user-space copy. Both paths take the same pass over the compressed file and the same per-window and decoded-chunk integrity checks. [Sealed traversal](../../../src/leo/storage/short_window.py) · [Inventory](../../../src/leo/storage/fast_scan.py) · [Deployed file reader](../../../src/leo/storage/scanner.py) · [Candidate buffered ingress](../../../tools/pipeline_eval/variants/experimental/receiver_ingress.py)

Linux already advances readahead within a sequentially accessed file. At inspection, the logical XFS device reported a 16 MiB readahead setting and the underlying RAID device reported 2 MiB. Those are current settings. The sealed files average 77–79 MB. An application hint could start a bounded prefix of at most one following sealed member while the current member is decoded and scored, on the same application core. `readahead()` may wait for metadata, and cached entries or outstanding readahead may leave little further work to overlap. A bounded hint can move bytes earlier, while the subsequent read still fetches any missing bytes and verifies the entire member. The saved runs establish neither the available overlap nor a reduction in bytes read. [Kernel readahead behavior](https://www.kernel.org/doc/html/v7.0/core-api/mm-api.html#readahead) · [Linux readahead system call](https://man7.org/linux/man-pages/man2/readahead.2.html)

## Optional cache observation before a future timing pair

The offline audit sums and verifies sealed metadata by default. An opt-in `cachestat` helper can query cache entries for the manifest-bound compressed files before each already-authorized arm, outside the timer. It uses read-only descriptors and reports unavailable files separately. The helper neither reads payload bytes nor submits storage advice. Four tests passed, including an actual kernel query on a synthetic file. The snapshot is advisory because entries can change and can include folios still being filled. It observes the Linux file cache, with storage-tier state below it still unknown. [Audit runner](storage_io_audit.py) · [Cache helper](../../../tools/pipeline_eval/qualification/cache_residency.c) · [Linux cachestat interface](https://man7.org/linux/man-pages/man2/cachestat.2.html) · [Kernel cache-count implementation](https://raw.githubusercontent.com/torvalds/linux/v7.0/mm/filemap.c)

For a later low-load comparison, observe both arms' starting cache states and match run order on comparable inputs. Keep the charged byte counts and CPU clocks, compare the launch-to-detections and full elapsed intervals, and count hint work inside the timed launcher if a prefetch arm is authorized. This distinguishes naturally resident inputs from time hidden by earlier I/O. The present audit used saved receipts, manifests and artifact timestamps. Neither prefetch nor cache eviction was exercised.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
cc -O2 -shared -fPIC tools/pipeline_eval/qualification/cache_residency.c -o /tmp/leo-cache-residency.so
sudo -n -u leo -- nice -n15 env PYTHONPATH="$PWD:$PWD/src:$release" \
  "$release/venv/bin/python" -BPs -m reports.ALGO08.single-core-2x.storage_io_audit \
  "$binding" "$saved_pair" --bulk /srv/bulk --cache-library /tmp/leo-cache-residency.so
```

Omit `--cache-library` for an audit confined to manifests and receipts. The binding and receipts used for each case are recorded with their digests in the measurement file.

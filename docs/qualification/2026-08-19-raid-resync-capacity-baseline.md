# RAID-resync capacity baseline — 2026-08-19

Status: provisional degraded-mode observation. This is not the clean-array
production capacity result required by WP10.

## Scope

This snapshot uses committed bundles from the active
`production-24h-20260819-01` qualification while `/dev/md127` is rebuilding.
The source recordings are the ordinary immutable bundles below
`/srv/bulk/leo/recordings`; the calculation is read-only. `/mnt/qnap01` was not
accessed or modified.

At the snapshot, the RAID6 had all four members present (`[UUUU]`) and was
resynchronizing at approximately 50–53 MB/s. The qualification was using two
Pluto+ radios, two RX paths per radio, 2.5 MS/s, and 60-second dwells.

## Observed bundle geometry

The bounded sample contained 23 committed, digest-valid bundles:

| Measurement | Observed value |
|---|---:|
| Logical uncompressed CI16 bytes | 55,200,000,000 |
| Compressed payload bytes | 27,047,028,351 |
| Complete physical bundle bytes | 27,048,671,776 |
| Mean physical bytes per 60-second capture | 1,176,029,208 |
| Smallest / largest bundle | 1,166,923,154 / 1,190,870,080 bytes |
| Physical/uncompressed ratio | 0.4900 |
| Mean physical write rate during a dwell | 18.69 MiB/s |

The complete physical size includes manifests and receipts, not only Zstandard
payload shards. The observed compression ratio is data-dependent and must not
be treated as a universal bound for admission control.

With the then-current sample-derived duty of approximately 79.7%, the observed
mean projects to approximately 1.35 TB/day of recording bundles. On the
51,998,902,714,368-byte filesystem, the 70% automatic-retention watermark is
approximately 36.4 TB, or about 27 days from empty at that particular profile,
compression ratio, and duty. Holds reduce reclaimable capacity and therefore
can shorten the effective rolling window.

## Interpretation

This proves that the active capture workload can publish its current profile
while RAID resync is consuming bandwidth. It does **not** measure maximum
writer capacity, clean-array latency, safe worker concurrency, or a supported
100% duty ceiling. The resync workload and the still-running qualification make
such conclusions invalid.

The final WP10 capacity record must be taken after `/proc/mdstat` reports no
resync/recovery operation. It must include:

1. the supported generated-CI16 writer benchmark on `/srv/bulk/leo`;
2. the same real four-receiver profile at sustained acquisition duty;
3. soak-cohort job arrival and completion rates with worker count and resource
   controls recorded;
4. storage latency, memory, queue depth, and service restart counters;
5. configured worker concurrency and operational thresholds derived from the
   clean-array measurements.

Until then, the current eight-worker deployment and its thresholds remain
qualification settings rather than final tuning.

## Reproduction method

For every committed, digest-valid trial receipt, resolve its confined
`bulk://recordings/...` URI below `/srv/bulk/leo`, read its `manifest.json`, and
sum:

- every chunk's `uncompressed_bytes`;
- every chunk's `compressed_bytes`; and
- `stat().st_size` for every regular file in the complete bundle.

Divide complete physical bytes by the sum of `recorded_span_seconds` for the
dwell write rate. The daily projection is:

```text
mean_bundle_bytes / dwell_seconds * 86400 * observed_duty_fraction
```

Record `/proc/mdstat`, the soak summary, filesystem capacity, profile revision,
and bundle count with every rerun so results cannot be detached from their
operating conditions.

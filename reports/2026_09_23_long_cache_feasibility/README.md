# Long-cohort response-free cache feasibility

The public `prepare_adaptive_tle_position_inputs` entry point supplies
reconstructed RF tracks, fixed randomized masks, a strictly causal catalogue,
and its snapshot digest without a published candidate pool or receiver
coordinate. The first frozen long-TRAIN session, `scan-hop-85afa91453f8847b`,
was exported with no spatial search or fit.

Candidates are retained only when a conservative normal-cap bound permits
above-horizon visibility somewhere in either public prior disk: Sacramento
250 km or Reno 500 km. It uses each centre normal plus radius/6335 rad and
retains candidates whose maximum possible dot product reaches the WGS84
semi-minor axis at any queried epoch. The filter is response-free and avoids
hard pruning from a finite point grid; exact point visibility remains a later
scoring operation.

The first session has 11,114 causal non-debris Starlink candidates; the bound
retains 880 on its 1-second grid. Its 1,354 eligible observations and integer
`[-5,+5]` tau support spans 14,894 exact query epochs, while the reusable grid
has only 309 nodes. The ECEF position/velocity cache is 12 MiB compressed,
avoiding a full-catalogue, full-300-second dense state tensor.

Against direct SGP4 for all 880 retained candidates, linear interpolation on all
776 distinct zero-tau training epochs has CFO-removed RMS 0.0205--0.0208 Hz
over the two prior centres and deterministic 50/100-km offsets; the maximum is
0.3230 Hz. This is below the 1-Hz acceptance threshold. The executable streaming
benchmark reloads the same causal catalogue and checks the prepared evidence
digest before direct propagation. It needs no large exact-cache oracle.
[interpolation_benchmark.json](results/interpolation_benchmark.json) binds the
compact cache, receipt, adapter and executable benchmark source hashes.

The original exact-query tensor was 454 MiB; the regular grid makes reuse across
many scans practical. At this sample's size, 151 scans would require roughly
1.8 GiB compressed, although actual candidate counts and compression will vary.
The next scorer should stream scans and candidate blocks while sharing each
scan's state grid across tracks, rather than duplicate states for every track.
The benchmark covers this recording's zero-tau training epochs and four sites;
it is not a global accuracy guarantee or a position estimate. The regional bound
assumes zero receiver altitude and an above-horizon visibility policy.

[cache_receipt.json](results/cache_receipt.json) records observation IDs,
training masks, partition seeds, causal manifests, snapshot, state layout, and
SHA-256 binding. `state_cache.npz` is the reusable first-session artifact. The
export is [helper/export_long_training_cache.py](helper/export_long_training_cache.py).
It runs as the read-only service identity because its production input namespace
is not readable by the desktop user.

Reproduce into a fresh local directory:

```bash
sudo -n -u leo .venv/bin/python \
  reports/2026_09_23_long_cache_feasibility/helper/export_long_training_cache.py \
  --session-id scan-hop-85afa91453f8847b --output /tmp/long-regular-cache-new
sudo -n -u leo .venv/bin/python \
  reports/2026_09_23_long_cache_feasibility/helper/benchmark_regular_cache.py \
  --cache-dir /tmp/long-regular-cache-new > /tmp/long-cache-benchmark-new.json
```

Query the grid through `helper/regular_cache.py`; no exact-query index is an
index into the regular grid. The adapter rejects out-of-range queries. The
regional bound has a synthetic test retaining visible near-boundary directions
and rejecting a far-side satellite.

The streaming oracle comparison procedure is retained at
[helper/benchmark_regular_cache.py](helper/benchmark_regular_cache.py); its
four fixed site coordinates and source/cache digests are recorded in the
benchmark receipt.

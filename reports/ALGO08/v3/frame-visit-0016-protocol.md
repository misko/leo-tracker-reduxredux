# Single-file Zstandard visit frames on DS30-0016

Freeze before measurement. Use only member 0 of the resident DS30-0016 stage
named by `future_capture_storage.ORIGINAL`. Authenticate its original manifest,
compressed member, index, full decoded member and 64 individual stereo visits
before treating the CI16 as owned input. No other member, backing reads, RF,
position solve or public contract change. Limit file scratch to 300 MB on tmpfs
and run under the shared Gauss lock on CPU 2 at nice 15 and ionice 7.

Compare the released level-1 writer with the same writer using one checksummed
Zstandard frame per nonempty visit and a block flush at the first 80,000 samples.
Reuse public manifest and index writers. The optional experiment-only sidecar
binds complete member/manifest/index pins and chronological frame/prefix extents
and decoded prefix hashes. Each writer must start from the same authenticated
CI16. Time all writes, hashes, sealing operations and file bytes.

Measure first use from before each writer through an independent complete
readback and real two-antenna 20/8 acquisition. The installed reader must fully
decode and authenticate both formats with unchanged code and row order.
Independently check the candidate sidecar's decoded prefix hashes against that
readback. After both complete passes, measure the ready path on each format in
both orders on the same artifacts. The ordinary source reads and checks the
complete member. The candidate first authenticates the sidecar, manifest, index
and every encoded member byte, then decodes the prefixes requested by the
unchanged 20/8 schedule and the complete two-scan anchors. Report whole clocks
and component timings. No speculative first-use credit for skipping any full
verification and no I/O credit for skipping encoded suffix bytes.

Require exact complete sample/row identity and identical ordered, signed
detector outputs including empty and cancellation lanes within each detector
mode. Where practical, also compare all-20 ms lanes on both complete artifacts.
Test sidecar and compressed suffix corruption under frozen pins before any
strict reader serves a visit. Report first-use and ready results separately and
exclude release or full-recording extrapolation.

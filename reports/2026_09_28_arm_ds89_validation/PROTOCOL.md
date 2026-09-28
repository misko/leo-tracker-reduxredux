# Frozen boundary-fallback validation on DS8 and DS9

This protocol is recorded before extracting or scoring the selected inputs.
The algorithm and 1000 Hz boundary threshold are frozen to the sealed
2026_09_28_arm_boundary_fallback host-cohort-v1 and arm-v1 builds. No threshold,
margin gate, candidate budget, or matching tolerance will be tuned on DS8/DS9.

Select four chronological midpoint-quartile visits from every admitted DS8
and DS9 recording, using inventory metadata alone. This covers 65 DS8 and
105 DS9 recordings, 680 saved 120 ms dual-RX dwells, and 14,960 overlapping
20 ms windows (10 ms stride; eleven per receiver). Do not use stored production
GLRT outputs to choose inputs: their 120 ms probe stride is a different workload.
Recompute the frozen original detector on exactly the same extracted IQ.

Score every original positive candidate independently with the existing
maximum-cardinality one-to-one matcher within its receiver/window: margin
>=0.025, epoch distance <=2 samples and tracking CFO distance <=8000 Hz.
Report per-dataset and per-rate original and recovered hits, positive windows,
new unmatched hypotheses, candidate entries and actual GLRT kernel calls.
An approximate result need not preserve verification fields or candidate order.

Host execution establishes broad numerical recovery, not ARM performance.
For ARM qualification, select four 2.5 MS/s dwells per dataset by metadata:
first and last lower-edge and first and last upper-edge visits. Process the
same saved inputs serially on CPU0 of PLUTO+ 192.168.1.15, comparing the frozen
boundary-fallback binary with the latest exact-cache binary. No RF collection
or simultaneous radio capture is performed. Input transfer is outside timing.

Use the public read-only saved-IQ adapter; never mutate source datasets.
Preserve source manifest, input, binary and runner hashes. Extractions and
individual execution phases are bounded; failures must be reported rather
than removed from the cohort. This tests transfer to later recordings at the
same site, not generalization across sites or independent signal ground truth.

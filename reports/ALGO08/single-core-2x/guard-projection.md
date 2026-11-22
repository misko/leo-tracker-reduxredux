# Packing the exterior guard's orbit projections

Packing orbit cells once per region saved at most **0.009 CPU seconds** over the existing cached-catalogue guard. Packing separately at each probe ran slower on all three public offers. Both variants reproduced all 96 probe records per offer. The trial ended at the requested 0.2 s cutoff and the scorer uses its original projection. [Timing and parity receipts](measurements/guard-projection.json)

| Northern public offer | Full projection, CPU | Packed once, CPU | CPU saved | Archived guard decision |
|---|---:|---:|---:|---|
| Receiver 100 m inside | 1.293 s | 1.286 s | +0.007 s | Keeps valid fix |
| Receiver 100 m outside | 1.303 s | 1.320 s | −0.017 s | Keeps false fix |
| Far omitted | 1.262 s | 1.253 s | +0.009 s | Withholds both arms |

The test used the original northern saved detections, one prepared Graph packet and one capture-time catalogue. A 1.307 s profile on the inside offer attributed 0.684 s to phase and Doppler projection, 0.327 s to track scoring and 0.207 s to preparing the orbit geometry. The first prototype computed the full range and horizon for each probe and gathered the visible cells before projecting Doppler and its phase derivative. Its CPU times were 1.437, 1.489 and 1.469 s, against 1.317, 1.278 and 1.295 s for the corresponding controls. [Original projection](../../../tools/pipeline_eval/variants/experimental/regional_reassignment.py) · [Catalogue reuse](regional-bound-guard.md)

The second prototype reused the existing conservative horizon bound across all 96 elevations to pack one geometry per region. It preserved the full per-probe range check, ran the original projection on the packed geometry and scattered its arrays into the original catalogue order. The remaining track scoring used the original sequence for accumulation and kept the same first-row tie rule. Removing arithmetic on ineligible cells saved little after paying for the range check, gathering and scattering. Each result above is the median of two pairs in opposite orders, with CPU 2, one numerical thread and low CPU and I/O priority.

Both prototypes reproduced the complete horizon masks and the binary64 Doppler and slope for every visible cell. Every pooled score, receiver score, owner map, candidate count and probe coordinate matched the archived evidence. Evaluating the existing bound gate against the original endpoints reproduced all three decisions. This isolates the comparison to the activated guard on one public simulated waveform. The results establish no new end-to-end speed or ability to detect omitted regions close to a face. [Pointwise reference](measurements/regional-reassignment.json.gz) · [Mirrored offer](measurements/region-mirrors.json.gz) · [Archived decisions](measurements/regional-bound-guard.json) · [Catalogue tie test](../../../tests/pipeline_eval/test_regional_reassignment.py)

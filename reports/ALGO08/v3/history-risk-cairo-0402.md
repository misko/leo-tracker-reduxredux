# Cairo publication on the DS30-0402 history-risk route

On the original physical DS30-0402 full-20 ms detector packet, the Cairo and explicit-layout worker completed in **24.685 s wall / 24.622 s CPU**. The previously verified ordinary worker for the same route took **27.240 / 27.130 s**. Publication time outside the solve fell by **1.100 s wall / 1.110 s CPU**. The entire worker difference also includes a **1.555 s faster solve**, although the numerical outputs and route trace agree. Two gray orbit layers again missed the frozen visual tolerance. Use the ordinary renderer where that tolerance is required. [Frozen protocol](history-risk-cairo-0402-protocol.md) · [Verified receipt](measurements/history-risk-cairo-0402.json.gz)

| Saved scope | Ordinary wall / CPU, s | Cairo wall / CPU, s |
| --- | ---: | ---: |
| Worker start through exit | 27.240 / 27.130 | 24.685 / 24.622 |
| Timed launcher admission and worker | 27.247 / 27.136 | 25.000 / 24.936 |
| Solve, including the 179-point grid | 22.792 / 22.697 | 21.236 / 21.187 |
| Publication minus solve | 3.177 / 3.174 | 2.077 / 2.065 |
| Render and encode all eight PNGs | — | 1.551 / 1.539 |

The ordinary 3.177 s outside the solve bounds the gross opportunity inside publication and includes image verification. The ordinary worker did not isolate its draw time. The candidate draw time includes 88 ms of live artist auditing. Both workers exited zero on Gauss CPU 2 under the shared lock, nice 15, I/O priority 7 and one numerical thread. The candidate ran once, later than the existing ordinary worker. It incurred 2 major faults and 1,016 process input blocks, versus 10 and 2,552 in the ordinary worker. The CPU difference outside publication can vary between processes. [Ordinary routed control](history-risk-0402-pair.md)

The 6,773 issued and 6,761 admitted visits, original 25 km square, cutoff and 48 resident causal snapshot bodies were identical to the ordinary branch. The existing portable catalogue artifact was loaded and checked inside the candidate for roughly 1 ms each, with zero accepted cached body hits and 42 cold-parsed bodies from tmpfs. Its earlier construction is outside both clocks. The worker used the original saved handoff and prohibited waveform and backing archive opens. The table excludes lock wait, controller imports, and offline scoring. [Saved-input and orbit assertions](history-risk-0402-protocol.md)

## Scientific result

Both workers selected lean through the orbit-health rule, made one inference, accepted the original named final fit and did no terminal exterior probing on this offer. The terminal, conditional RF, fixed and fitted coordinates, all **4,821 ordered owners and roles per arm**, 179 grid locations and values, and fit path agreed exactly. The position sidecars each verified against their own published image. Error was joined offline using the same qualified reference as the ordinary test. Both position plots retain the inherited ALGO08v2 presentation title and indicate that a survey reference was unavailable to the renderer. [Reference and prior calibration comparison](history-risk-0402-pair.md)

| Calibration | Position, degrees | Horizontal error | Conditional RF RMS |
| --- | --- | ---: | ---: |
| Fixed zero | 37.846099655, −122.476659387 | 863.651 m | 100.672 Hz |
| Fitted | 37.846193033, −122.476652641 | 860.302 m | 100.576 Hz |

## Eight published PNGs

Four Cairo orbit sheets, two Cairo residual sheets, and both explicit-layout figures executed without fallback. The publisher verified and reused eight reads. Every file decoded as RGBA with the ordinary dimensions, DPI and PNG metadata. Side-by-side inspection found the orbit and residual panel headings, units, legends, zero lines, sampled position maps, paths and track bar labels readable, with changes in panel placement, tick choices and antialiasing. The timed artist snapshot binds plot series, axes and labels from the Cairo draw. The ordinary renderer was compared using its stored figures, which lack a matching live artist snapshot. The total encoded size rose from **12,445,091 to 13,025,503 bytes (4.66%)**. [Artist, raster and byte audit](measurements/history-risk-cairo-0402.json.gz)

Across the 32 registered orbit panels, colored pixels reached at least 99.893% bidirectional support within two pixels. The gray RX1 CH2 layer reached 96.00% Cairo-to-ordinary support on the all-observations sheet and 95.76% on the unassociated-only sheet. Ordinary-to-Cairo support on these layers was 99.72% and 99.75%. The other 62 of 64 layers reached the preregistered 98% in both directions. The locations and fractions reproduce the earlier DS30-0402 gray-layer result on a different solver route. A previous audit found that panel cropping and antialiasing explain most of those unmatched pixels. The frozen visual gate remains failed. [Earlier two-pixel result](named-combined-0402.md) · [Gray layer audit](orbit-registration-0402.md)

## Reproduction

Use `history_risk_cairo_0402.py launch FRESH_TMPFS_ROOT` under the installed interpreter and admission slot, then `score FRESH_TMPFS_ROOT --output RECEIPT.json` under the output owner. The one worker used commit `837e23439`. The source check allows the two pinned dispatcher revisions because `da2358879` adds the 0169 branch, leaving the 0402 worker and admission unchanged. The first scorer verified the results but stored the image map under a route field. The corrected offline reducer writes the actual route trace and preserves all original worker bytes and timings. The witness is `/dev/shm/leo-v3-history-risk-cairo-0402-result01`. Receipt SHA-256 before compression is `82a177ef8ea46681c9021ab830cdaa7f737f1ad633f644890a06ce742aac239f`. Sixteen component tests passed. [Driver](history_risk_cairo_0402.py) · [Component tests](../../../tests/pipeline_eval/test_history_risk_cairo_0402.py)

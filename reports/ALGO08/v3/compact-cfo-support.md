# Literal CI16 retention for deferred CFO refinement

Packing the original refiner's sample ranges reduces the pre-ownership buffer from **6.208 GB to 1.068 GB** on saved dense DS30-0008, **996.8 to 165.6 MB** on North, and **515.2 to 67.2 MB** on physical DS30-0016. The refill reproduced all eight diagnostic doubles, the emitted signed tuples and the refinement decisions on all 23 held North owners. These bytes are original CI16 samples. They contain no precomputed band-limited correlations or phase recurrence. [Protocol](compact-cfo-support-protocol.md) · [Receipt](measurements/compact-cfo-support.json.gz)

## Exact storage census

The original released geometry uses 14 or 15 pilot frames, each with `64 × 44 = 2,816` complex samples in its aperture. Fractional positions require seven samples before the floor and eight after, for 2,831 complex samples per frame. The packed sequence preserves both CI16 components and covers only those literal sample ranges. Epoch and fractional offset reconstruct their absolute addresses when the exact verifier runs. Neither the NCO rotation phase nor the interpolation fractions are changed. The native range function separately validates the integer branch's rounded start and a fractional branch's floor. It explicitly refuses unsupported ranges. None of the authenticated short positives in the three saved packets needed the full-lane fallback. The actual archived positives all used the fractional branch. [Native support kernel](compact_cfo_support.inc)

| Archived mixed packet | Positive short lanes / stereo visits | Owned short lanes | Whole stereo CI16 (MB) | Whole lanes packed separately (MB) | Exact support before ownership (MB) | Support for realized owners (MB) |
|---|---:|---:|---:|---:|---:|---:|
| Dense DS30-0008 | 6,380 / 3,880 | 3,788 | 6,208.000 | 5,104.000 | 1,068.023 | 634.155 |
| Public North | 996 / 623 | 303 | 996.800 | 796.800 | 165.591 | 49.656 |
| Weak DS30-0016 | 401 / 322 | 101 | 515.200 | 320.800 | 67.151 | 16.918 |

The dense census binds the actual saved mixed detector packet to its original-finish 4,367-row owner roster. The North and weak censuses use the sealed post-owner experiments. A contiguous arena with one 64-bit offset per positive plus a sentinel would add **51,048 / 7,976 / 3,216 bytes** respectively. The epoch, phase and lane identifiers already appear in the selected factor records. The owner-only column is known after selection, so retaining it alone would require a second source or a policy that obtains those samples later. The measured pack used individual allocations and charged their CPU. Arena sizing is a separate layout estimate. [Dense mixed final-fit roster](mixed-named-finish-0008.md) · [North and weak owner rosters](owned-cfo.md)

## Held native comparison and CPU boundary

One already-resident public North simulation member supplied 58 short positives, 23 in the original accepted roster. The pack held 9.614 MB across those 58 lanes. Four repetitions rotated gather/refill order and retained a fresh packed buffer on each pass. The exact gather and refill use the same native rotation, normalization, correlation and signed refinement rule. Each compared result reproduced the archived genuine refined tuple at the original accepted epoch and short CFO. Twelve deterministic CI16 controls covered both pilot edges, CFO signs, integer offsets, near-integer offsets and fractional support near the aperture limit. No original physical waveform or position solve ran.

| Measured North operation | Median CPU per relevant lane |
|---|---:|
| Pack every positive, including allocation | 63.3 µs |
| Exact gather, original diagnostics and rule, per owner | 532.7 µs |
| Compact refill, original diagnostics and rule, per owner | 526.5 µs |

Pack CPU varied from 1.892 to 4.042 ms over 58 lanes. Compact refill mostly changes storage. Its per-owner advantage over immediate exact gather is about **6 µs**, so packing pays for itself only through the reduced count of later refinement calls or the storage requirement. The measured readback clock includes original numerical refinement and Python rule evaluation. No earlier sample processing is hidden in the copy.

| CPU projection from the bounded held rates (s) | Dense | North | Weak DS30-0016 |
|---|---:|---:|---:|
| All-positive pack | 0.404 | 0.063 | 0.025 |
| Owned-only refill and waveform refinement | 1.994 | 0.160 | 0.053 |
| Pack plus refill | 2.398 | 0.223 | 0.079 |
| Immediate exact gather on all positives, same per-lane scale | 3.399 | 0.531 | 0.214 |
| Historical raw all-positive refinement, independently measured | — | 0.900 | 0.319 |

The last row is the original raw fixed-epoch kernel on the full North and weak workloads, including their original data-dependent branching. It is distinct from the held exact-gather scale. North **0.223 s** covers packing and refined waveform readout only. Adding the earlier measured **0.108 s** for changed-value alignment and the original two-arm refit, plus **0.253 s** for the follow-up exterior check, gives **0.584 CPU s**. Weak **0.079 s** plus **0.054 s** for alignment and refit and negligible exterior work gives **0.133 CPU s**. Using these average rates, the North guard makes the total deferred treatment more expensive than scaling immediate exact gather alone. The weak treatment keeps a positive CPU margin. These projections do not charge a sustained gigabyte arena, cold rereads, an integrated detector or new grid/evidence differences. No broad CPU or raw latency claim follows. [Historical North raw kernel](raw-cfo-north.md) · [Historical weak raw kernel](raw-cfo-0016.md) · [Saved post-owner fit and exterior clocks](owned-cfo.md)

## Reproduce

Run `compact_cfo_support.py` as a module under the shared Gauss CPU 2 lock at nice 15, best-effort I/O priority 7 and one numerical thread. Run `--census-only` into fresh tmpfs under the account that owns the saved weak metadata. Use that directory with `--prepared` for the resident North replay under the simulation member's original owner. The latter checks the prepared native library and independently rebuilds the North census. The first admission under the capture account failed before reading the simulated member. The paired replay used its original owner and saw all **20,571 payload and 10 index pages** resident before and after. The original cold or physical payloads stayed closed. Two component tests passed. The raw result SHA-256 is `de0a298656a7520824b28267989b594d3899796a102a635db47a0c833eace089`. [Driver](compact_cfo_support.py) · [Tests](../../../tests/pipeline_eval/test_compact_cfo_support.py)

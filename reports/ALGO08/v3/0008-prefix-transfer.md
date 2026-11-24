# Measured first-member 20/8 ms replacement on dense DS30-0008

Replacing only the first 64 visits of the released full 20 ms detector packet increased horizontal error by **277.2 m** at fixed zero and **111.5 m** at fitted c under the same frozen guarded solver. It also changed the selected satellite for **525 observations after the altered prefix**, whose native measurements were unchanged. Both versions fixed on the original physical offered region and published all eight plots and the complete standard position grids. This is a saved development comparison on a previously measured recording. [Frozen protocol](0008-prefix-transfer-protocol.md) · [Scored publications](measurements/0008-prefix-transfer.json.gz) · [Trace audit](measurements/0008-prefix-transfer-trace.json.gz)

## Exactly what changed

The two previous reversed detector pairs authenticated the same first original 64 visits and both radios, including the original hardware counters, signed compressed and decoded custody and every original visit hash. The independent named 20 ms prefix reproduced all 128 full-packet probe dictionaries exactly, including native signed CFO, rank, score, epoch and eligibility. The mixed receiver repeated byte-for-byte. Its recorded held choice was unfiltered. Reversing only the selection provenance reproduced the archived pre-selector native digest exactly, and the receipt records zero subsequent CFO refinement calls. [Original receiver experiment](original-dense-intake.md)

The first member had 19 positive lanes at 20 ms and 70 at 20/8 ms. Two unassigned lanes lost a detection, 53 gained one and 17 had a single detection in both views. All 17 shared positive lanes changed signed CFO and fractional epoch, including the four previously owned lanes. One prior predictive row at visit 49 used a mixed candidate with a −62,693 Hz CFO difference and lost publication ownership. The three other previously owned lanes changed CFO by −53.833, −39.034 and +34.704 Hz and kept the same satellite and role. Shared lanes track the same original observation coordinate. Their common presence alone provides no evidence that the receivers measured the same carrier.

The hybrid changed 72 probe rows and kept the original signed inventory, probe order, hardware/UTC epoch, delivery clocks, excluded visits, RF/channel metadata and all 6,708 issued visits after the prefix. Both start from 6,772 issued visits and 6,765 admitted stereo visits. The hybrid has its own detector recipe and native digest. The solver used the exact 37-source frozen DS30-0419 composition, supplying the new digest via the existing saved acquisition parameter. It reused the same 47 already staged original catalogue snapshots and identical supplied region at cutoff 1794556783056720638. No raw recording file was opened. [Earlier guarded solver](nomination-handoff-0419-local.md) · [Updated packet builder and launcher](prefix_transfer_0008.py)

## Both calibrated positions and all publication products

| Saved input and solver | Fix | Horizontal error, fixed / fitted c | RF RMS, fixed / fitted c | Ordered owners per arm |
|---|---|---:|---:|---:|
| Historical installed v3, full 20 ms | Yes | 1,638.978 / 1,511.956 m | 129.703 / 129.663 Hz | 4,472 |
| Guarded control, full 20 ms | Yes | 1,086.273 / 1,079.543 m | 128.821 / 128.753 Hz | 4,440 |
| Same guarded solver, measured 20/8 prefix | Yes | 1,363.447 / 1,191.018 m | 131.203 / 131.162 Hz | 4,336 |

Each paid worker inferred once, chose lean after a healthy orbit census, accepted the named survivor and had no endpoint bound or exterior evaluation. There was no named checkpoint reuse or orbit-support restart. Both calibration arms used the same owner roster within each publication. All 179 grid points, the standard path, zero endpoint objective-replay deltas and all eight fully decoded PNGs verified for each publication. The two results have different grid and path values and different pixels in all eight sheets at the same native dimensions. Each grid and path binds its own position PNG. [Publication scorer](prefix_transfer_0008_score.py)

## The untouched suffix changed satellite assignments

Only four original prefix lanes had owners in each arm of the historical installed and guarded control, or about 0.09% of full ownership. After the intervention, 20 prefix lanes had owners. Three kept their prior owner, one lost ownership and 17 gained ownership. Each full roster dropped 315 IDs and added 211. Shared rows recorded 525 satellite switches and 21 role switches, all on the original untouched suffix.

All 525 satellite switches involved the same pair over visits 5,093–6,766. There were 443 switches from NORAD 63594 to 57404 and 82 in the opposite direction. Among them, 503 observations switched in 11 intact conditional curves with identical ordered observation IDs and aliases. The other 22 were predictive in both publications. Only 6/525 (1.14%) fell below the installed receiver's 0.1 native strong-margin threshold, all predictive. The 503 conditional rows have a minimum native margin of 0.105 and a median of 0.487. Native margin measures receiver evidence. The sealed confidence instrumentation reports aggregate counts and lacks the per-curve assignment gaps needed to tell how many satellites were weakly distinguished.

The earliest recorded solver difference is the Graph stage, with 87,376 versus 87,906 edges and 6,456 versus 6,469 assigned points across the same 236 tracks. Both workers used the same two earlier catalogue digests and 1,476 current rows. Both ranked seven nodes and completed cold-search branch 1. Already at the first recorded branch-1 prefix, east/north changed from (4.478, −1.897) km to (5.676, −6.210) km. The completed cold endpoints were (4.939, −5.813) km and (4.625, −7.502) km. The trace lacks the initial ordered seeds and candidate assignments, leaving the first switched satellite proposal and the relative roles of initial nomination and subsequent optimization unresolved. [Trace reducer](prefix_transfer_0008_trace.py)

## Paid boundary and reproduction

| Saved worker | Numerical wall / CPU | In-worker publication wall / CPU | Launch through exit wall / CPU |
|---|---:|---:|---:|
| Full 20 ms | 26.666 / 26.624 s | 29.129 / 29.084 s | 30.512 / 30.465 s |
| Measured prefix | 24.374 / 24.337 s | 26.821 / 26.784 s | 28.199 / 28.160 s |

Both successful children ran in one CPU 2 Gauss lease with one numerical thread, nice 15 and I/O priority 7. Both exited zero with zero process input blocks and major faults. The controller took 0.346 wall s including input certificate replay, hybrid serialization and verification of the resident 84,051,499-byte causal view. There was no prebuilt transferable archive index. Four failed pre-inference setup workers cost 0.063, 0.342, 1.381 and 1.339 wall s separately. They exposed isolated import, admission path, digest prefix and lazy-runtime setup issues in the new wrapper. Neither scientific worker was repeated after entering inference. The timings above isolate the actual saved publications and exclude the separate historical original acquisition. The faster hybrid ended with a different graph and worse positions than the matched control.

The runner in /tmp/leo-v3-0419-prefix-owners binds the certified input bundle SHA-256 851e47b00394a7b2006889afc1dd9ec16374f0be22d8d99d5fe758d6adc7e795, the issued hybrid d9240b72ab14b87e75d4353328fc5ec4e91a6c8268158bac4ec8318a845976c4 and the prediction seal 014568015a902fc2cd85c874306caa00c3892db17f334e678eae43cf8e2ef95c. The uncompressed score SHA-256 is a6ec2ebafcd8794c2ffebff34ca646155ce9c0c24825f79021e40e73c507f8ed. Seventeen focused and adjacent tests passed. The DS30-0419 prefix comparison remains unscored. [Separate blind-case closure](0419-prefix-transfer.md)

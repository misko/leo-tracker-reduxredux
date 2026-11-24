# Integrated original-file pipeline on the known South simulation

The integrated sparse 8 ms receiver and six-Cairo publisher
reproduced the earlier 20/8 ms containing fix exactly. The same
pipeline again **falsely fixed** when the original offer put the
reference 100 m outside. The containing child took **11.118 s**,
**1.412×** faster than the earlier fresh installed v3 raw child.
It missed 1.6× on this simulation even before setup charges.
The two offers are known controls on one synthetic recording.
[Frozen protocol](integrated-south-protocol.md)

| Offer | Calibration | Integrated error | Earlier 20/8 error | Installed v3 error | Integrated / installed conditional RF RMS |
| --- | --- | ---: | ---: | ---: | ---: |
| Reference 100 m inside | Fixed zero | 325.347 m | 325.347 m | 816.789 m | 10.212696 / 6.502299 Hz |
| Reference 100 m inside | Fitted | 362.672 m | 362.672 m | 1,101.409 m | 10.108210 / 6.391940 Hz |
| Reference 100 m outside | Fixed zero | 325.334 m | 325.334 m | 817.172 m | 10.212700 / 6.502345 Hz |
| Reference 100 m outside | Fitted | 362.940 m | 362.940 m | 1,102.143 m | 10.108138 / 6.392003 Hz |

The latest and earlier 20/8 estimates and RF RMS values match
exactly in both offers. Within each offer the fixed and fitted
arms used the same rows and budget. Fitting `c` lowered the latest
conditional RF RMS by **0.1045 / 0.1046 Hz** and increased
position error by **37.324 m** inside and **37.606 m** outside.
For the omitted offer the latest estimates landed **219.699 m**
and **250.856 m** inside the east face. The terminal checked that
boundary and did not evaluate an exterior veto. Installed v3 and
the earlier exact 20/8 ms solver also published both arms on that
offer. [Earlier 20/8 containment](strict-cairo-south.md) ·
[Earlier 20/8 omission](exact-named-south-omitted.md)

Both latest runs kept the original **1,200 visits**, all 2,400
probe rows and the same 456 selected factors. The live receiver
measured **152 full-aperture** and **1,048 short-primary** stereo
visits. The held selector chose `history` for both radios,
reducing 1,346 observed factors to 456 with no CFO remeasurement.
The sparse recipe changed acquisition and terminal hashes. After
re-binding the earlier packet to that recipe, every field and
ordered observation matched. The containing run reproduced all
**304 ordered owners per arm**, the 137 numerical grid locations,
the fit path and **all eight PNG bytes and decoded pixels** from
the prior six-Cairo publication. The omitted run published 304
owners per arm, a complete 137-point grid and fit path, and eight
independently decoded PNGs. Both grids and paths identify their
actual position PNG. Each run used four Cairo orbit sheets and
two Cairo residual sheets, with eight native PNG checks and zero
readback fallbacks.

| Paid scope | Containing wall / CPU s | Omitted wall / CPU s |
| --- | ---: | ---: |
| Owner's passive admission | 1.257 / 1.255 | 1.244 / 1.239 |
| Service controller setup | 0.047 / 0.040 | 0.050 / 0.044 |
| Separate waveform-denied startup check | 1.387 / 1.349 | 1.266 / 1.262 |
| Within child, authenticated original acquisition | 5.520 / 5.519 | 4.744 / 4.743 |
| Within child, decision and publication | 4.966 / 4.960 | 4.969 / 4.964 |
| **Original raw input through child exit** | **11.118 / 11.105** | **10.345 / 10.339** |
| **Child with admission, controller and startup** | **13.809 / 13.749** | **12.906 / 12.883** |
| **Also charging passive post-run check** | **15.093 / 15.032** | **14.187 / 14.150** |

The earlier fresh installed v3 containing clock was **15.699 wall /
15.694 CPU s**. The older independently verified installed clock
was **14.370 wall s**, giving **1.293×** through exit. The
**9.620 s** earlier 20/8 child used an existing packed derivative
and paid **9.444 s** separately for creation and full readback.
The latest original-file runs used no derivative or replay map.
The archived omitted installed comparison supplies the fix and
RF endpoints. There is no same-boundary original raw clock for
the omitted offer.

Both latest runs selected lean after the history census. The
earlier portable producer predates the South cutoff. The index
served 11 bodies and prepared 12 ordinarily, with no compatibility
fallback. Regional preparation took **1.588 / 1.600 wall s** for
containing and omission respectively. Both ran two nomination
centres, found two finalists and retried ordinary ranking. The
two-centre work cost **0.220 / 0.221 s** and the retries **0.298 /
0.305 s**. This geographic transfer earned no single-rank refusal
saving. Numerical solves took **3.269 / 3.293 s**, and the renderer
**0.790 / 0.784 s**. Child-level inputs and faults were 664 blocks
and eight major faults inside, 128 blocks and zero major faults
outside. The process counters do not identify a source file.

The two workers used the unchanged `b54ea2104` runtime, with
96 source pins from the original-file development receipt and
the same native library digests. The sealed original has 19
members, **1,574,298,988 encoded bytes** and **1,920,000,000 decoded
bytes**. Every member and its index retained the original hash,
extent and order. The local original remained fully resident
before and after each child, with 384,361 payload and 188 index
pages. All 29 in-use catalogue snapshots, **51,844,567 bytes**,
were resident. No waveform copy, backing waveform read or new
collection occurred. Each worker ran as `leo` on one low-priority
CPU 2 lease. Three controller attempts stopped before scientific
launch due to user-specific library access, owner-only residency
observations and Git's checkout ownership check. The measured
launch used the file owner's read-only residency checks, a private
481,338-byte control directory, and a checkout-scoped Git option.

The measured controller froze at `f6fb9e7e6`, with prediction
seal SHA-256 values `f94821596f03d0ca1295c725d65f146ad9d0e47d7f36744a13d7e7638323dce8`
and `acfbcf553e8e11a475a58eeeeaa17bfaa1a0f41862717fba34ebfb54cb97a09c`.
Eighteen component and adjacent tests passed.
[Runner](integrated_south.py) · [Scorer](integrated_south_score.py) ·
[Machine receipt](measurements/integrated-south.json.gz),
uncompressed SHA-256
`aa6761fa9448939338cbaa56b22fb7381d04037ad9e6bf5adc63c12df8eee402`.

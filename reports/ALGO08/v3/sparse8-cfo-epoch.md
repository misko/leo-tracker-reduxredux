# Effective observation time for sparse 8 ms CFO

The equal-frame aperture correction reduced the observed stock-to-short CFO difference RMS from 100.165 to 99.098 Hz across 12,858 strict short-window matches. The squared loss fell by 2.12% pooled and 2.06% with equal capture weights. All five held-out captures with eligible matches improved. The sign-reversed correction raised RMS to 105.808 Hz.

Almost all predictions had the same sign. Removing the per-capture, radio, channel, edge and RF mean from both observed and predicted differences left a 0.027% incremental squared-loss reduction across 80 groups. The observations support a small systematic signed shift on these captures. They give weak evidence for Doppler slope variation beyond that shift. They provide one negative predicted lane and therefore little coverage of opposite slope signs. The fitted diagnostic scale was 0.724 pooled and 0.581 after centering, and the study used the unscaled source-derived correction throughout.

## Trace from native support to Graph time

The 8 ms verifier explicitly loads 80,000 samples and gathers five pilot frames. The reviewed full verifier admits fourteen or fifteen frames from 200,000 samples, depending on the candidate frame epoch and the fractional interpolation guard. Both gather 64×44 samples per pilot beginning 88 samples after the frame origin. The scout delay-product refinement spans five pilots for the prefix and fourteen for the full input. The reported tracking CFO is scout CFO plus the fractional-verification residual. Native complex correlations, signal amplitudes and phase statistics determine the actual weights. The exported candidate supplies the refined frame origin and residual but does not include enough information to reconstruct those weights. The study uses the source-derived equal-frame and within-frame midpoint convention.

The receiver exports a separate alignment epoch in samples. The ordinary Graph adapter selects one gated maximum-margin factor and reports time as the original sample-counter offset plus half of the signed 20 ms visit interval. Both detector apertures therefore have a 10 ms nominal assignment. The UTC origin comes from the midpoint of the original realtime bracket, and the earlier bracket boundary remains the TLE cutoff. The timestamp adapter applies a differential correction to short winners before Graph fitting and retains the original clock bracket, full anchors, signed CFO, native detections and visit identities.

The paired acquisition prediction uses the historic saved source configuration and a causal donor fit on earlier installed measurements. Track-piece membership is determined by the full stock graph and so can depend on later visits. The two receivers' corresponding factors are unambiguous rank-zero primaries on the same native lane for this test. The named subgroup in the table establishes common satellite ownership between the two successor calibration arms. The blind graph-time correction uses the cadence and exported frame epoch.

The earlier [12 ms primary epoch test](short-primary-epoch.md) used a different aperture and propagation experiment. Its two physical recordings moved signed squared error in opposite directions. The present cohort and fixed clock-centroid convention answer a different aperture question.

## Saved acquisition results

| Capture | Strict short rows | Difference RMS before → after, Hz | Squared loss reduction | Published successor RF RMS, `c=0` / fitted, Hz |
| --- | ---: | ---: | ---: | ---: |
| DS30-0019 | 2,375 | 105.607 → 104.260 | 2.534% | 174.592 / 174.734 |
| DS30-0178 | 2,003 | 109.310 → 109.003 | 0.562% | 159.788 / 159.677 |
| DS30-0274 | 3,269 | 98.235 → 96.810 | 2.881% | 130.288 / 130.241 |
| DS30-0330 | 2,618 | 94.489 → 93.730 | 1.601% | 125.559 / 125.555 |
| DS30-0397 | 2,593 | 95.528 → 94.217 | 2.726% | 139.860 / 139.692 |
| DS30-0049, development | 231 | 115.747 → 115.375 | 0.641% | 168.634 / 168.814 |
| DS30-0049, owned in both successor arms | 165 | 115.680 → 116.681 | −1.737% | Same publication |

DS30-0397 had a sealed installed native packet from a failed installed solve. DS30-0107 withheld in both publications and had zero eligible common positives. DS30-0452 was unverified in the original freeze. All 3,111 strict full/full anchor matches had identical native factors. No strict pilot match passed only by wrapping its CFO alias. The source model predicted a median short lead of 6.667 ms, 21.79 Hz RMS CFO change, 27.80 Hz at the 95th percentile and a 37.49 Hz maximum. The linear slope sensitivity agreed on the predicted sign in 99.992% of lanes and gave 99.064 Hz corrected RMS. Held-stock extrapolation error was 289.29 Hz RMS. The measured 1.07 Hz paired gain and the 125.55–174.73 Hz published conditional RMS describe different denominators.

The [frozen acquisition roster](measurements/sparse8-cfo-epoch-roster.json) and [signed lane result](measurements/sparse8-cfo-epoch-prediction.json.gz) reproduce these numbers. The original uncompressed receipt SHA-256 is `774acc6d3967ef08c780ac170ef0a792c16517d5d3832a97851b7f7cb3dfcf67`. Five component tests cover exact frame admission, past-only witness construction, native/wrapped alias distinction, the two stereo anchor visits and unchanged CFO/observation identity.

## DS30-0019 saved publication

The [frozen publication protocol](sparse8-cfo-epoch-0019-protocol.md) selected the lowest eligible complete held-out accession. Both cached publications used the original checked runtime, independent offer and 47-snapshot causal roster reconstructed from exact resident copies. Both produced the same original signed detections with SHA-256 `1acd2fcf8104fe990eaf40c82848e723de2da0c74f1ac1f29f59c659442d8d0d`. They each emitted a complete 179-point matched grid, both calibration paths and eight PNGs verified to original encoded and decoded media. The ordinary terminal, position/RF arms, ordered owners, path, scientific grid and all eight images exactly reproduced the archived raw successor. The grid elapsed-time field reflects the new run.

| Calibration | Ordinary error, m | Corrected error, m | Error change, m | Endpoint shift, m | Ordinary → corrected RF RMS, Hz |
| --- | ---: | ---: | ---: | ---: | ---: |
| `c=0` | 434.866 | 179.799 | −255.066 | 532.335 | 174.592 → 176.294 |
| Fitted `c` | 375.184 | 303.170 | −72.014 | 521.196 | 174.734 → 176.371 |

Both arms passed the predeclared 250 m deterioration limit. Fitting `c` reduced the ordinary horizontal error by 59.682 m and increased corrected error by 123.371 m. The timestamp adapter retained 654 unchanged anchors and moved 907 short rows earlier by 6.000004 ms and 3,435 earlier by 6.666673 ms. The solver chose the lean route in both publications. Assigned Graph rows grew from 3,633 to 3,697. For each arm, the final selected rows grew from 2,842 to 2,980 with 253 added, 115 dropped, 27 role changes and zero changed satellite IDs on the 2,727 common rows. The position improvement is an effect of a full fit with recomputed support. Published RF RMS worsened on that different support.

The ordinary process ran 16:54:02.593–16:54:20.022 UTC, taking 17.429 s wall and 16.790 s CPU. Its extra research receipt failed serialization after the complete standard publication and exact verification witness were written. The standard products were recovered and authenticated without a solver rerun. The corrected process ran 16:55:38.469–16:55:56.367 UTC, taking 17.897 s wall and 17.564 s CPU through successful exit. The measured correction was 0.106851 s wall and 0.106808 s CPU. The ordinary exception and separate naturally idle benchmark leases limit inference from the two process clocks. Both ran on Gauss CPU2, nice 15, best-effort I/O priority 7 and one numerical thread. No waveform was reopened.

The prediction seal predates survey scoring and is SHA-256 `ac8d1e2a7d35415e4d0e7c1541f888c5f136d2aa2976c48eaacdd1bdfe2ab1bf`. The [scored result](measurements/sparse8-cfo-epoch-0019-score.json) is `f921e11bf0314c18f757e688f305200f28d3ec3ffb2da2df0ed0b70ef7253b0d`. The [sealed publication receipts](measurements/sparse8-cfo-epoch-0019-receipts.tar.gz) are `ad398b1e41cc85c391cb2b72378c14c00cb69571f35fa5c5363ffea8e360294e`. This one same-site result leaves site transfer unmeasured.

## DS30-0049 development challenge

The [frozen challenge protocol](sparse8-cfo-epoch-transfer-protocol.md) used the same untuned correction and the original 48-snapshot causal view. The archived saved ordinary control had reproduced the raw terminal, both arms, owner maps, full scientific grid, path and all eight encoded and decoded PNGs. The new publication emitted the original native digest, both arms, a matched 179-point grid and eight verified plots. Ordinary and corrected selected the lean route, formed 15 tracks with 399 assigned Graph rows, and retained the same 268 ordered owner rows in each arm.

| Calibration | Ordinary error, m | Corrected error, m | Error change, m | Endpoint shift, m | Ordinary → corrected RF RMS, Hz |
| --- | ---: | ---: | ---: | ---: | ---: |
| `c=0` | 4,471.923 | 4,594.722 | +122.799 | 124.423 | 168.634 → 168.116 |
| Fitted `c` | 4,040.232 | 4,166.511 | +126.279 | 126.592 | 168.814 → 168.296 |

Both position estimates moved further from the survey despite a roughly 0.52 Hz RF RMS gain on unchanged ownership. Both remained inside the predeclared 250 m deterioration bound. The earlier acquisition result on the 165 contrary successor-owned paired lanes remains a separate measurement.

The single corrected worker ran from 17:09:07.567 to 17:09:14.669 UTC, 7.103 s wall and 6.873 s CPU through successful exit. The graph-time adapter charged 13.682 ms wall and 13.678 ms CPU. The existing parity-matched saved normal clock was 6.36 s wall and 6.31 s CPU, with no absolute timestamps in that receipt. The workers used different shared leases.

The corrected prediction seal is `56830f0eea83f88ee1ae62d48179310cea187fa5f56ba5e3d2796e4404139672`. The [scored challenge](measurements/sparse8-cfo-epoch-0049-score.json) is `3c8a2e38922b2383d9f5ed9d4b2ffe77c3aa543464280da49cf3ae5c35f2bec8`. The [challenge receipts](measurements/sparse8-cfo-epoch-0049-receipts.tar.gz) are `0272f589a1b4902b6385bb10066d9ae9002779202c318ee6d9496996c3c38c3b`.

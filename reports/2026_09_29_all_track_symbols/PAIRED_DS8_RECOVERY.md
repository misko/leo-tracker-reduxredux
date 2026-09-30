# Expanded carrier coverage for the existing S13 / DS8 visit

**Correction:** the source-identification audit found that this is the same raw
recording previously called **S13**, not an additional independent DS8 recording
or a satellite revisit. Both receiver excerpt hashes and candidate parameters
match exactly. The valid addition is four decoded carriers (472–475), with a
refitted calibration. See the coverage audit below.

A 120 ms excerpt from DS8-F039 visit 1498 yields 20 jointly pilot-qualified
frames and reproducible changing early-header signs. On ten held evaluation
frames, receivers agree on 541 of 764 selected signs (70.81%), versus 53.69%
mean agreement in mismatched-frame controls. This expands paired header coverage
within the existing S13 recording. It does not decode a header field or establish plaintext.

## Selection and provenance

The preceding 14-frame run identified original census track DS8-F039-T0039 as
qualified on all seven of its evaluation frames. Its geometric association is
conditionally STARLINK-31407; that label is not decoded here and is not an input
to the header assay. This visit was selected on pilot recovery, not unknown
header similarity.

Read visit 1498 from the existing session `scan-fw-5afe76333c91ce83` through the
public read-only storage adapters. Verify the input and analysis manifest hashes
against the census. Both receiver probes are upper edge, channel 2, RF center
11.19 GHz, probe start zero, and share the same valid-start counter. Select each
receiver's maximum pilot-margin candidate with rank as a deterministic tie-break.
The selected RX1 CFO matches the earlier track candidate; duplicate candidate
ranks have identical parameters. The two fractional frame epochs differ by less
than two native samples. This supports pairing equal frame indices but is not
an independently verified absolute transmit-time measurement.

Each receiver supplies 1,200,000 samples at 10 MS/s (120 ms). No collection was
started. Recover up to 90 frames with the unchanged native decoder and expanded
supported-carrier option, obtaining 89 complete frames per receiver. Their
intersection has 28 nonpilot carriers: 1,495,200 paired-stream complex
observations over symbols 2–301, including calibration and unqualified frames.
Only qualified evaluation frames support the claims below.

## Known pattern and unknown header

Twenty frames pass held-pilot coherence >0.5 on both receivers. In 15 of them,
symbols 194–225 pass the existing known-repeat compatibility check: fit RX0
alternating symbols, evaluate the others and RX1, require matching state
selection and superiority to shuffled-code controls. This is compatibility with
the known 60-state family, not proof of every individual bit or new payload.

For symbols 2–7, reuse the earlier header-recovery assay. The first ten jointly
qualified frames select coordinates with 20–80% positive signs using RX0 only
and set each coordinate's median real-axis confidence threshold. The remaining
ten frames evaluate those frozen coordinates and thresholds. Selection retains
152 of 168 possible coordinates; the RX0-only evaluation confidence gate leaves
764 decisions. RX1 never selects the mask.

| Measurement | Result |
|---|---:|
| Matched receiver agreement | 70.81% |
| Marginal-sign baseline | 57.46% |
| Mean mismatched-frame agreement | 53.69% |
| Mismatched-frame range | 50.65–56.68% |
| Agreed selected signs | 541 / 764 |

All nine nonzero cyclic shifts of the evaluation RX1 frame sequence are controls.
They retain coordinates and the frozen RX0 selection mask. Controls are dependent
descriptive comparisons; they are not independent statistical trials.

| OFDM symbol | Selected decisions | Receiver agreement |
|---|---:|---:|
| 2 | 120 | 68.33% |
| 3 | 136 | 66.18% |
| 4 | 103 | 76.70% |
| 5 | 123 | 69.11% |
| 6 | 140 | 71.43% |
| 7 | 142 | 73.94% |

These per-symbol values are descriptive subdivisions, not selection of the best
symbol followed by independent validation. The symbol-4 marginal baseline is
already 73.13%, so its larger agreement alone is not strong evidence of changing
data. Shared receiver distortion, calibration effects, and model errors remain
possible; agreement is not transmitter bit accuracy.

## Available observations and limits

The alias audit isolates the four added carriers from the 24 previously covered
ones. They provide 23 discovery-variable coordinates and 108 held selected sign
decisions. Receivers agree on **79/108 (73.15%)**, compared with a 50.41% mean and
63.89% maximum across the nine mismatched-frame controls. These are additional
observations within an already studied acquisition, not independent replication.
The previously covered carriers account for the other 656 decisions and 462
agreements. Original-coordinate values also change under the expanded SSS fit:
relative RMS change is 5.14% on RX0 and 12.14% on RX1. The entire 541-agreement
count must therefore not be added to previous S13 counts as new information.

`audit_ds8_alias.py` verifies the shared session/visit, both raw excerpt hashes,
and both candidate dictionaries against the earlier signal inventory. It saves
the exact alias, calibration changes, per-coverage metrics, and input hashes in
`local/paired-ds8/alias-audit.json`. There are **zero new independent recordings**.

`local/paired-ds8/summary.json` stores both receivers' real-sign strings,
selection masks, and agreement strings (`?` for excluded or disagreeing signs),
along with source hashes, timing/candidate parameters, and the selected track
binding. The 541 agreements are corroborated observations, not 541 independent
information bits. There is no descrambler, FEC/CRC validation, byte framing,
satellite ID, timing field, or orbit message established by this result.

This separately calibrated 120 ms recovery preserves the earlier 20 ms results.
Neither its extra frames nor its calibration should be silently substituted into
the frozen four-frame census. The three earlier qualified STARLINK-35850 candidate
tracks use different selected visits and therefore were not combined as if they
were simultaneous receiver observations.

`paired_ds8_recovery.py` writes only ignored research outputs and removes temporary
raw excerpt copies. The 33 research-folder tests plus two reused header-assay
tests pass (35 total), as do Ruff checks. Source/method and recovered-file hashes
are recorded. No raw corpus file, remote branch, or deployed service was changed.

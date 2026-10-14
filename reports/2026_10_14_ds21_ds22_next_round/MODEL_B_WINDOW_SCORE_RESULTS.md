# B059 receiver conflict dominates the likelihood gap

The frozen window audit completed both independent slices:0539.552s and05912.066s,3 objective plus3 explicit orbit evaluations each, **6 objectives and zero fits** total. Each case had120/135/140-second whole-slice bounds. Two workers ran independently. All saved objective/NLL, row-normalization/mixture, group-partition and physical-prior closures passed; no reference or held data was read. Sources and original states remained unchanged.

For059, the accepted nearby donor loses NLL453.406707 to the distant incumbent. Only34.168005 (7.54%) comes from conditional detection/visibility normalization; **419.238702 comes from residual-mixture density**. Uniform visibility normalization alone cannot explain the ranking. The original full start3 loses675.764562, of which33.908757 is normalization and641.855805 mixture density.

The distinguishing feature is opposing receivers at both nearby full states:

| 059 alternative minus incumbent | RX0 NLL gap (1820 windows) | RX1 NLL gap (702) | Low NLL gap (1550) | High NLL gap (972) |
|---|---:|---:|---:|---:|
| Accepted A-final donor after B fit | +1002.111398 | −548.704691 | −103.375266 | +556.781973 |
| Accepted original full start3 | +936.350736 | −260.586174 | +862.166870 | −186.402307 |

The donor and original start3 do not have the same bad band: they expose different coupled timing/calibration/association modes. A blanket low-band or high-band downweighting is not justified. Receiver0 prefers the incumbent at both alternatives, while receiver1 prefers both alternatives. This is conditional score evidence, not proof of a faulty receiver or correct satellite identities. Unequal sample counts are recorded; equalizing weights merely to make a closer state win would not be a validated likelihood model.

| 059 donor channel | Windows | NLL gap | Mixture gap | Assignment TV | MAP switches |
|---|---:|---:|---:|---:|---:|
| CH1 | 286 | −143.452003 | −149.968140 | .564101 | 168 |
| CH2 | 424 | −111.567675 | −116.940114 | .701476 | 308 |
| CH3 | 418 | +142.034320 | +135.877054 | .757848 | 327 |
| CH4 | 422 | +9.610092 | +1.763701 | .628397 | 276 |
| CH5 | 270 | +30.742828 | +28.005509 | .617912 | 174 |
| CH6 | 269 | +289.747555 | +288.602887 | .684419 | 190 |
| CH7 | 226 | +172.341909 | +170.816096 | .853151 | 198 |
| CH8 | 207 | +63.949682 | +61.081710 | .586742 | 124 |

Receiver0 accounts for277.025/279.959 of CH6/CH7 losses, with70.300/63.525 fewer signal-posterior windows respectively. Receiver1 gains107.617 NLL on CH7. Receiver0 loses signal mass276.523 overall, receiver1 gains148.866. Such masses are model probabilities, not classifications supplied by truth.

The loss is not a handful of isolated windows. Donor positive row losses sum2011.938494 and gains sum−1558.531787. Top10 windows contribute2.20% of positive loss, top10019.49%; reaching80% needs451 of2522 windows. Original start3 needs580 windows for80% of positive losses. Receiver0's donor loss occurs in every prespecified60-second diagnostic bin; the last two bins contribute357.434+361.659 of its1002.111 loss. These bins are descriptive summaries, not new holdouts or excluded groups. The donor-versus-incumbent clock-function difference RMS is148.603Hz on RX0 and143.218Hz on RX1; their similar sizes and coupling to orbital timing/association do not establish a receiver0 clock defect.

The059 prior ledger confirms a frequency-likelihood ranking problem rather than an expensive near-state prior:

| State | Common timing | Relative timing | Receiver clock | Group contrast |
|---|---:|---:|---:|---:|
| Incumbent | .004103 | 528.180198 | 74.854147 | .376347 |
| Donor | .008651 | 447.801772 | 25.850134 | .464907 |
| Original full start3 | .048402 | 444.260772 | 43.266304 | .446139 |

053 is a contrasting failure, not a replication of the receiver split. Its donor loses NLL214.046095 = normalization5.410633 + mixture208.635462; both receivers lose (+124.183065/+89.863030) and both bands lose (+182.674832/+31.371263). CH1/2 losses208.222/112.721 offset CH3/4/5 gains103.750/34.518/97.847. Positive losses1430.114830 offset−1216.068735; top10 contribute3.20%,80% needs320 windows. Original053/start3 is nonstationary and diagnostic-only; it is not admitted into selection. These current after-only results do not establish that the replaced bank or transferred original starts cannot support a better mode. A's separate replacement-bank audit should be assessed on its own source authority.

## Next falsifiable sensitivity: receiver time versus additive frequency

Source inspection distinguishes receiver-specific receive-time offset from additive receiver frequency correction. A receive-time contrast changes Doppler by satellite-dependent derivatives; additive offset/receiver-clock terms apply the same Hz correction to every candidate in a row. Existing original B supports receiver offsets/slopes/common-clock functions and common/relative **satellite** epoch timing, but no receiver-specific observation-time offset. The native relative-phase experiments changed satellite phase/Earth-orientation conventions, not this receiver-time contrast. The older039 receiver RF contrast already had a completed negative localization control and is not being repeated.

The059 input metadata records one radio ID, one continuous-IIO generation, a common2.5MS/s device-counter anchor and per-probe receiver IDs0/1 with valid-start counters. Its first-valid host bracket is249.882791ms and realtime-minus-monotonic spread16.028µs; `source.timing` is absent. This provides no evidence of independent receiver UTC clocks or a conversion fault. Prior039 timing-source inspection likewise found consistent integer-counter/support-center conversion and no calibrated absolute-sync attestation. Fitted per-satellite timing allowances must not be called measured clock errors.

The authorized next diagnostic, not yet executed in this report, is a source-frozen fixed-state centered receive-time contrast (+delta for RX0,−delta for RX1), compared with a centered additive-frequency contrast. Prescribe time grid within±.25s (host-bracket context, not a measured relative-clock bound), preserve all calibration functions at original recorded times, and retain source ephemeris/timing-domain failures as excluded rather than clipping. Require an exact delta0 oracle and finite-difference validation of the satellite-dependent time derivative. Assess all three predetermined states and both cases under independent120-second zero-fit slices; no geography fit or new receiver-time parameter. A useful result requires a time-specific likelihood gain that is not imitated by the frequency contrast, with support and boundary effects disclosed. Negative profiles rule out this bounded sensitivity; positive profiles still do not establish a timestamp fault or accuracy improvement.

Source/protocol457f961ff;7 tests and Ruff passed. Runtime `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-b-window-score-audit-v1`. Case terminal SHA256:053`3def4d234e0939d7b0fc318520a2de0ed96a80f400f59cbc449a8700eccd2fed`;059`f84b106f8b4ed9cd4e2c9d2e2cf0a6b49c03685a0e4b88a3b6794d5496931783`. Per-state window records retain exact scores, residual means/RMS (undefined at zero signal posterior), visible counts, MAP IDs and physical clock values. No fit or histogram promotion follows from this audit.

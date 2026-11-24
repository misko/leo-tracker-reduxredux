# How much does one recording explain?

DS30-0049 accounts for **67.7% of the net excess fitted squared error** between the candidate and ALGO08v3 on the 13 shared fixes among the first 16 verified original recordings. Excluding that case reduces the gap, but the other 12 still have **1.090 km candidate RMS versus 0.786 km installed**. All 16 recordings remain in the primary comparison. [Scored pair evidence](measurements/ds30-field-error-influence.json)

| Calibration | Shared fixes | Candidate worse | DS30-0049 share of excess squared error | ALGO08v3 RMS on other 12 | Candidate RMS on other 12 |
|---|---:|---:|---:|---:|---:|
| Fixed zero | 13 | 9 | 70.8% | 0.816 km | 1.113 km |
| Fitted | 13 | 8 | 67.7% | 0.786 km | 1.090 km |

Each contribution is the candidate’s squared horizontal error minus ALGO08v3’s squared error on the same recording. The denominator is the sum of the signed contributions, including improvements. DS30-0049, DS30-0452 and DS30-0124 had the three largest contributions under both calibrations. DS30-0170 improved on both. These cases were selected after scoring and can help distinguish mechanisms. The remaining 12 provide a sensitivity check on this one-site cohort. [Shared-fix error decomposition](ds30-centered-error.md)

## Information in the search region

The frozen search square was 25 km wide. Its center was **8.193 km** from the independently surveyed roof. The separate point used for satellite screening was 57.742 km from the survey. Returning the search center without observing the radio signal would therefore produce the same 8.193 km error on every recording here. Every returned fix in each calibration beat that distance, with 13/16 returned by ALGO08v3 and 14/16 by the candidate. The original timing and fix-rate comparisons continue to include every attempt. Testing at a second physical location requires separate observations.

The analysis authenticates the original plan and detached offer, the frozen 16-pair export and its seal, the independent reference roster, both selected attempts and the relocated DS30-0452 proof. It reads no waveforms and launches no solver. The receipt SHA-256 is `8cc847243bb31cf40837b37b88cfb4b7cf805117b2221966224406a881be0344`. [Reproduction script](ds30_field_error_influence.py) · [Original comparison protocol](full-successor-field-protocol.md)

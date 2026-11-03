# Scan-16 waveform replication inventory

This directory prepares a measurement-only replication of the scan-0 known-pilot
audit.  The target was frozen before IQ access: among all 18 qualified exact
IID source-deletion folds for scan 16, physical-NORAD group 67103 has the
largest east/north endpoint movement, 1,839.721532 m.  The NORAD association is
conditional candidate evidence rather than authenticated identity.

The selected DS11-F045 session is `scan-fw-6a8bd0ca578b58eb`.  Its three tracks
contain 124 localization-training and 81 localization-held observations:

| Track | Receiver | RF | Training | Held |
|---|---:|---:|---:|---:|
| `sha256:f7bbef3…750a3a` | 0 | 11.46 GHz | 22 | 11 |
| `sha256:b6c1f80…7f470c` | 0 | 11.46 GHz | 56 | 36 |
| `sha256:aa39593…186dad` | 1 | 11.46 GHz | 46 | 34 |

Repeated visits are allowed because tracks can use different receivers, probes,
or acquisition candidates in the same visit.  Preparation records the exact
`(visit, receiver, probe, candidate-rank)` identity for every selected row and
reports both repeated-visit and repeated-identity groups.

Preparation reads only public tracking metadata.  It does not open IQ, run the
waveform estimator, fit position, or evaluate geography.

# Joint physical-identity screen assessment

The single `joint_identity` arm was screened on indices 0, 4, 8, 12, 16, 20,
24, and 28 using the common protocol. All eight processes exited successfully
and all eight selected endpoints qualified. The arm does not pass the screen:

| metric | joint identity | original IID |
|---|---:|---:|
| qualified / attempts | 8 / 8 | 8 / 8 |
| median position error | 3107.934 m | 3108.162 m |
| P90 position error | 6046.174 m | 6046.037 m |
| maximum position error | 6346.243 m | 6345.775 m |
| paired wins | 4 | -- |
| sub-kilometre results | 1 | 1 |

The common-IID held-score change summed over the eight selected endpoints is
-0.03797. Median process time was 25.59 seconds.

| index | joint error (m) | IID error (m) | endpoint position move (m) |
|---:|---:|---:|---:|
| 0 | 765.072 | 765.072 | 0.0007 |
| 4 | 3509.635 | 3510.342 | 0.779 |
| 8 | 5270.649 | 5270.648 | 0.0017 |
| 12 | 1180.884 | 1183.767 | 5.731 |
| 16 | 2153.140 | 2153.140 | 0.00004 |
| 20 | 2706.233 | 2705.981 | 0.293 |
| 24 | 5917.572 | 5917.578 | 0.0075 |
| 28 | 6346.243 | 6345.775 | 0.474 |

The pre-fit training diagnostic showed that every grouped identity was already
effectively saturated at the original IID endpoint. Fixed points two kilometres
away produced meaningful gradient changes in some scans, but optimization still
returned within 5.8 metres of every IID endpoint. Sharing the discrete identity
therefore changes mixture constants and some off-endpoint curvature without
adding useful position evidence on this panel. This family should not advance
to replication, and its negative result does not justify adding association
power or weight parameters.

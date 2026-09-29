# Training-weighted support from target-disjoint donor groups

All 72 target scans are excluded from donor fitting. Donor groups become available only after their last observation. Target distributions remain the original eight-scan q020 fits; no held outcome or reference error selected starts or groups.

| Target dataset | Tracks | Mean one-group mass | Mean two-group mass | Mean target signal × two-group mass | Tracks with two-group mass >0.5 | MAP with two groups |
|---|---:|---:|---:|---:|---:|---:|
| DS7 | 1434 | 3.433% | 0.000% | 0.000% | 0 | 0 |
| DS8 | 1434 | 11.401% | 0.264% | 0.263% | 4 | 4 |
| DS9 | 1460 | 35.902% | 7.986% | 7.405% | 117 | 117 |

Strong group support requires signal responsibility × conditional candidate weight ≥0.5 in at least one donor track in that group. Two-group support counts distinct fitted groups, not multiple tracks sharing geometry. These descriptive masses are not identity confidence or calibrated probabilities.

| Donor group | Scans | Qualified starts /3 | Training-selected start | Exported tracks |
|---|---:|---:|---|---:|
| DS7_donor_00 | 8 | 3 | northwest | 469 |
| DS7_donor_01 | 8 | 3 | origin | 474 |
| DS7_donor_02 | 8 | 3 | origin | 486 |
| DS7_donor_03 | 8 | 3 | southeast | 467 |
| DS7_donor_04 | 8 | 3 | origin | 450 |
| DS7_donor_05 | 8 | 3 | origin | 459 |
| DS7_donor_06 | 8 | 3 | northwest | 420 |
| DS7_donor_07 | 8 | 3 | origin | 472 |
| DS8_donor_08 | 8 | 3 | southeast | 481 |
| DS8_donor_09 | 8 | 3 | southeast | 482 |
| DS8_donor_10 | 4 | 3 | origin | 232 |
| DS8_donor_11 | 8 | 3 | origin | 453 |
| DS8_donor_12 | 8 | 3 | southeast | 455 |
| DS8_donor_13 | 5 | 2 | northwest | 303 |
| DS9_donor_14 | 8 | 3 | southeast | 475 |
| DS9_donor_15 | 8 | 3 | northwest | 484 |
| DS9_donor_16 | 8 | 3 | southeast | 491 |
| DS9_donor_17 | 8 | 3 | southeast | 488 |
| DS9_donor_18 | 8 | 3 | origin | 477 |
| DS9_donor_19 | 8 | 3 | northwest | 461 |
| DS9_donor_20 | 8 | 3 | origin | 465 |
| DS9_donor_21 | 8 | 3 | southeast | 468 |
| DS9_donor_22 | 8 | 3 | origin | 476 |
| DS9_donor_23 | 8 | 3 | southeast | 483 |
| DS9_donor_24 | 1 | 3 | northwest | 59 |

![Target candidate support from independent donor groups](support.png)

The auditor verifies hashes, disjoint recording coverage, group availability, optimizer/audit qualifications, training-only selection, row score sums and weight normalization before mapping candidates and aggregating support. It is not an independent radio-likelihood implementation or satellite-identity verifier. No residual correction or new geographic accuracy result is produced.

[Protocol](PROTOCOL.md), [complete summary](summary.json), [group tests](tests.log), [optimizer tests](optimizer-tests.log), [evidence](evidence-sha256.json).

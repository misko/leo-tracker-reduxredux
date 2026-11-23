# Survey-channel geometry versus satellite assignment

The survey and stock solver assigned the same satellite to **every shared observation** on both containing offers. On the southern control, the survey's 152 observations exactly matched the stock observations on paid visits, including their roles. A cold exact signed fit with those stock assignments reproduced the survey's position and RF results in both calibration arms. On dense DS30-0008, the schedule removed 3,023 of the 4,472 stock observations before association. A further 182 paid stock observations were absent from the survey result and 63 shared observations changed role. The evidence favors buying additional overlapping time and RF coverage over spending solver time relabeling shared observations. The dense case leaves room for better retention and role assignment within the paid data. [Frozen protocol](survey-owner-diagnostic-protocol.md) · [Numeric summary](measurements/survey-owner-diagnostic.json) · [Auditable owner and oracle receipts](measurements/survey-owner-diagnostic.json.gz)

## Owner accounting

Each row below applies to both calibration arms. Shared means the same original session, receiver and hardware counter. Changed role is measured independently of changed NORAD.

| Containing offer | Paid stereo visits | Stock rows | Unpaid stock | Paid stock | Survey rows | Common | Paid stock missing | Survey only | Changed NORAD | Changed role |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| DS30-0008 | 2,539 / 6,765 | 4,472 | 3,023 | 1,449 | 1,407 | 1,267 | 182 | 140 | 0 | 63 |
| South containing | 450 / 1,200 | 266 | 114 | 152 | 152 | 152 | 0 | 0 | 0 | 0 |

On dense, the survey kept channels 3 and 8 continuous after the opening survey. Every original stock observation on those channels was paid. The other six channels supplied valid rows during the survey only. Of the 182 missing paid owners, 122 were predictive and 60 were conditional in stock. The 140 survey-only rows comprised 41 predictive and 99 conditional observations. All 63 role changes occurred by 50.064 seconds. Fifty-four shared rows changed from conditional to predictive and nine changed in the other direction. All of those role changes retained their original satellites. The maximum stock-owner support available within the existing payment schedule was 1,449 rows, 32.4% of the full stock set.

| Offer and population | Rows by original time third | Families | Seen by both receivers | Seen on multiple RFs | Seen in both RF halves | Median family time span (s) | Median TLE epoch age (h) |
|---|---|---:|---:|---:|---:|---:|---:|
| Dense stock | 1,530 / 1,395 / 1,547 | 26 | 17 | 22 | 21 | 77.26 | 20.61 |
| Dense stock on paid visits | 905 / 318 / 226 | 19 | 7 | 9 | 7 | 41.81 | 20.57 |
| Dense survey | 954 / 269 / 184 | 16 | 7 | 7 | 5 | 41.43 | 19.76 |
| South stock | 114 / 76 / 76 | 7 | 7 | 0 | 0 | 36.00 | 10.29 |
| South paid stock and survey | 76 / 0 / 76 | 4 | 4 | 0 | 0 | 36.00 | 11.05 |

Dense survey owners still spanned 2.203 to 298.887 seconds across the recording. Within individual satellites the available time span declined, and the survey lost most of the late stock observations and multi-RF support. The selected TLE ages did not shift older. On the southern offer, channels 1 and 6 kept four families and all 76 late-third measurements. All 76 middle-third measurements belonged to groups that were no longer paid. Long recording-wide time span can coexist with missing simultaneous or within-family support.

## Cold fixed-owner test

The southern paid intersection had eight original curved tracks. Their complete stock aliases were available in the independently sealed curved membership witness. The diagnostic used the supplied offer, original measured paid observations and causal history, with initial endpoint at the offered centre and phase reference zero. It rebuilt receiver noise and nuisance estimates on retained data, passed the original ordinary and signed two-arm checks and the exterior check, and completed a 165-point numerical grid. Both objective replay differences were zero. This oracle used stock membership and discrete alias labels only. The two fitted positions and both RF RMS values matched the survey exactly. The cold solve through evidence took 2.858 CPU s, plus 0.150 s to reconstruct the original Graph membership layout. This is an off-clock diagnostic with perfect labels.

The dense paid intersection contained 1,194 conditional and 255 predictive observations. Seven of 37 originally conditional tracks lost the required curvature on their paid rows, affecting 92 observations. The available stock alias witness covered the conditional rows and lacked discrete aliases for all 16 predictive tracks. A paid-only fit using every original membership could not meet the frozen support and witness requirements. It stopped after a 1.711 CPU s Graph membership audit. No dense oracle endpoint was scored. Substituting new aliases, changing roles, or dropping the undersupported rows would change the question.

| Containing offer and mode | \(c=0\) horizontal error (km) | Fitted \(c\) horizontal error (km) | \(c=0\) RF RMS (Hz) | Fitted \(c\) RF RMS (Hz) |
|---|---:|---:|---:|---:|
| Dense installed v3 | 1.639 | 1.512 | 129.703 | 129.663 |
| Dense full signed joint | 1.086 | 1.080 | 128.821 | 128.753 |
| Dense survey | 2.234 | 2.168 | 125.474 | 125.524 |
| South installed v3 and full signed joint | 0.817 | 1.101 | 6.502 | 6.392 |
| South survey and paid-stock oracle | 1.144 | 1.143 | 6.969 | 6.969 |

The southern geographic loss reproduced with exact stock assignments on the paid support. Dense RF RMS fell by 4.229 and 4.139 Hz versus stock while position errors rose by 0.595 and 0.656 km. Dense missing paid observations and role changes could contribute in addition to the large schedule loss. The unavailable dense oracle limits separation of those effects. These saved controls measure RF support and position separately and leave any new schedule, acquisition speed, or geographic qualification untested.

## Receipt verification

The two support-only reconstructions reused the original detector packets, masks, capture-era archives, offers and released Graph. They stopped after the ordinary fit and any original repair, before the signed refit and grid. The original signed update preserves the support. Each reconstructed observation-to-NORAD map matched the exact sealed owner digest for its calibration arm, and the role counts matched. Independent stock owner rows were checked against the archived installed digest. The support-only costs were 10.204 CPU s for dense and 2.776 CPU s for south. Those diagnostic costs do not replace the original survey solve clocks. No raw samples were opened.

To reproduce, run `survey_owner_diagnostic.py CASE OUT --saved-receipts RECEIPT_DIRECTORY` under the shared Gauss lock with the pinned ALGO08v3 payload and release on `PYTHONPATH`. Then run `survey_owner_oracle.py run CASE ORACLE_OUT OUT --saved-receipts RECEIPT_DIRECTORY` for the same two cases. `survey_owner_oracle.py score DIRECTORY SCORE_OUT` scores the two sealed `CASE.oracle.json` outputs. The original survey receipt directory can be passed directly by a user who can read it. The measured run used byte-identical read-only copies for the release account because the original directory was private.

# Causal preparation on the physical DS30-0016 Cairo handoff

The previously sealed causal portable index saved **0.219–0.240 s** in matched preparation on the fresh physical Cairo run's exact native handoff. All prepared numerical arrays and documents reproduced, including the original catalogue elections, provenance, orbit bank, tracks, and forecast. The new bounded prototype reused **14,356 of 20,105** elected Satrec objects, but added memory and showed no reliable time gain. This experiment stopped at preparation and read no waveform or backing catalogue files. [Receipt](measurements/validated-satrec-reuse-0016.json.gz) · [Preparation driver](validated_satrec_trial.py)

| Fresh saved worker, original offer | Cold 1 | Candidate 1 | Candidate 2 | Cold 2 |
|---|---:|---:|---:|---:|
| Paid regional preparation, wall | 1.564 s | 1.345 s | 1.322 s | 1.562 s |
| Paid regional preparation, CPU | 1.564 s | 1.345 s | 1.322 s | 1.562 s |
| Whole preparation-only worker through exit, wall | 2.904 s | 2.590 s | 2.596 s | 2.840 s |
| Process peak RSS | 356.1 MiB | 367.0 MiB | 366.9 MiB | 355.8 MiB |

The raw Cairo publication used cold indexing. The four corrected measurements exercised the installed same region wrapper, original signed 20/8 ms handoff, original offer, exact Graph port, native strict TLE parser and all archive checks. The unchanged archive contains 46 signed snapshot files in tmpfs. Preparation verified 177,013,672 logical bytes in 99 calls across 38 filenames. Of that total, 109,065,803 bytes were repeated reads of already visited paths. In the stable controls, all verified reads took 116–117 CPU ms, strict record parsing took 86–88 ms, the two orbit-bank calls took 321–324 ms, and forecast took 260–263 ms. Logical read volume includes digest checks and ASCII decoding. It does not measure block-device I/O. Repeating bytes does not imply repeated strict parsing. The cold route parsed 20 distinct bodies once each and constructed 92,697 native source pairs and 20,105 elected scan objects. Prior audits bounded genuine predecessor sharing at about 29 ms and newly reusable exact nominal propagation at about 20 ms in their measured scopes. [Earlier repeated-read and predecessor audit](predecessor-election.md) · [Earlier weak propagation audit](live-orbit-setup-audit.md)

## New scan-local object retention

The prototype uses only exact two-line keys and retains at most 24,576 native objects during source admission. The ordinary constructor still validates each admitted source pair and supplies the original epoch and angular fields. Election transfers an exact pending object when available or uses the normal constructor. It leaves the original order, cutoffs, export checks and later canonical-record validation in force. The scope clears unused references before handing off prepared inputs. Each measured original-offer run reused 14,356 elected objects, constructed the remaining 5,749, evicted 56,421 pending records, and discarded 21,920 unused records on exit. This represents roughly 20 MiB additional process peak RSS. [Prototype](validated_satrec_reuse.py)

| Comparison | Cold preparation CPU | Retention preparation CPU | Observed change |
|---|---:|---:|---:|
| Original, cold first | 1.558 s | 1.643 s | +0.085 s |
| Original, retention first | 1.829 s | 1.659 s | −0.170 s |
| Narrow control, cold first | 1.590 s | 1.627 s | +0.037 s |

The reverse cold arm spent 0.512 CPU s in its two unchanged bank calls, versus 0.323 s for the corresponding retention run. Subtracting bank clocks leaves 1.317 versus 1.336 s in that reverse order. The narrow control halved the search width to 12.5 km and shifted the independent coarse latitude by 0.125 degrees. It moved the regional roster from 1,449 to 1,451 while keeping all canonical output and bank bytes equal between its two modes. The experimental loader recreates the measured prototype only in private scratch, and verifies the recreated source by digest. The ordinary historical orbit source retains its original digest. Nineteen focused and adjacent tests passed. There is no basis to credit scan-local retention with closing the raw gap.

## Existing index eligibility and raw budget

The existing DS30-0008 artifact was eligible because its cutoff `1794556783056720638` precedes the signed DS30-0016 cutoff `1794568912154038024`. It served 19 of 20 verified bodies, with 212,721 indexed rows and one cold body. The guard and artifact load together took 2.25–2.41 ms. The content and producer manifest were already present. A standalone earlier producer took **4.320 s** wall and **4.319 CPU s** through source preparation and export. These one-time costs are separate from the matched load clocks. The known artifact occupies 2,688,577 bytes. [Earlier producer and transfer](portable-orbit-index.md)

Keep the original physical Cairo recipe and pass these index parameters to `exact_named_raw.py`.

```text
--portable-orbit-index /dev/shm/leo-v3-portable-orbit-prep-02/dense-orbits.bin
--portable-orbit-index-sha256 sha256:fc51655ff19185cc382aeed925e466cea7290453256d45f80446aceef6f9e30e
--portable-orbit-producer-sha256 c1c2f5d911c978ad7673a2a53f05e272806f87c539f2f0a552b7e02916fe9c8b
```

The raw named clock was 10.745 s and the raw Cairo candidate was 7.677 s. The 1.6× target for that pair is 6.716 s. Transferring just the measured preparation saving would put the candidate at **7.44–7.46 s**, about **1.44×** faster than named and **0.72–0.74 s** above the target. A fresh raw publication with the index was outside this experiment. [Original physical Cairo comparison](history-risk-physical-cohort.md)

Two initial portable attempts were rejected by the normal compatibility checks. The first instrumentation wrapped the installed parser while the artifact was being admitted. The second imported the experimental index source before its pristine counterpart could bind. The final worker restores the unwrapped parser during admission and explicitly imports the exact original index source by its recorded hash. All paid launches are in the receipt. Only the validated original-offer pair orders contribute portable speed credit. All trials and tests used the shared low-priority Gauss CPU 2 slot.

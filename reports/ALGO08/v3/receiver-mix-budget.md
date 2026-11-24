# Receiver CPU budget on three blind DS30 recordings

DS30-0359 allows **26.588 s** to deliver detections if its 89.017 s installed raw runtime is to halve and the saved candidate’s downstream and admission costs stay at 17.921 s. Its original signed packet determines **1,296 full-anchor and 9,024 short primary calls** under the candidate schedule. Applying the measured rates from four completed runs gives **22.57–26.35 CPU s** for authenticated acquisition. That leaves **0.24–4.01 s** for every additional cost through the detector handoff, including startup and waits. We have not timed this full waveform. Its first 79,072,939-byte member had zero of 19,305 pages resident when checked on November 24. [DS30-0359 saved result](ds30-0359-combined.md) · [Passive original admission](first-member-0359.md)

| Blind DS30 case | Full / short antenna calls | Intake allowance for 2× | Projected acquisition CPU | Remaining time through detections |
|---|---:|---:|---:|---:|
| 0163 | 1,338 / 9,322 | 38.267 s | 22.89–26.72 s | 11.55–15.38 s |
| 0173 | 1,190 / 8,276 | 34.840 s | 21.70–25.35 s | 9.49–13.14 s |
| 0359 | 1,296 / 9,024 | 26.588 s | 22.57–26.35 s | 0.24–4.01 s |

Each row authenticates the actual installed 20 ms packet and pairs the two receivers by original visit, RF, channel, edge and sample counter. The candidate uses one full anchor followed by seven short primaries within each admitted RF stream. The counts follow from that schedule before history-dependent selection. For each observed run we multiply its CPU per full and short call by the corresponding target counts. We price the rest of its measured acquisition CPU per original compressed byte, after subtracting both callback categories. Each result uses all three rates from one donor run together. The prediction includes no waveform reads from these target cases. A change in selected detections can also change the solver workload or the decision to publish. [Reproducer](receiver_mix_budget.py) · [Source hashes, stream counts and modeled costs](measurements/receiver-mix-budget.json)

| Measured donor | Original acquisition CPU | Full call | Short call | Other acquisition CPU per compressed GB |
|---|---:|---:|---:|---:|
| Gauss 0016, fixing recording first | 2.894 s | 2.516 ms | 0.814 ms | 1.428 s |
| Gauss 0016, withholding recording first | 2.923 s | 2.561 ms | 0.829 ms | 1.431 s |
| South, containing offer | 5.519 s | 3.109 ms | 0.953 ms | 1.637 s |
| South, omitted offer | 4.743 s | 2.529 ms | 0.870 ms | 1.366 s |

Using either Gauss run to predict the South containing run underestimates its CPU by **0.75–0.80 s**. The same Gauss rates predict the South omitted run within **0.025 s**. The South runs used the same original samples and the same primary schedule. Since the region is used downstream, the observed acquisition difference cannot identify a region-dependent receiver effect. The four scenarios show timing sensitivity on two inputs and provide no statistical bounds on the blind recordings. [Gauss clocks](integrated-original.md) · [South clocks](integrated-south.md)

The 2× release goal applies to both pooled timing gates. If every target incurred the same extra elapsed time above its modeled acquisition CPU and measured downstream charge, the three-case allowance would be **7.09–10.83 s per recording**, depending on the donor. The summed gate is limiting in all four scenarios. This calculation cannot establish a passing fix rate, a position-error distribution or deployment throughput. Those still require matched complete recordings.

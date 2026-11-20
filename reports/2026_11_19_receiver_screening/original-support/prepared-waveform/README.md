# Prepared original detector on a complete lower-edge waveform

The prepared FFT replay reproduced every original native candidate on DS26-0237 and returned a compact position within **5% of original v5 in both calibration settings**. It processed every valid visit of a distinct lower-edge recording, complementing the earlier complete upper-edge DS29-0082 replay. The installed original detector, preceding combined implementation and prepared implementation had equal public outputs, ordered factors and acquisition attempts on two qualified raw visits and one prospectively hash-selected visit. The whole replay used the qualified prepared binary. [Protocol](PROTOCOL.md) · [Source lock](source-lock.json) · [Prior prepared-kernel qualification](../original-kernel/README.md) · [Earlier upper-edge recording](../../antenna-confirmation/capture-whole/README.md)

## Native fidelity

The replay authenticated all 106 chunks and all 6,768 visits. It retained the two capture exclusions, 6,768 delivery clocks, UTC anchor and final sample counter. All **13,532 physical probe rows and 60,306 ordered candidate records** matched the original canonical factors byte for byte. Both used 10,243 passing candidates on 3,740 physical probes, with zero gate changes. The fresh output carries its own detector and source-lineage metadata. [Audit](audit.json) · [Fresh native stream](native.json.gz) · [Prediction lock](prediction-lock.json)

## Position

The actual waveform factors and the full original archived factors were sent through distinct compact services on the same original 25 km offer and verified 47-snapshot causal archive. Both returned identical coordinates, conditional RF RMS and frequency scores in both calibration arms. [c = 0 error chart](charts/c0/modifications.pdf) · [Fitted-c error chart](charts/fitted_c/modifications.pdf) · [Per-arm scores](scores.csv)

| Position input and solver | `c = 0` geographic error (km) | Fitted `c` geographic error (km) | Conditional RF RMS, `c = 0` / fitted (Hz) |
|---|---:|---:|---:|
| Actual prepared full IQ → compact | 0.3531 | 0.2619 | 80.67 / 80.61 |
| Full archived original factors → fresh compact | 0.3531 | 0.2619 | 80.67 / 80.61 |
| Earlier stock four-region IQ → compact | 0.3816 | 0.3230 | 92.54 / 92.43 |
| Earlier wide fifth-region IQ → compact | 0.2186 | 0.1786 | 93.72 / 93.65 |
| Original v5, all four reference roles | 0.3618 | 0.2714 | 102.89 / 91.74 |

The earlier fifth-region measurement had the smallest geographic errors on this recording. The prepared original replay had the lowest conditional RF RMS among the compared receivers. The two metrics give different orderings.

## Host runtime and prepared cache

The eight independently capped raw workers took 483.71 seconds wall through complete authenticated replay. Aggregate detector CPU was 2,914.74 seconds, including 923.16 seconds in folded coarse kernels and their input preparation. The recording spans 299.98 seconds, so the measured detector CPU alone is 9.7 times that duration. Median/P95 detector CPU was 372/625 ms per valid visit and wall was 385/858 ms. None of the 6,766 valid visits met 20 ms wall. The largest individual charge was 512 MiB, the largest detector process RSS was 216 MiB, and swap use was zero. The fresh compact service took 50.37 seconds wall and 48.19 CPU seconds, with 313 MiB charged peak and zero swap. [Per-visit timing](timing.csv) · [Timing chart](timing.pdf) · [Service receipts](receipts/)

The workers executed 15,330 full folded grids and scored 4.292 billion CFO-by-epoch cells. They reused prepared filters and FFT workspaces on 15,314 grid calls, with 16 cold builds and 5,712 filter FFTs. Every input spectrum was computed from that visit's raw samples. The largest declared per-grid workspace was 2.07 MB. On the three fresh preflight visits the median dual-detector CPU was 1,498 ms installed, 443 ms preceding combined and 402 ms prepared. Those paired observations compare detector modes on identical CI16 windows. The full wall and CPU measurements apply to the new prepared replay. [Cache ledger](cache.csv) · [Paired launch check](receipts/smoke.json)

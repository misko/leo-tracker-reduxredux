# How much of the twofold target can the position grid supply?

On the first 62 original DS30 recordings, ALGO08v3 took 6,077.80 seconds and the candidate took 3,632.25 seconds. The candidate needed to save another **593.35 seconds** to halve total elapsed time. Its entire position grid took **183.45 seconds** across the 58 grid publications. Giving those maps zero cost would raise aggregate speedup from **1.673× to 1.762×**. All 62 attempts contribute to both timing gates. [Measured field clocks and source digests](measurements/grid-time-ceiling-first62.json.gz)

| Scenario on the same 62 recordings | Summed wall speedup | Median paired wall speedup | Seconds above half the ALGO08v3 total |
|---|---:|---:|---:|
| Measured candidate | 1.673× | 1.727× | 593.35 |
| Entire grid takes zero time | 1.762× | 1.806× | 409.90 |
| Native receiver runs 1.5× faster and the entire grid takes zero time | 1.962× | 2.029× | 59.60 |
| Native receiver runs 1.5× faster and the entire grid takes 44.21% of its measured time | 1.911× | 1.983× | 140.71 |

The 44.21% figure is the measured elapsed-time ratio for a single fitted-calibration likelihood calculation on DS30-0008. Two runs per build used the same saved numerical input. Applying that ratio to the **entire map** also accelerates geometry, assembly, prediction and other operations outside that calculation. The 1.5× receiver rate is an independent engineering assumption. The complete-map experiment on DS30-0138 can measure how much of this extrapolation holds. [Physical DS30-0008 measurement](profiled-grid-export-0008.md) · [Receiver and solver budgets](receiver-solver-targets.md)

On these 62 recordings the receiver callbacks consumed 1,050.89 seconds, and the solver consumed 995.92 seconds including the maps. Under the last scenario, cutting the remaining 812.48 seconds of solver work by **17.32%** would meet both time gates if other intervals and outcomes stayed fixed. Savings from reading and decoding would also count toward the 140.71-second gap. On the last eight recordings alone, the same two assumed rates give 1.934× summed and 1.995× median paired speedup, with 13.53 seconds still needed. These scenarios price runtime. They provide no position accuracy measurement for a modified receiver or solver.

The calculator verifies the frozen plan, both selected field attempts and their build and recording identities. It reads the completed 179-point map clock from each candidate's original acquisition ledger and checks that it lies inside the solver clock. The four attempts without map products retain their full elapsed times. Run the following as the campaign reader on Gauss. It reads signed timing metadata and performs no waveform or orbit processing.

```sh
python -B -m reports.ALGO08.v3.grid_time_ceiling /srv/postgres-nvme/leo-ds30-evaluation-20261124
```

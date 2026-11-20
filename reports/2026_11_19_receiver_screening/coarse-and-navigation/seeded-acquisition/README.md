# Causal seeded pilot acquisition

On the held upper-edge recording, the seeded tracker reproduced **one of 29** original positive follow probes. The development-budget native control reproduced **eight**, with slightly lower total detector CPU. Only four of the 29 reference-positive probes had a usable seed when the tracker reached them. [Stage chart](active-search.pdf) · [Held audit](audit.json)

## Raw replay

The two spans were frozen by hashing complete neighboring chunks using capture validity. The development span used lower-edge DS26-0237 visits 3840–3967, all 128 valid. The holdout used upper-edge DS29-0082 visits 4608–4735, with 92 valid and 36 physically excluded. Each recording revisited its eight physical RFs within the span. [Protocol](PROTOCOL.md) · [Source lock](source-lock.json)

The first and every sixth valid visit per physical RF ran the original conditional 12/22-anchor detector on saved IQ. These slots were set by chronology and physical validity. The best original gate-positive candidate seeded its own receiver, stream generation, RF and edge. Follow visits propagated epoch with the hardware counter and rational 750 Hz frame period, carried signed CFO, ranked bounded local epochs using six known symbols in seven frames, and ran original fractional GLRT on the best two proposals. Only a fresh gate-positive local result within the signed CFO innovation bound could update the state. A physical receiver without a current seed returned an empty candidate row. [Raw service receipts](receipts/)

Development tried fixed phase-rate uncertainties of 220 and 550 samples/s. Each matched three of 56 reference-positive follow probes, and the 220 setting used 0.98 detector CPU seconds on follow visits versus 1.21 seconds for 550. It also used 39.27% of the native control's full follow CPU, so that fraction became the native control's per-RF follow-call budget before the held run. The held shifted control used the same bounds and original anchors with a half-frame displacement applied to its seed. [Development lock](tune-lock.json)

## Held outcomes

The 20 shared original anchor scans executed 41 dense grids, exactly reproduced the archived anchor factors, and returned six gate-positive anchor probes. Their median detector wall was 453.08 ms. A signed identity match means an original and measured gate-positive candidate on the same physical probe agreed within two samples of wrapped epoch and 2,000 Hz of signed CFO. Folding CFO by the symbol alias period produced the same counts on this held span. [Held factor comparison](stage.csv) · [Search diagnostics](active-search.json)

| Held policy | Active follow visits | Searched receiver probes | Positive follow probes | Signed matches | Follow CPU (s) | Total detector CPU (s) |
|---|---:|---:|---:|---:|---:|---:|
| Seeded local search | 11 / 72 | 20 | 1 | 1 | 0.773 | 10.255 |
| Half-frame shifted | 9 / 72 | 18 | 0 | 0 | 0.630 | 10.112 |
| Native budget control | 25 / 72 | 50 | 10 | 8 | 0.595 | 10.077 |

The native budget control skipped 47 follow visits, and its realized follow CPU was 77% of the seeded policy's. The seeded policy's 144 physical follow probes contained 114 without a surviving original anchor and ten with expired state. Those groups accounted for 17 and eight of the 29 reference-positive probes, respectively. Of the four reference-positive probes with a search, three were inside the predicted epoch and signed CFO bounds. One reached the two-candidate shortlist and passed the raw gate. [Coverage and diagnostics](active-search.json) · [Full held factors and clocks](receipts/DS29-0082.log.gz)

| Active follow policy | Median wall (ms) | P95 wall (ms) | Calls at or under 20 ms |
|---|---:|---:|---:|
| Seeded local search | 54.59 | 123.88 | 1 / 11 |
| Half-frame shifted | 65.52 | 116.48 | 0 / 9 |
| Native budget control | 23.60 | 30.26 | 1 / 25 |

The active timing chart covers follow visits that processed raw IQ. The all-poll timing includes skipped or unseeded work according to each policy. The development and held services completed in 21.02 and 15.95 wall seconds on CPUs 12 and 13, with 512 MiB caps and zero swap. This comparison ends at detector factors from the two frozen spans. [Active-search timings](active-search.csv) · [All-poll timings](stage.pdf) · [Stage seal](active-lock.json)

# Keeping every visit in the receiver

The installed ALGO08v3 executable repeated the original 1,200-visit North simulation in **16.133 s elapsed and 16.128 CPU s**. The earlier identical command took **16.761 s elapsed**. Both verified all 19 source members from memory on one low-priority Gauss core. The signed detection packet, opportunities, both positions and RF residuals, both owner digests, terminal, 137 grid points, and the encoded and decoded content of all eight PNGs matched. In the independent postprocessing check, in-memory image dimensions were tuples and archived dimensions were JSON lists. Normalizing the dimensions reproduced the expected checksums on the existing output. Only one new benchmark child ran. [Frozen control](current-north-control-protocol.md) · [Command, clocks, products and verification](measurements/current-north-control.json.gz)

The earlier all-visit 8 ms candidate took 10.828 s, giving **1.49×** against the fresh control and **1.55×** against the earlier one. The respective half-time targets are 8.066 and 8.380 s. This repeat matters when interpreting changes worth a few tenths of a second. The full North control is simulated, and the recording-specific times do not establish a DS30 panel result. [8 ms original-input run](eight-ms-native-live.md)

## Physical DS30 position and timing

On the complete weak DS30-0016 saved 8 ms input, the corrected solver took **4.166 s** against **4.516 s** with the earlier preparation. All 506 signed measurements, both positions (490/980 m), all 115 assigned observations in each calibration, the regional decision, 179 grid points and the eight PNGs matched. The original 808-visit 8 ms acquisition took **3.141 s** in a different process. Adding those clocks gives **7.307 s** against a named half-time of **5.412 s**. The 1.895 s gap is a model. One combined original-waveform physical run is still needed to measure that time. [Exact saved publication and disjoint clocks](weak-all8-combined.md)

The released DS30 metadata includes 455 recordings. All 14 smaller than 500 MB withheld in both ALGO08v2 calibration arms. The smallest positive there is DS30-0016 (992 MB). A previous partial staging operation retained 103 MB of its required inputs. This makes a small positive saved-data test cheaper for the shared server while the storage device is busy. V2 enrollment supplies no fresh v3 speed or accuracy evidence. [Complete size roster](ds30-v2-size-roster.md)

## Which observations require a second scan at the full anchors?

The mixed receiver gives every antenna a short primary search at each non-anchor visit. At every eighth admitted visit of each RF stream it runs a full 20 ms two-scan search. Removing cancellation at those anchors preserves the short visits that earlier thinning experiments lost. The saved maximum-margin output tells us where a rank-one winner hides the first-scan alternative.

| Input | Full antenna calls | Hidden first-scan alternatives | Original selected → selected if those anchors were empty |
|---|---:|---:|---:|
| DS30-0016, 12 ms short | 186 | 0 | 475 → 475 |
| DS30-0057, 12 ms short | 584 | 12 | 1,996 → 1,984 |
| DS30-0008, 12 ms short | 1,696 | 26 | 7,336 → 7,310 |
| Simulated North, 12 ms short | 304 | 1 | 456 → 456 |
| Simulated South, 12 ms short | 304 | 0 | 456 → 456 |
| DS30-0016, 8 ms short | 186 | 0 | 506 → 506 |
| Simulated North, 8 ms short | 304 | 1 | 456 → 456 |

Every held-history choice stayed the same under that erasure. It is only a sensitivity check for the ambiguous lanes. A separate archived native comparison measured the real alternative for one of them on DS30-0008. The 32 anchor calls in the first 128 visits took **93.816 ms** for two scans and **54.827 ms** for first-scan-only execution. All 256 original opportunity descriptors matched the archived mixed packet, and every paid anchor matched the original verified rank-zero result. At visit 71 on antenna 1, the winning two-scan carrier was **394,594 Hz** and the actual first-scan carrier was **296,630 Hz**. Dropping that row would misrepresent the algorithm. [Seven-case sensitivity receipt](measurements/anchor-primary-transfer.json.gz) · [Dense native operating points](measurements/anchor-primary-dense-prefix.json) · [Original timing ledger](primary-schedule.md)

The local optimizer remains another possible target. On accurate all-visit North and weak DS30-0016, even eliminating the original fixed-roster proposal and signed refit work entirely removes at most **0.660 and 0.351 CPU s**, respectively. On dense and hard signed fits, the entire compiled curved likelihood takes **0.450 and 0.321 CPU s**. These are intersecting scope limits from different recordings. They cannot be summed as a speedup. [Trust-region ceiling](fixed-roster-trust-ceiling.md) · [Factorization ceiling](signed-factor-roof.md)

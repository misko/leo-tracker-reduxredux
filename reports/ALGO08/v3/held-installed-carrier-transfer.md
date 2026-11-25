# Installed-carrier agreement on two saved held half-blends

The frozen DS30-0218 diagnostic transferred to both archived recordings. Strict signed agreement rose **322 → 340** on DS30-0019 and **457 → 463** on DS30-0274. The loose-window counts stayed fixed. The p95 absolute signed CFO difference fell **306.86 → 236.29 Hz** and **261.35 → 206.68 Hz**, respectively. [Protocol](held-installed-carrier-transfer-protocol.md) · [Sealed evidence](measurements/held-installed-carrier-transfer.json)

| Recording and native receiver | Edited | Full winner / empty | Coverage | 250 Hz / 2 samples before → after | Restored / spoiled | 2,250 Hz / 6 samples before → after | p95 absolute CFO difference (Hz) |
|---|---:|---:|---:|---:|---:|---:|---:|
| DS30-0019, both | 366 | 355 / 11 | 96.99% | 322 → 340 | 20 / 2 | 347 → 347 | 306.86 → 236.29 |
| DS30-0019, radio 0 | 256 | 250 / 6 | 97.66% | 231 → 238 | 9 / 2 | 243 → 243 | 306.86 → 243.85 |
| DS30-0019, radio 1 | 110 | 105 / 5 | 95.45% | 91 → 102 | 11 / 0 | 104 → 104 | 302.78 → 201.48 |
| DS30-0274, both | 499 | 484 / 15 | 96.99% | 457 → 463 | 11 / 5 | 472 → 472 | 261.35 → 206.68 |
| DS30-0274, radio 0 | 293 | 284 / 9 | 96.93% | 270 → 270 | 4 / 4 | 275 → 275 | 249.23 → 220.98 |
| DS30-0274, radio 1 | 206 | 200 / 6 | 97.09% | 187 → 193 | 7 / 1 | 197 → 197 | 261.35 → 182.45 |

On DS30-0019, 201 of 355 matched edits moved closer and 154 farther. MAE fell from 2,383.49 to 2,370.49 Hz. On DS30-0274, 286 of 484 moved closer and 198 farther. MAE fell from 3,640.67 to 3,627.11 Hz. The paired distributions retain the large signed separations. There were zero extra joint matches when testing whole-alias offsets. Installed empties remain in coverage with no reference CFO. Hardware-referenced pilot arrival was unchanged by the edits.

Each ordinary calibration arm yielded the same edited owner split. On DS30-0019 the 290 edited owners had 280 installed winners and gained 11 strict matches overall. The 76 edited nonowners had 75 installed winners and gained seven. On DS30-0274 the corresponding counts were 426 owners with 418 installed winners and five net gains, and 73 nonowners with 66 installed winners and one net gain. Both arms’ splits and full signed/absolute statistics are in the receipt.

Both original and edited native digests reproduced, along with the sealed edit digests and ordinary owner ledgers. Each original installed packet was bound to the same capture, radio, tuning and hardware epoch through the original verified field pair. Both recordings had compatible receipts. The results show that the saved edits’ tighter agreement with full-aperture measurements appears beyond the prospective DS30-0218 case, with unequal gains by receiver. The separately acquired full receiver is a same-capture measurement reference. The historical publications still lack the signed residual vectors needed to determine the fixed ordinary model effect on these two recordings. [Prospective 0218 comparison](masked-cfo-0218-installed-agreement.md) · [Saved fixed-state audit](held-cfo-fixed-residual.md)

The metadata-only CPU 3 result reproduced byte for byte. Eight focused tests passed. No Graph, receiver, orbit or position replay ran. [Runner](held_installed_carrier_transfer.py) · [Tests](../../../tests/pipeline_eval/test_held_installed_carrier_transfer.py)

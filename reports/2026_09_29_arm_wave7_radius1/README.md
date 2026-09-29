# Narrower regional search with exact ranking improvements

This experiment keeps four proposal centers but searches their three adjacent
epoch cells (radius one), instead of five cells (radius two). It starts from
Wave7's exact single-scan radix histograms and integer-key implementation.
Coarse and final scoring retain all 16 frames; every receiver/window runs.
This is an approximate search change, separate from the exact ranking gains.

On the matched four-dwell 2.5 MS/s Cortex-A9 panel, outer CPU time falls from
863.029 ms for Wave6 to **776.227 ms/dwell**. Exact ranking alone takes
831.795 ms. All **119/119 standard hits** remain, with 173 emitted candidates
instead of 182. Coarse search takes 88.353 ms versus 134.470 ms in Wave6.

On the separate 704-dwell mixed-rate host panel, recovery is
**19,206/19,581 standard individual hits**, versus 19,217 for Wave6.
The net reduction of 11 is not an identity-loss count: candidate identities
can be lost and gained. All 15,488 overlapping 20 ms receiver/windows run.
This is a selected DS7 subset, not full DS7, and no DS8/DS9 qualification is
claimed. It does not preserve every previously recovered hit.

Builds include inherited component tests for all four rates and the ranking
oracle. `evaluate.py` declares the actual radius-one geometry; frozen
`standard-audit.json` files compare with the standard analysis pipeline.
Timing includes dwell preprocessing and proposal generation; initial setup,
file I/O, output formatting, and radio capture are excluded.

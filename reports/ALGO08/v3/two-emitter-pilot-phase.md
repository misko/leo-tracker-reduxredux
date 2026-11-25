# Coincident pilot phase can join different transmitters

The unchanged installed ALGO08v3 detector returned **two different-transmitter
pairs within ±2 wrapped samples**. One passed with a −98.301 kHz signed
carrier difference and the other with a +227.254 kHz difference, near
one complete carrier alias period. Their phases differ by −0.107 and
+0.108 samples. Signed CFO and separate single-emitter detections
support the two winner identities independently of phase and gain
rank. This gives a counterexample to using phase agreement alone to
discard a competing transmitter before solving.
[Frozen protocol](two-emitter-pilot-phase-protocol.md) ·
[All mixture and isolated factors](measurements/two-emitter-pilot-phase.json.gz)

| Fixed case | Supported RX1 / RX2 winner | Wrapped RX2 − RX1, samples | Within ±2 |
| --- | --- | ---: | --- |
| Empty | — / — | — | — |
| One radio | A / — | — | — |
| Same transmitter | A / A | +0.419 | Yes |
| Same transmitter with shared decoy | A / A | +0.246 | Yes |
| Different transmitters, coincident arrivals | A / B | −0.107 | Yes |
| Different transmitters, separated arrivals | A / B | +66.931 | No |
| Different transmitters, near carrier alias | A / B | +37.000 | No |
| Different transmitters, exact planted carrier alias | A / B | +0.108 | Yes |
| Identical pilot atoms, swapped planted strengths | Ambiguous / ambiguous | +0.431 | Yes |

Seven of nine synthetic opportunities gave two detector winners. Both
supported same-emitter pairs agreed, as did two of the four supported
different-emitter pairs and the one ambiguous pair. Both pilots exist
on both radios in the two-emitter cases. Swapping their gains does not
identify a winner when the planted epochs and signed frequencies
coincide on each radio. The coverage describes this fixed synthetic
matrix with one arbitrary 18 m baseline. It estimates no field error
rate, position or inter-radio calibration.

The case table and association rule sealed at `213f449227684e92eff7ba1be8b492873037dcdf`.
The one nonblocking Gauss lease admitted at 3.52% full 10 s I/O PSI
and zero queued requests on dm-5. The single CPU2 worker ran at nice
15 with idle I/O and a 12 s cutoff. It completed in 2.12 s elapsed and
1.48 CPU s (1.25 user, 0.23 system), with 207,928 KiB maximum RSS.
The 46 native calls took 0.160 wall and CPU seconds. Reproduction
uses the installed Python environment and pinned implementations
in the runner. The uncompressed receipt SHA-256 is
`4922e2c5937aa05e0558d0c714559d4298756e59ea9e30d1cd67c1eb8443e252`.
Three component tests passed. No acquired waveform, orbit data,
solver or production changes were used.
[Runner](two_emitter_pilot_phase.py) ·
[Component tests](../../../tests/pipeline_eval/test_two_emitter_pilot_phase.py)

# Primary-literature constraint check

Reviewed September 29, 2026, against the actual firmware assays and prior
experiments, rather than treating a secondary patent summary as a decoder.

The [downlink patent US12074683B1](https://patents.google.com/patent/US12074683B1/en)
describes a BPSK header, a non-systematic, non-recursive rate-1/3 convolutional
code with six memory bits, and sequence/partial/MCS fields. Its transmitter
discussion separates payload-bit scrambling from symbol rotations. The latter
uses polynomial `1+D^14+D^15` and resets at burst boundaries. These are example
architectures, not a demonstrated mapping of our captures. Relevant locations:
description of Figs. 6A, 6B and 9, and the packet-header decoding discussion.
The text also uses both 15-degree polynomial and 16-bit register descriptions;
that wording alone must not determine an implementation's register convention.

The [uplink patent US12003350B1](https://patents.google.com/patent/US12003350B1/en)
also describes separate payload-bit and rotational scrambling stages. It is not
independent confirmation of an observed downlink header layout.

## What changes in our interpretation

No new RF scan is justified by this check. The following constraints already
have reproducible investigations in this repository:

| Constraint | Existing implementation/evidence | Remaining limitation |
|---|---|---|
| Rotational PN model | `../2026_09_28_sequence_semantics/rotational_descramble.py`, `scrambler_candidates.py` | Historical public-reference work; no newly established local field placement |
| Candidate convolutional structure | `../2026_09_28_sequence_semantics/moving_header_code.py`, `blind_header_114.py`, `rectangle_convolution_probe.py` | Assumed generators/order; prior negative scans do not exclude other coding or placement |
| 32 information bits / 114 coded symbols | Firmware MAC table and scheduler evidence in `../../docs/research/starlink-literature/firmware-header-analysis.md` | Numerical agreement does not identify generators or RF coordinates |
| Software prefix and bit order | `prefix_execution.py`, `PREFIX_BRANCHES.md` | Actual software serialization is not an on-air bit-order proof |

The patent's sequence field does not establish that the observed T-state is a
counter. Its scrambling architecture does not turn the seven frozen local sign
pairs into code checks. The actual firmware role labels and mask/table consumers
remain the stronger constraints on interpretations of their respective software
constants. No patent evidence supplies a SATAddr-to-NORAD equivalence.

This check preserves the main ranking: shared early received structure is
supported; a particular header-field interpretation remains unverified. The
missing bridge is an independently constrained mapping between recovered RF
coordinates and the software decoder's input, including coding and scrambling.

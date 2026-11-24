# Passive admission screen on three medium physical recordings

None of the three frozen recordings passed the two-end residency screen. All six signed end-member paths were observable, with **zero of 83,104 file pages resident**. Neither an interior-member census nor a raw publication ran. [Frozen protocol](end-member-admission-protocol.md) · [Machine receipt](measurements/end-member-admission.json)

| Original recording | Captured visits | First member, resident / total pages | Last member, resident / total pages |
|---|---:|---:|---:|
| DS30-0169 | 4,219 | 0 / 19,252 | 0 / 17,375 |
| DS30-0445 | 4,312 | 0 / 18,938 | 0 / 6,695 |
| DS30-0083 | 4,807 | 0 / 19,170 | 0 / 1,674 |

The exact locally sealed named ALGO08v3 pairs record complete fixes and clocks for these three. Both historical methods published fixes in both calibration arms. The recorder marked each capture `incomplete`, and the signed input inventory accounts for every recorded visit. The selection excluded DS30-0057 and DS30-0316, which already had dedicated whole-roster observations. Closer above-band candidates without a sealed local named-v3 clock were ineligible. The original named benchmarks included their own historical cache measurements. This is a one-time exact end-member probe, with no inference about unseen interior pages. [Earlier DS30-0316 query](prospective-small-physical.md) · [Local enrollment record](family-endpoint-transfer-0169.md)

First and last paths came from the archived manifest roster, signed captured-visit counts, and the original 64-window member naming scheme. Its complete expected member count matched the old benchmark on each recording before the endpoint descriptors opened. The passive query checked the inode, regular-file type, owner and extent and used inaccessible mappings. It took 4.58 ms under the existing Gauss lock. The scope charged 88 input blocks and zero major faults. There were no original manifest-body or waveform reads, no readahead, and no staging. Three component tests passed. [Scanner](end_member_admission.py) · [Tests](../../../tests/pipeline_eval/test_end_member_admission.py)

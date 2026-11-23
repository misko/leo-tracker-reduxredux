# Fixed-timing CFO remeasurement on the original 20 ms waveform

On held DS30-0169, adding a bounded frequency measurement reduced signed CFO RMS against the full-aperture primary from **87.70 to 53.28 Hz**. Absolute error fell on **27 of 38 fixed counterparts**, worsened on four, and stayed equal on seven. All **45 short positives** were retained. The candidate made no change to their reported epoch, rank, radio, or original admission margins. [Waveform receipts, paired errors, and development freeze](measurements/short-cfo-refine.json.gz)

## Measured frequency at the original timing

The short detector nominates and admits the original primary. The new helper reuses the installed verifier's integer or fractional pilot interpolation at that primary's measured timing and signed CFO. Within each pilot frame, it cross-multiplies corresponding despread half-frame blocks and sums their complex products. The resulting phase measures the local signed frequency offset without requiring a phase connection between frames. The proposal uses all valid 20 ms frames. Prefix-contained and wholly trailing frames provide independent consistency checks.

The frozen rule applies the full offset when at least four disjoint tail frames contribute, tail exact-minus-rolled exceeds 0.025, both delay-product coherences are at least 0.70, and the two independent offsets agree within 400 Hz. The full correction must be within ±250 Hz and keep the signed CFO in its original search interval. Every other case returns the original tuple. The wrapper receives waveform samples, the short tuple, and the receiver's RF search center. Full reference factors enter the scorer only. The original timing and GLRT margins describe the original short acceptance and remain attached to it. [Native estimator](short_cfo_refine.inc) · [Gate and replay](short_cfo_refine.py)

The earlier tail confirmation used trailing evidence to reject a hypothesis. The scout readout changed the acquisition path and depended on a small independent symbol block. Directed verification changed how a scout reached verification. The short epoch audit changed the downstream time convention. This experiment keeps the original detector and published epochs and changes only the measurement of frequency when the longer waveform supports it. [Tail confirmation](tail-confirm.md) · [Scout readout](scout-readout.md) · [Directed verification](directed-verifier.md) · [Short epoch audit](short-primary-epoch.md)

## Fixed counterparts and held transfer

Development used the first 24 signed physical DS30-0008 visits already staged in tmpfs and 18 saved weak DS26 stereo clips, copied to tmpfs using cache-only reads. The three predetermined correction fractions were 0.25, 0.5, and 1.0. All passed the pooled improvement gates. The lowest pooled RMS selected 1.0 before the DS30-0169 staged member was opened. Pinned full and short libraries verified the signed dense and held source probes. Weak references were fresh signed full-aperture primary calls on the same sealed clip samples. The held 64-visit member supplied 51 admitted visits and 86 nonanchor lanes. Every clip intake charged zero block-storage reads.

A fixed counterpart requires a rank-zero 20 ms factor within two wrapped samples and 250 signed Hz of the original short primary. The rule forms that comparison before refinement. All originally matched lanes remain in the denominator, including fallbacks. The frequency table uses Hz throughout.

| Panel | Short positives retained | CFO updates | Fixed counterparts improved | Signed median, short → refined | Absolute median, short → refined | RMS, short → refined |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Dense DS30-0008 development | 21/21 | 17 | 16/19 | +58.29 → −2.98 | 69.40 → 12.63 | 97.05 → 57.75 |
| Weak DS26 development | 34/34 | 26 | 19/30 | +11.98 → +3.53 | 31.49 → 17.04 | 61.73 → 27.95 |
| Held DS30-0169 | 45/45 | 35 | 27/38 | −11.30 → +1.17 | 60.77 → 19.55 | 87.70 → 53.28 |

Held radio 0 improved on 19 of 22 counterparts and its RMS fell from 84.90 to 25.48 Hz. Radio 1 improved on eight of 16 and its RMS fell from 91.42 to 76.48 Hz. The median wrapped epoch difference with the full reference remained 0.264 samples. Four of the seven held short positives without a fixed full reference were also updated. Those four lack an accuracy comparator. The experiment scores the longer receiver's measurement as a reference and contains no geographic test.

## North simulation transfer

The unchanged physical freeze and DSO retained all 58 short positives from the first 64 signed visits in the existing North tmpfs member. The same short and full signed factor controls verified the lane inputs. All 24 updated short positives had fixed full counterparts and improved. The remaining matched lane fell back unchanged. Absolute median CFO error fell from **10.31 to 1.25 Hz**, signed median from **+9.67 to +0.03 Hz**, and RMS from **29.38 to 27.12 Hz**. One unchanged outlier accounts for most of the remaining squared error.

Radio 0 improved on 12 of 13 counterparts and its RMS went from 39.12 to 37.57 Hz. Radio 1 improved on all 12 and its RMS went from 11.87 to 1.79 Hz. The median paid addition was **39.465 CPU ms**, compared with **111.724 CPU ms** for the short baseline. The read-only tool verified full page residency and read 84,305,903 logical bytes from the signed tmpfs member, with zero block-storage reads. An initial preflight under the recording account could not query page residency on the owner-held file. The completed run used the file owner under the same Gauss lock and CPU, process, and I/O priorities. This transfer compares waveform frequencies against the full reference from the same simulation. [North replay](short_cfo_north.py) · [North receipt](measurements/short-cfo-north.json.gz)

## CPU cost and controls

Five interleaved repeats charged refinement and rule evaluation for each opportunity. The median added CPU / wall was **14.443 / 14.446 ms** for the dense fixture, **25.384 / 25.390 ms** for weak, and **32.570 / 32.579 ms** for held. The held short-only baseline used 84.217 CPU ms on those nonanchor lanes. The added **0.724 ms per short positive** projects to **4.62 CPU seconds** if 6,380 positives cost the same as this held fixture. The exact interpolator still visits the full aperture, though there is no timing or carrier search. This is a measurable RF-quality improvement with an added CPU charge.

The identical development and held DSO has SHA-256 `fed887f464c78d9a547bd1d939dbb0a3987ab4babd3db8f0779928be5a6a1d4e`. Four native controls on both pilot edges, with both signed carrier polarities and integer or fractional timing, reduced planted ±80 Hz errors below 0.68 Hz. Zeroing the tail left the original tuples intact in all four controls. Eleven component tests passed. [Component tests](../../../tests/pipeline_eval/test_short_cfo_refine.py)

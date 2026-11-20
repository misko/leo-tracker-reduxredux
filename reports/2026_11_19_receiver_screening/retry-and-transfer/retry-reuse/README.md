# Reuse the original detector’s two shared retry anchors

Keep the prepared coarse bank. A preallocated magnitude cache avoided **17,577 inverse transforms per retry** and reproduced every coarse score and public candidate on six genuine visits. Median paired coarse CPU increased by **10.40 ms on retry visits** and **4.79 ms on visits without a retry**. The measured cost ends the detector trial. [Stage chart](stage.pdf) · [Plotted measurements](stage.csv) · [Protocol](PROTOCOL.md)

## Shared geometry and exact replay

The primary anchor IDs are `range(2, 302, 26)`. The retry IDs are `range(2, 302, 14)`. Their intersection is exactly **2 and 184**, at offsets 88 and 8,096 samples at 10 Msps. Both use the same 44-sample aperture, template normalization, CFO lattice, frame clocks and valid-start support. Their native 22-anchor contributions include the same partial final frame boundaries.

The native primary fold retains one float32 magnitude per physical start, anchor and CFO for the two shared anchors. The same magnitude enters the same weighted float64 accumulation in each original pass. The retry keeps its own complete support count and original accumulation order. It skips only the shared inverse FFTs. A single preallocated buffer serves the receiver still eligible for retry. The wrapper releases a passing lane and collects the other lane only when it might be retried. A lookup checks receiver, probe, edge, rate, frequencies, epoch count, exact template bytes and exact IQ bytes. The current cache lifetime is one stereo visit.

Per visit the cache reserves 33,600,000 bytes for float32 magnitudes. Holding the existing complex128 sample and template buffers extends their lifetimes by at most 3,413,328 bytes on the measured geometry. The cache allocates its region when the adapter is created and holds references to the existing waveforms. Cache admission took 5.27 µs median for a staged primary call and the byte-checked retry lookup took 475 µs. The measured coarse clock includes the larger cost of filling and reading the magnitude buffer. [Per-grid costs and transforms](grids.csv)

## Matched radio visits

Five alternating comparisons per visit used three authenticated capture producers and both pilot edges. Both FFT workspaces persisted across calls, with first-use costs included on the first pair. The natural retry cases exercised both receiver lanes. All **4,199,895** inspected coarse cells and all **96** ordered public candidate records agreed exactly, with all **19** fractional gate positives retained. The installed arm reproduced the archived probe rows. Empty controls emitted zero candidate records. Both signed controls retained the planted negative CFO on both lanes. The tied-carrier component test reproduced the entire tied map, including its supported tail, and forced an independently scored crossed-lane retry.

| Visits | Median paired change in coarse CPU | Median paired change in full CPU | Median paired change in full wall |
| --- | ---: | ---: | ---: |
| Three with retry | +10.40 ms | −5.42 ms | −4.53 ms |
| Three without retry | +4.79 ms | +8.64 ms | +9.90 ms |

The paired coarse change was positive in every case. Whole-detector measurements varied more across repetitions and producer releases. A retry used 173,460 inverse FFTs from 191,037. The additional cache traffic and lookups outweighed those savings. Among exported acquisitions, zero fine-entry `(refined epoch, coarse CFO)` or finished `(refined epoch, acquired CFO)` keys appeared in both primary and retry for the same lane. [All paired timings](timing.csv) · [Full field and grid comparisons](decisions.json)

## Reproduction

Run `tools.pipeline_eval.qualification.retry_reuse_eval <local-scratch>` for the build and fixed capture lock. Use the installed capture Python and each named producer root first on `PYTHONPATH`, pin CPU 2 or 3 and set one numerical thread. Run the same module with `<local-scratch> <case>` to replay a case. Run `tools.pipeline_eval.qualification.retry_reuse_results <local-scratch> <output>` to reproduce the stage without radio decoding. Detector results end at candidate output. [Source freeze](source-lock.json) · [Evidence seal](evidence-lock.json)

# Stateless server concurrency benchmark

The unchanged FP32 FFTW detector preserved every scientific result under
concurrency. Across all 256 receiver visits and every timed repetition, the
1/2/4/8-worker results exactly matched serial FP32. Relative to packed FP64,
FP32 retained all 129 positive observations within the frozen 2 microsecond and
8 kHz association gates, added none, and changed no rank order, selected
window, or projected epoch.

The practical two-receiver mode waited for RX0 and RX1 of each physical visit
before submitting the next visit. Serial FP32 reduced the median pair latency
from 5.50 ms to 3.74 ms and p95 from 8.75 ms to 6.25 ms relative to serial
packed FP64. Two concurrent FP32 workers reduced median pair latency further to
3.17 ms, but p95 worsened to 10.04 ms and aggregate process CPU rose from
478.2 ms to 560.2 ms for the complete 256-receiver schedule. This mode offers
no latency-tail improvement on this host.

| Mode | Batch wall median | Aggregate CPU median | Receiver visits/s | Wall speedup vs FP64 | Pair wall median / p95 |
|---|---:|---:|---:|---:|---:|
| Packed FP64 serial | 740.2 ms | 740.1 ms | 345.8 | 1.00x | 5.50 / 8.75 ms |
| FP32 serial | 502.4 ms | 478.2 ms | 509.5 | 1.47x | 3.74 / 6.25 ms |
| FP32 two-receiver pair | 466.2 ms | 560.2 ms | 549.2 | 1.59x | 3.17 / 10.04 ms |
| FP32 batch, 1 worker | 505.1 ms | 505.1 ms | 506.8 | 1.47x | — |
| FP32 batch, 2 workers | 349.8 ms | 490.2 ms | 731.8 | 2.12x | — |
| FP32 batch, 4 workers | 364.8 ms | 500.4 ms | 701.7 | 2.03x | — |
| FP32 batch, 8 workers | 240.6 ms | 510.5 ms | 1,064.0 | 3.08x | — |

Eight-worker batch mode had the highest throughput, but the 3.08x wall speedup
is well below 10x. Aggregate CPU was 510.5 ms, distinct from the 240.6 ms batch
wall time. Four workers were slower than two in this bounded run, and task p95
rose from 3.44 ms with one worker to 3.87 ms with eight. Batch concurrency
improves queued-work throughput while increasing individual task latency.

IQ loading, input/source-file hashing, page warming, thread creation, native
workspace creation, and FFT planning were excluded. Timings include
receiver-view formation, required FP64 packing, dispatch, the detector, result
compaction, and result collection. Result compaction includes pickling and
SHA-256 hashing each scientific signature for exact cross-worker validation.
That validation overhead is not representative of a narrow production result
port and can serialize Python work under the GIL. This experiment does not
separate that overhead from native execution, so it cannot attribute the
observed 3.08x scaling limit to the native kernel, FFTW, or the GIL. Measuring a
narrow result port would require a new preregistered benchmark. The main thread
and workers were pinned to P-cores 0–7, and the original main-thread affinity
was restored. Per the
[FFTW thread-safety contract](https://www.fftw.org/fftw3_doc/Thread-safety.html),
all workspace creation, lazy-plan prewarming, and destruction ran serially;
only execution of private plans ran concurrently.

The valid timed phase lasted 10.06 seconds with one warmup and three
counterbalanced repetitions. The first attempt is retained as an invalid
receipt: it failed during host-metadata serialization, wrote no result, and
exposed no timing values. The clerical fix was re-locked without changing the
benchmark design before the valid rerun.

Batch throughput is not single-visit latency, a real-time guarantee, aggregate
CPU speedup, or an end-to-end pipeline result. This server-only stateless
component benchmark makes no ARM claim and uses no fallback, cache, or
lookahead.

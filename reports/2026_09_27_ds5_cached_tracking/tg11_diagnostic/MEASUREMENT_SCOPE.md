# What the 1,515 ms to 16 ms result measures

The result is an observed server processing-time reduction of approximately
94.5x at 2.5 MS/s and 122.8x at 5 MS/s on the four frozen development visits.
Both calls receive the same natural CI16 recording: 120 ms, two receivers.
One P-core executes the paired calls with numerical worker counts fixed at one.
Input conversion, search, scoring, and decision/state assembly are inside the
timed calls. File loading, source hashing, and reusable initialization are outside.
There is one warmup and three measured repetitions for each method and visit.
See `../tg11/phase1_cost_results.json` for the individual measurements.

The baseline is the current repository scanner configured for eleven overlapping
20 ms probes, both receivers, and ten acquisition candidates per probe. Its
decision wrapper derives the decision from the complete analysis. The prototype
uses the existing native C/FP32 FFTW presence implementation with a much smaller
candidate inventory, scans all eleven windows, and returns a fresh supporting
pair. These are different search procedures and different reporting contracts.
Both use GLRT evidence, but the original prototype's final symbol selection and
preprocessing also differ from the current scanner.

The result is neither a measurement on DS5's ARM processor nor a deployed DS5
end-to-end latency measurement. It does not include RF capture or recording I/O.
It is not a same-220-result numerical optimization and does not establish a
corpus-wide or tail-latency bound. All measured routes were cold blind searches,
so it also does not measure a benefit from cached tracks.

The current Python point scorer independently passes the prototype's additional
hypothesis at two nonoverlapping probes; its original acquisition search did not
retain those coordinates. This is encouraging detection evidence, but it does
not transform the four-visit study into a qualified replacement. The failed
TG11 comparator gate remains failed. The following canonical-scoring prototype
has its own measurements and must never inherit these timing numbers.

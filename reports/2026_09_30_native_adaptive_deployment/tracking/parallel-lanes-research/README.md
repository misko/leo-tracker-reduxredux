# Independent tracking lanes

This research copy partitions the existing ordered lane map across one caller
and one worker. Each lane retains its original point order, histogram, fit
cache and floating-point calculations. Results merge in original lane order
before the unchanged final sort. Exceptions are retained per lane, all work is
joined, and the first exception in lane order is rethrown. The production
tracking implementation and deployed application remain serial.

Build with `bash tests/native_adaptive/tracking/build_parallel_lanes_research.sh`
and `host`, `sanitize`, `thread` or `arm`. The two sanitizer modes instrument the
tracking implementation and test/CLI together. Component tests and the complete
DS9 fixture pass ASAN/UBSAN and ThreadSanitizer. All 60 causal prefixes match the
serial oracle exactly. The shared prefix comparison tool retains its historical
fit-cache schema name; this directory identifies the actual experiment.

An eventual production interface should accept a synchronous, borrowed execution
port rather than create a hidden pool inside reconstruction. The caller owns
worker lifetime and the total capture/detector/analysis CPU budget; dispatch
must execute every lane exactly once and finish all callbacks before returning,
including when propagating a worker failure. Existing callers retain serial
execution. The same port can serve stateless and optional cached reconstruction
without modifying scientific configuration or persisted result contracts.

Before production use, test serial and two-worker adapters, failure propagation,
bounded scheduling and context lifetime, and compare full DS9/prefix results.
The isolated physical benchmark does not establish capture contention behavior.
Do not enable two analysis workers on PLUTO+ from this result alone; Pi and
offline execution can reserve different explicit worker budgets.

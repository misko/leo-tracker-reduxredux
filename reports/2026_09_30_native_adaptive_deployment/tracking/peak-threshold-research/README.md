# Peak cutoff experiment

This isolated copy of the deployed tracking source splits initial heap filling
from subsequent peak admission. Once the heap is full, bins strictly below its
current minimum cannot enter the retained top peaks. The original comparison
still decides ties and replacements; the cutoff refreshes after each accepted
replacement. Histogram accumulation, candidate visitation and fitting are
unchanged. The experiment receipt freezes the pre-promotion state. After review,
the identical source delta was promoted; see
[production deployment](../../application/peak-cutoff-deployment.json).

Build with `bash tests/native_adaptive/tracking/build_peak_threshold_research.sh`
using `host`, `sanitize` or `arm`. The build runs component tests on host and
sanitizer. `peak_threshold_fixture.cpp` additionally covers 30 configurations:
equal or varying weights, 1/8/32 intercept bins and 1/4/16/64/1000 retained peaks.
Compile it against both the frozen control and candidate objects and compare
stdout. All 30 cases contain tracks; host, sanitizer and physical ARM output
matches exactly, including ties and heap capacities exceeding one histogram.

All 60 causal DS9 prefixes match the deployed control. The shared prefix tool's
historical schema name mentions fit caching; the experiment here is peak
admission. [The receipt](receipt.json) binds source and binary hashes and keeps
the raw compiler-matched physical ABBA logs. Mean cold reconstruction improves
from 28.869 to 27.842 seconds (3.56%), with the same complete output bytes. This
is CPU-only tracking evidence and does not qualify continuous operation.

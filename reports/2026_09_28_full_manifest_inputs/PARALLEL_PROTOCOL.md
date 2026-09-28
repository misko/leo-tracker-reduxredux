# Execution-only amendment: two disjoint input workers

Applies only to future stages launched by launch_parallel.py. The original
PROTOCOL.md, serial launcher, executed stages and their seals remain unchanged.
Full manifest membership, five-record batches, scientific exporter/loader,
partition, banks, stage timeouts, 4 GiB address-space cap, BLAS1/nice19, 1800 s
invocation deadline, validation gates and no-retry policy are unchanged.

The first ten new recordings took 897.94 summed job seconds; measured peak RSS
was below 0.9 GiB. After production workload release, available memory was 41 GiB
at the start of this tranche. Permit at most two input workers, exactly one
for DS8 and one for DS9. No modeling worker may overlap this two-input mode.
Each launcher holds a shared global lock, incompatible with the old serial
launcher's exclusive lock, plus an exclusive dataset lock. Invalid datasets,
duplicate dataset workers and serial/parallel overlap must fail before science.

Before each stage require MemAvailable >= 2 GiB for validation, 2.5 GiB for observation
export and 3 GiB for bank export. These checks add 1 GiB to each serial threshold;
they are not reservations against independent production workloads. Preserve
unstarted stages on insufficient headroom or time. Do not alter services to
force capacity. Audit only after all participating launchers are terminal.

Archive this amendment, the new launcher, lock helper and focused lock tests
in every new stage's bindings. The unchanged scientific runner determines all
numerical outputs. This is an execution-budget change, not a model retuning,
new collection, provider fetch or exception to read-only QNAP access.

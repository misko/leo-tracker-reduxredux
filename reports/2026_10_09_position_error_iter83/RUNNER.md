# Serial checkpoint continuation

The frozen experiment uses600-second invocations and resumes immutable receipts.
`run_shard.py` automates up to three such invocations for one shard, waiting for
each subprocess to exit successfully before starting the next. It stops on a
nonzero exit or changed protocol, and never reruns a shard whose terminal member
receipts are complete. A terminal member failure remains terminal and explicit.

Launch only after the existing invocation for that shard has authoritatively
terminated. At most two shard runners may be active, each with one numerical child.
Use the same production Python, worker source path, single-thread BLAS environment
and worktree as the original invocation. This changes orchestration only; the
frozen numerical sources, fit budgets, policy and membership remain untouched.

Three tests verify no duplicate invocation after completion, no retry of a fatal
subprocess exit, and bounded serial continuation of incomplete successful invocations.
The runner has not been used to alter any scientific outcome or hide failed receipts.

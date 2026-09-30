# Engineering amendments

The initial `uv run` launcher stalled before Python started (empty logs, no Python child), including timeout cleanup stalls. The scheduler and its own descendants were stopped; `launcher-interruption.json` records the PIDs. Original logs and receipts remain. A diagnostic direct cached interpreter also blocked on `xfs_buf_lock` in the bulk filesystem containing the uv cache.

Resume uses the immutable installed release Python directly through sudo, with NumPy 2.4.6 and SciPy 1.18.1. `installed-replay/runs/00_shared.json` repeats a completed original fit: selected parameters and score are exactly equal. The numerical runner, model sources, starts, iteration limits, qualification and 90-second fit cap are unchanged. Existing completed scientific outputs are retained. Missing outputs from empty-log launcher failures are retried, with `.retry` logs and receipts; no model qualification failure is retried. Input-export failures can be retried only on the same frozen scan, with original receipts preserved.

Bulk filesystem contention also caused derived-input export timeouts. Recovery resumes completed observation exports at the orbit-bank stage, with a separate bounded stage receipt and unchanged observation content, bank policy and validation. This changes preprocessing scheduling, not fitting budgets or sample membership.

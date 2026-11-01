# ALGO06 production promotion

The approved policy is 72-hour causal new-family recovery with ±30-second phase bounds and no recency penalty. See [the algorithm specification and paired cohort results](../ALGO06/README.md).

The deployment uses a separate v5 persisted namespace and preserves ALGO05 as the upstream incumbent and exact fallback. All previous scientific manifests remain pinned. The production default will be selected only after release staging, contract/storage/worker tests, a bounded causal live-data replay, and API verification.

The capture timer's post-recording gap is now 7 minutes 30 seconds rather than 20 minutes. Five-minute recordings and fast/adaptive alternation are unchanged, doubling the nominal cadence. Existing backlog protection remains active. Before-change configuration is recorded in `cadence-before.txt`.

Qualification and activation receipts are added here when each operation completes. No historical result or recording is rewritten.

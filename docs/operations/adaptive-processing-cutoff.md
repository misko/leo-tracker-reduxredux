# Adaptive recording processing cutoff

`LEO_ADAPTIVE_MIN_CAPTURE_UTC_NS` sets an optional inclusive minimum recording
timestamp for adaptive analysis and tracking queue admission. It uses the sealed
capture timing's `first_sample_estimate_utc_ns`, not the manifest creation or
publication time. With a cutoff configured, recordings without capture timing
are also excluded. Without this variable, existing queue behavior is preserved.

The guard applies to live enqueue, explicit tracking backfill, and tracking
scheduled after analysis completes. Configure it on both the queue service and
the worker template. It does not cancel jobs already queued: stop queue admission
and workers, audit actual recording timestamps, cancel the older pending jobs,
then restart with the cutoff enabled. Keep recordings and completed products.

On October 1, 2026, the operational cutoff is `1790812800000000000`, corresponding
to October 1 at 00:00 UTC. The deployment extends the existing presentation-only
package snapshot with `cli/adaptive_processing_queue.py`; scientific processing
and the ten-minute capture gap remain unchanged.

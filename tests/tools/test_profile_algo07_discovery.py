"""Discovery measurement observes eligibility without starting any processing."""

from tools.profile_algo07_discovery import measure


def test_discovery_counts_pending_and_recoverable_running_jobs_only():
    class Store:
        def inputs(self, *, minimum_completed_utc_ns):
            assert minimum_completed_utc_ns == 25
            return iter([dict(job_id=str(i)) for i in range(5)])

        def status(self, job_id):
            return {
                "0": dict(state="complete"),
                "1": dict(state="failed"),
                "2": dict(state="running"),
                "3": None,
            }[job_id]

    result = measure(Store(), cutoff=25, limit=4)
    assert result["completed_input_jobs"] == 4
    assert result["eligible_job_ids"] == ["2", "3"]

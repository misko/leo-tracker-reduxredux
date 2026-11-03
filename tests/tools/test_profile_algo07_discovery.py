"""Discovery measurement observes eligibility without starting any processing."""

from tools.profile_algo07_discovery import SelectedIncumbent, measure


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


def test_matched_selection_composes_with_pending_filter():
    class Source:
        def completed_inputs(self, *, minimum_completed_utc_ns, include_status):
            assert minimum_completed_utc_ns == 10
            for identifier in ("a", "b", "c"):
                row = dict(job_id=identifier)
                if include_status(row):
                    yield row

        def terminal(self, job):
            return job, {"sha256": "same-receipt"}

    source = SelectedIncumbent(Source(), ["a", "c"])
    rows = list(
        source.completed_inputs(
            minimum_completed_utc_ns=10, include_status=lambda row: row["job_id"] == "c"
        )
    )
    assert rows == [dict(job_id="c")]
    assert source.seen == {"a", "c"}
    assert source.terminal(rows[0]) == (rows[0], {"sha256": "same-receipt"})

import select_balanced_confirmation as selector


def row(session_id, time, *, ready=True, pose=True):
    return {"session_id": session_id, "capture_start_utc_ns": time,
            "pose_valid": pose, "pose_error": None, "tracking_ready": ready}


def test_combined_development_is_unique_and_contains_both_frozen_cohorts():
    combined = selector.combined_development()
    ids = [item["pose"]["session_id"] for item in combined["sessions"]]
    assert len(ids) == len(set(ids)) == 14
    assert all(value.startswith("sha256:")
               for value in combined["source_manifest_sha256"].values())


def test_wrapper_selects_earliest_ready_disjoint_rows_strictly_after_latest():
    combined = selector.combined_development()
    ids = {item["pose"]["session_id"] for item in combined["sessions"]}
    after = max(item["pose"]["capture_start_earliest_utc_ns"]
                for item in combined["sessions"])
    excluded = next(iter(ids))
    rows = [row(excluded, after + 1), row("old", after),
            row("not-ready", after + 2, ready=False),
            row("one", after + 3), row("two", after + 4)]
    selected, accounting = selector.select_after_combined(
        rows, combined, selector.METADATA_CUTOFF_UTC_NS, count=2)
    assert [item["session_id"] for item in selected] == ["one", "two"]
    reasons = {item["session_id"]: item["exclusion_reasons"] for item in accounting}
    assert "development_cohort" in reasons[excluded]
    assert "not_after_development" in reasons["old"]


def test_wrapper_enforces_frozen_cutoff_without_replacement():
    combined = selector.combined_development()
    after = max(item["pose"]["capture_start_earliest_utc_ns"]
                for item in combined["sessions"])
    rows = [row("inside", after + 1),
            row("after-cutoff", selector.METADATA_CUTOFF_UTC_NS + 1)]
    selected, accounting = selector.select_after_combined(
        rows, combined, selector.METADATA_CUTOFF_UTC_NS, count=1)
    assert [item["session_id"] for item in selected] == ["inside"]
    late = next(item for item in accounting if item["session_id"] == "after-cutoff")
    assert late["exclusion_reasons"] == ["after_metadata_cutoff"]

from batch import run_member


def test_only_pending_slices_resume_failed_results_never_retry():
    calls = []
    counts = {}

    def invoke(label, phase):
        calls.append((label, phase))
        counts[phase] = counts.get(phase, 0) + 1
        if phase == "search":
            return "pending" if counts[phase] == 1 else "complete"
        return "failed" if phase == "native" else "complete"

    result = run_member(dict(label="member"), invoke, lambda *args: None)
    assert result == dict(search="complete", native="failed", fixed="complete")
    assert len(calls) == 4 and counts["native"] == 1
    calls.clear()
    assert run_member(dict(label="member"), invoke, lambda label, phase: result[phase]) == result
    assert not calls


def test_fixed_slice_caps_no_extension():
    calls = []
    result = run_member(
        dict(label="member"),
        lambda label, phase: calls.append(phase) or "pending",
        lambda *args: None,
    )
    assert all(status == "pending" for status in result.values())
    assert calls.count("search") == 6 and calls.count("native") == calls.count("fixed") == 2
